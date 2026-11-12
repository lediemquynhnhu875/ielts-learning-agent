"""Start, resume, save and submit practice against a fixed verified snapshot."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import secrets
from uuid import UUID, uuid4

from .grading import grade, validate_exercise
from .ports import AttemptStore


class PracticeError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_exercise(source: dict) -> dict:
    """Allowlist learner content; trace/provider/verification details stay private."""
    result = {key: source[key] for key in ("id", "title", "text", "skill", "topic", "target_band")}
    result["question_groups"] = []
    for group in source["question_groups"]:
        public = {key: deepcopy(group[key]) for key in (
            "group_id", "position", "question_type", "instructions", "response_mode",
            "options", "response_limits", "allow_reuse"
        )}
        public["questions"] = []
        for question in group["questions"]:
            if question.get("excluded", False):
                raise ValueError("Excluded question")
            projected = {key: question[key] for key in ("id", "position", "number", "prompt")}
            projected["options"] = deepcopy(question.get("options", {}))
            projected["target"] = {key: value for key, value in question.get("target", {}).items()
                                   if key in {"item_id", "paragraph_id"}}
            public["questions"].append(projected)
        result["question_groups"].append(public)
    return result


class PracticeService:
    def __init__(self, store: AttemptStore, *, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def start(self, item_id: str) -> dict:
        source = self.store.load_source(item_id)
        if source is None:
            raise PracticeError("exercise_not_found", "Exercise not found or unavailable", 404)
        exercise, key = source
        try:
            if (exercise["id"] != item_id or exercise["status"] != "verified"
                    or exercise["skill"] not in {"reading", "listening"}
                    or any(exercise["validation"].get(layer) is not True for layer in ("rules", "solver"))):
                raise ValueError("Exercise is not verified Reading/Listening content")
            public = _public_exercise(exercise)
            for group in public["question_groups"]:
                for question in group["questions"]:
                    if str(UUID(question["id"])) != question["id"]:
                        raise ValueError("Question IDs must be canonical UUIDs")
            # Validate the whole snapshot before creating a resumable attempt.
            # This uses only the answer key and code; it never calls a model.
            validate_exercise(public, key)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise PracticeError("exercise_not_gradable", "Exercise has no supported, verified answer key", 409) from error
        token = secrets.token_urlsafe(32)
        attempt = {
            "attempt_id": str(uuid4()), "item_id": item_id, "skill": public["skill"],
            "status": "in_progress", "token_hash": _token_hash(token),
            "exercise_snapshot": public, "answer_key_snapshot": deepcopy(key),
            "answers": {}, "started_at": self.clock(), "submitted_at": None,
            "result": None, "raw_score": None,
        }
        self.store.create(attempt)
        return {**self._view(attempt), "attempt_token": token}

    @staticmethod
    def _authorize(attempt: dict | None, token: str | None) -> None:
        if attempt is None or not token or not secrets.compare_digest(attempt["token_hash"], _token_hash(token)):
            # A guessed ID must not reveal whether someone else's attempt exists.
            raise PracticeError("attempt_not_found", "Attempt not found", 404)

    def get(self, attempt_id: str, token: str | None) -> dict:
        attempt = self.store.get(attempt_id)
        self._authorize(attempt, token)
        return self._view(attempt)

    @staticmethod
    def _merge(attempt: dict, answers: dict[str, str | None]) -> None:
        allowed = {question["id"] for group in attempt["exercise_snapshot"]["question_groups"]
                   for question in group["questions"]}
        if set(answers) - allowed:
            raise PracticeError("unknown_question", "Answers contain a question outside this attempt", 422)
        for response in answers.values():
            if response is not None:
                try:
                    response.encode("utf-8")
                except UnicodeEncodeError as error:
                    # Do not echo an unpaired surrogate in a validation response:
                    # that response itself could not be serialized as UTF-8.
                    raise PracticeError("invalid_answer", "Answers must contain valid Unicode text", 422) from error
        # Validate membership for the complete patch before changing any answer.
        attempt["answers"].update({key: response if response is not None and response.strip() else ""
                                   for key, response in answers.items()})

    def save(self, attempt_id: str, token: str | None, answers: dict[str, str | None]) -> dict:
        with self.store.edit(attempt_id) as attempt:
            self._authorize(attempt, token)
            if attempt["status"] != "in_progress":
                raise PracticeError("attempt_submitted", "Submitted answers cannot be edited", 409)
            self._merge(attempt, answers)
            view = self._view(attempt)
        return view

    def submit(self, attempt_id: str, token: str | None, answers: dict[str, str | None]) -> dict:
        with self.store.edit(attempt_id) as attempt:
            self._authorize(attempt, token)
            if attempt["status"] == "in_progress":
                self._merge(attempt, answers)
                attempt["result"] = grade(attempt["exercise_snapshot"], attempt["answer_key_snapshot"], attempt["answers"])
                # Materialize missing slots so stored answer rows and result agree.
                for question in attempt["result"]["questions"]:
                    attempt["answers"].setdefault(question["question_id"], "")
                attempt["raw_score"] = attempt["result"]["raw_score"]
                attempt["submitted_at"] = self.clock()
                attempt["status"] = "submitted"
            # Retries always return the original persisted submission.
            view = self._view(attempt)
        return view

    def _view(self, attempt: dict) -> dict:
        ended_at = attempt["submitted_at"] or self.clock()
        return {
            "attempt_id": attempt["attempt_id"], "item_id": attempt["item_id"],
            "skill": attempt["skill"], "status": attempt["status"],
            "started_at": attempt["started_at"], "submitted_at": attempt["submitted_at"],
            "elapsed_seconds": max(0, int((ended_at - attempt["started_at"]).total_seconds())),
            "exercise": deepcopy(attempt["exercise_snapshot"]), "answers": deepcopy(attempt["answers"]),
            "result": deepcopy(attempt["result"]),
        }
