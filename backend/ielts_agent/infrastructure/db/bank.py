"""PostgreSQL content bank with atomic verification, deduplication and publication.

This is a temporary standalone-practice schema, not a production migration for
the underspecified EXAM/EXAM_ITEM relationships. See DATABASE_CONTEXT.md.
"""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from itertools import groupby
import math
import re
from typing import Iterator
import unicodedata
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...agents.uc04.models import ExerciseDraft, GenerateRequest
from ...agents.uc04.rules import validate_rules
from ...core.errors import DuplicateError
from .migrations import apply_migrations


_LOCK_KEY = 0x55433034
_METADATA_KEYS = ("model", "prompt_version", "solver_model", "solver_prompt_version", "skill_hash")
_TERMS = re.compile(r"[^\W_]+", re.UNICODE)


class BankNotInitializedError(RuntimeError):
    pass


def _terms(text: str) -> Counter:
    return Counter(_TERMS.findall(unicodedata.normalize("NFKC", text).casefold()))


def _cosine(left: Counter, right: Counter) -> float:
    denominator = math.sqrt(sum(v * v for v in left.values()) * sum(v * v for v in right.values()))
    if denominator == 0:
        return 0.0
    return min(1.0, sum(value * right.get(key, 0) for key, value in left.items()) / denominator)


def _group_key(question):
    return question.kind, tuple(sorted(question.options.items())), question.word_limit


def _group_contract(kind: str, limit: int | None) -> tuple[str, str, dict]:
    if kind == "sentence_completion":
        return f"Complete each sentence. Write NO MORE THAN {limit} WORDS from the text.", "text", {"max_words": limit}
    if kind == "true_false_not_given":
        return "Write TRUE, FALSE or NOT GIVEN for each statement.", "classification", {}
    if kind == "matching_headings":
        return "Choose the best heading for each indicated paragraph.", "options", {}
    return "Choose ONE correct option for each question.", "options", {}


class Bank:
    def __init__(self, database_url: str):
        if not database_url or not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")
        self.database_url = database_url

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        try:
            with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=30) as connection:
                yield connection
        except psycopg.errors.UndefinedTable as error:
            raise BankNotInitializedError("UC-04 PostgreSQL schema is unavailable; run Bank.initialize() first") from error

    def initialize(self) -> None:
        with self._connection() as connection:
            apply_migrations(connection)

    @staticmethod
    def _write_trace(connection: psycopg.Connection, trace: dict) -> None:
        connection.execute(
            """INSERT INTO uc04_trace(trace_id, details) VALUES (%s, %s)
               ON CONFLICT (trace_id) DO UPDATE SET details = EXCLUDED.details,
               updated_at = CURRENT_TIMESTAMP""",
            (trace["id"], Jsonb(trace)),
        )

    def save_trace(self, trace: dict) -> None:
        if not isinstance(trace.get("id"), str) or not trace["id"].strip():
            raise ValueError("Trace requires a nonblank id")
        with self._connection() as connection:
            self._write_trace(connection, trace)

    def get_trace(self, trace_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute("SELECT details FROM uc04_trace WHERE trace_id = %s", (trace_id,)).fetchone()
            return row["details"] if row else None

    @staticmethod
    def _require_verified(request: GenerateRequest, draft: ExerciseDraft, metadata: dict, trace: dict) -> dict:
        if any(not isinstance(metadata.get(key), str) or not metadata[key].strip() for key in _METADATA_KEYS):
            raise ValueError("Verified content requires generator/solver model, prompt versions and skill_hash")
        if not isinstance(trace.get("id"), str) or not trace["id"].strip():
            raise ValueError("Verified content requires a trace id")
        if not validate_rules(draft, request).passed:
            raise ValueError("Content failed publication rule validation")
        attempts = trace.get("attempts")
        if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
            raise ValueError("Verified content requires final validation trace")
        final = attempts[-1]
        rules, solver = final.get("rules", {}), final.get("solver", {})
        if not isinstance(rules, dict) or rules.get("exercise_errors") != []:
            raise ValueError("Final trace has no passing exercise rules")
        if not isinstance(solver, dict) or solver.get("status") != "passed":
            raise ValueError("Final trace has no passing blind solver")
        rule_items, solver_items = rules.get("items"), solver.get("items")
        if not isinstance(rule_items, dict) or not isinstance(solver_items, dict):
            raise ValueError("Final trace is missing per-question validation")
        for question in draft.questions:
            result = solver_items.get(question.id)
            if rule_items.get(question.id) != [] or not isinstance(result, dict) or result.get("passed") is not True:
                raise ValueError(f"Question {question.id} has not passed both validators")
        return final

    def save_verified(self, request: GenerateRequest, draft: ExerciseDraft, metadata: dict, trace: dict) -> dict:
        final = self._require_verified(request, draft, metadata, trace)
        item_id = str(uuid4())
        saved_trace = deepcopy(trace)
        saved_trace.update(status="verified", item_id=item_id)
        saved_metadata = {key: metadata[key] for key in _METADATA_KEYS}
        body = {"title": draft.title, "text": draft.text, "metadata": saved_metadata, "trace_id": trace["id"]}
        with self._connection() as connection:
            # A database-wide application lock serializes the similarity scan and
            # insertion. Under READ COMMITTED, the scan after this lock sees the
            # previous writer's committed item even if both requests began together.
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            terms = _terms(draft.text)
            best_similarity, best_id = 0.0, ""
            for existing in connection.execute(
                """SELECT item_id, body ->> 'text' AS text FROM content_item
                   WHERE status = 'verified' AND jsonb_typeof(body -> 'text') = 'string'"""
            ):
                score = _cosine(terms, _terms(existing["text"]))
                if score > best_similarity:
                    best_similarity, best_id = score, str(existing["item_id"])
            if best_similarity > 0.9:
                raise DuplicateError(best_similarity, best_id)
            dedup = {"passed": True, "metric": "unicode_casefold_token_frequency_cosine", "threshold": 0.9,
                     "max_similarity": best_similarity, "nearest_item_id": best_id or None}
            saved_trace["attempts"][-1]["dedup"] = dedup
            connection.execute(
                """INSERT INTO content_item(item_id, skill, topic, target_band, source, model,
                   prompt_version, status, body, position) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1)""",
                (item_id, request.skill.title(), request.topic, request.target_band, "llm_generated_verified",
                 metadata["model"], metadata["prompt_version"], "verified", Jsonb(body)),
            )
            number = 0
            for group_position, (_, questions_iter) in enumerate(groupby(draft.questions, _group_key), start=1):
                questions = list(questions_iter)
                first = questions[0]
                group_id = str(uuid4())
                instructions, response_mode, response_limits = _group_contract(first.kind, first.word_limit)
                connection.execute(
                    """INSERT INTO question_group(group_id,item_id,position,question_type,instructions,
                       response_mode,options,response_limits) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (group_id, item_id, group_position, first.kind, instructions, response_mode,
                     Jsonb(first.options), Jsonb(response_limits)),
                )
                for position, question in enumerate(questions, start=1):
                    number += 1
                    question_id = str(uuid4())
                    target = {"item_id": item_id, "paragraph_id": question.paragraph_id} if question.paragraph_id else {}
                    connection.execute(
                        """INSERT INTO question(id,item_id,group_id,position,number,prompt,target,answer_key,evidence_span)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (question_id, item_id, group_id, position, number, question.prompt, Jsonb(target),
                         Jsonb({"answer": question.answer, "explanation": question.explanation}), question.evidence_span),
                    )
                    self._validation(connection, item_id, question_id, "rules", {"generator_question_id": question.id, "errors": final["rules"]["items"][question.id]})
                    self._validation(connection, item_id, question_id, "solver", {"generator_question_id": question.id, **final["solver"]["items"][question.id]})
            self._validate_positions(connection, item_id, number)
            self._validation(connection, item_id, None, "rules", {"exercise_errors": [], "retained_questions": number})
            self._validation(connection, item_id, None, "solver", {"status": "passed", "retained_questions": number})
            self._validation(connection, item_id, None, "dedup", dedup)
            self._write_trace(connection, saved_trace)
            result = self._get_item(connection, item_id)
        trace.clear()
        trace.update(saved_trace)
        return result

    @staticmethod
    def _validation(connection: psycopg.Connection, item_id: str, question_id: str | None, layer: str, details: dict) -> None:
        connection.execute(
            "INSERT INTO validation_result(id,item_id,question_id,layer,passed,details) VALUES (%s,%s,%s,%s,true,%s)",
            (str(uuid4()), item_id, question_id, layer, Jsonb(details)),
        )

    @staticmethod
    def _validate_positions(connection: psycopg.Connection, item_id: str, count: int) -> None:
        groups = connection.execute("SELECT group_id, position FROM question_group WHERE item_id=%s ORDER BY position", (item_id,)).fetchall()
        if [group["position"] for group in groups] != list(range(1, len(groups) + 1)):
            raise ValueError("Group positions must be contiguous")
        numbers = []
        for group in groups:
            questions = connection.execute("SELECT item_id, position, number FROM question WHERE group_id=%s ORDER BY position", (group["group_id"],)).fetchall()
            if [question["position"] for question in questions] != list(range(1, len(questions) + 1)):
                raise ValueError("Question positions must be contiguous within each group")
            if any(str(question["item_id"]) != item_id for question in questions):
                raise ValueError("Question must belong to its group's content item")
            numbers.extend(question["number"] for question in questions)
        if numbers != list(range(1, count + 1)) or not 8 <= count <= 13:
            raise ValueError("Question numbering must be contiguous from 1 and contain 8–13 questions")

    @staticmethod
    def _readable_item(connection: psycopg.Connection, item_id: str) -> dict | None:
        # An exclusion invalidates the published shape and its old verification.
        # Keep the entire item unavailable until a future workflow revalidates it.
        item = connection.execute(
            """SELECT ci.* FROM content_item ci WHERE ci.item_id=%s AND ci.status='verified'
               AND NOT EXISTS (SELECT 1 FROM question q WHERE q.item_id=ci.item_id AND q.excluded)""",
            (item_id,),
        ).fetchone()
        if not item:
            return None
        validation = connection.execute(
            """SELECT layer, bool_and(passed) AS passed FROM validation_result
               WHERE item_id=%s GROUP BY layer""", (item_id,)
        ).fetchall()
        outcomes = {row["layer"]: row["passed"] for row in validation}
        if any(outcomes.get(layer) is not True for layer in ("rules", "solver", "dedup")):
            return None
        return item

    @staticmethod
    def _get_item(connection: psycopg.Connection, item_id: str) -> dict | None:
        item = Bank._readable_item(connection, item_id)
        if not item:
            return None
        body = item["body"]
        result = {"id": str(item["item_id"]), "title": body["title"], "text": body["text"],
                  "skill": item["skill"].lower(), "topic": item["topic"], "target_band": item["target_band"],
                  "source": item["source"], "status": item["status"], "model": item["model"],
                  "prompt_version": item["prompt_version"], "position": item["position"],
                  "created_at": item["created_at"].isoformat(), "trace_id": body["trace_id"],
                  "validation": {"rules": True, "solver": True}, "question_groups": []}
        groups = connection.execute("SELECT * FROM question_group WHERE item_id=%s ORDER BY position", (item_id,)).fetchall()
        for group in groups:
            public_group = {key: group[key] for key in ("position", "question_type", "instructions", "response_mode", "options", "response_limits", "allow_reuse")}
            public_group["group_id"] = str(group["group_id"])
            public_group["questions"] = []
            # Explicit projection prevents future answer fields entering this path.
            for question in connection.execute("SELECT id,position,number,prompt,options,target,excluded FROM question WHERE group_id=%s ORDER BY position", (group["group_id"],)):
                if question["excluded"]:
                    return None
                public_group["questions"].append({**question, "id": str(question["id"])})
            result["question_groups"].append(public_group)
        return result

    def list_items(self, *, skill: str | None = None, target_band: float | None = None,
                   q: str = "", limit: int = 20, offset: int = 0) -> dict:
        """Return answer-free summaries and a filtered total from one snapshot."""
        filters = [
            "ci.status = 'verified'",
            "ci.skill IN ('Reading', 'Listening')",
            "NOT EXISTS (SELECT 1 FROM question q WHERE q.item_id = ci.item_id AND q.excluded)",
        ]
        params = []
        if skill is not None:
            filters.append("ci.skill = %s")
            params.append(skill.title())
        if target_band is not None:
            filters.append("ci.target_band = %s")
            params.append(target_band)
        if q:
            # strpos treats SQL wildcard characters as literal search text.
            filters.append("(strpos(lower(ci.body ->> 'title'), lower(%s)) > 0 OR strpos(lower(ci.topic), lower(%s)) > 0)")
            params.extend((q, q))
        params.extend((limit, offset))
        with self._connection() as connection:
            rows = connection.execute(
                f"""WITH eligible AS (
                    SELECT ci.item_id, ci.body ->> 'title' AS title, ci.skill, ci.topic,
                           ci.target_band, ci.source, ci.status, ci.created_at
                    FROM content_item ci
                    JOIN (
                        SELECT item_id FROM validation_result
                        WHERE layer IN ('rules', 'solver', 'dedup')
                        GROUP BY item_id
                        HAVING count(DISTINCT layer) = 3 AND bool_and(passed)
                    ) validated ON validated.item_id = ci.item_id
                    WHERE {' AND '.join(filters)}
                ), page AS (
                    SELECT eligible.*,
                           (SELECT count(*) FROM question q WHERE q.item_id = eligible.item_id) AS question_count,
                           ARRAY(SELECT DISTINCT g.question_type FROM question_group g
                                 WHERE g.item_id = eligible.item_id ORDER BY g.question_type) AS question_types
                    FROM eligible
                    ORDER BY created_at DESC, item_id DESC
                    LIMIT %s OFFSET %s
                )
                SELECT totals.total, page.*
                FROM (SELECT count(*) AS total FROM eligible) totals
                LEFT JOIN page ON true
                ORDER BY page.created_at DESC, page.item_id DESC""",
                params,
            ).fetchall()
        fields = ("title", "topic", "target_band", "source", "status", "question_count", "question_types")
        items = [
            {"id": str(row["item_id"]), "skill": row["skill"].lower(),
             "created_at": row["created_at"].isoformat(), **{key: row[key] for key in fields}}
            for row in rows if row["item_id"] is not None
        ]
        return {"items": items, "total": rows[0]["total"], "limit": limit, "offset": offset}

    def get_item(self, item_id: str) -> dict | None:
        try:
            with self._connection() as connection:
                return self._get_item(connection, item_id)
        except psycopg.errors.InvalidTextRepresentation:
            return None

    def get_answers(self, item_id: str) -> dict | None:
        try:
            with self._connection() as connection:
                if self._readable_item(connection, item_id) is None:
                    return None
                answers = []
                for question in connection.execute("SELECT id,number,answer_key,evidence_span,excluded FROM question WHERE item_id=%s ORDER BY number", (item_id,)):
                    if question["excluded"]:
                        return None
                    answers.append({"question_id": str(question["id"]), "number": question["number"],
                                    "answer_key": question["answer_key"]["answer"], "evidence_span": question["evidence_span"],
                                    "explanation": question["answer_key"]["explanation"]})
                return {"item_id": item_id, "answers": answers}
        except psycopg.errors.InvalidTextRepresentation:
            return None

    def close(self) -> None:
        """Connections are scoped to each operation; there is no persistent pool."""
