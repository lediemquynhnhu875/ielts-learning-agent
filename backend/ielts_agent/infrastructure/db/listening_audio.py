"""Version-bound Listening WAV artifacts and their private verification reports.

This repository never decides whether audio is deliverable: callers must compare
the current source/configuration hashes and require a verified stored outcome.
The full artifact, including answer diagnostics, is internal and must not be
serialized directly to learners.
"""

import hashlib
import json
import re
from uuid import uuid4

from psycopg.types.json import Jsonb

from .bank import Bank


MAX_AUDIO_BYTES = 29_000_000
_HASH = re.compile(r"[0-9a-f]{64}")


def _hash_json(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         default=str, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_hash(exercise: dict, answers: dict) -> str:
    """Bind audio to the exact public source and its private fixed answer key."""
    return _hash_json({"exercise": exercise, "answers": answers})


def config_hash(config: dict) -> str:
    """Hash caller-owned voice/locale/pipeline settings without credentials."""
    return _hash_json(config)


def _record(row: dict, *, include_audio: bool) -> dict:
    result = dict(row)
    result["audio_id"] = str(result["audio_id"])
    result["item_id"] = str(result["item_id"])
    if include_audio:
        result["audio"] = bytes(result["audio"])
    else:
        result.pop("audio", None)
    for key in ("created_at", "updated_at"):
        value = result.get(key)
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    return result


class ListeningAudioStore:
    def __init__(self, bank: Bank):
        self.bank = bank

    def load_source(self, item_id: str) -> tuple[dict, dict] | None:
        with self.bank._connection() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            exercise = Bank._get_item(connection, item_id)
            if exercise is None or exercise.get("skill") != "listening":
                return None
            answers = []
            for row in connection.execute(
                """SELECT id,number,answer_key,evidence_span FROM question
                   WHERE item_id=%s ORDER BY number""", (item_id,)
            ):
                answers.append({"question_id": str(row["id"]), "number": row["number"],
                                "answer_key": row["answer_key"]["answer"],
                                "explanation": row["answer_key"]["explanation"],
                                "evidence_span": row["evidence_span"]})
            return exercise, {"item_id": item_id, "answers": answers}

    def save(self, item_id: str, source_hash: str, config_hash: str, audio: bytes,
             manifest: dict, verification: dict, status: str) -> dict:
        if status not in {"blocked", "verified"}:
            raise ValueError("Audio status must be blocked or verified")
        if not isinstance(audio, bytes) or not 0 < len(audio) <= MAX_AUDIO_BYTES:
            raise ValueError("Audio must contain at most 29000000 bytes")
        if not all(isinstance(value, str) and _HASH.fullmatch(value) for value in (source_hash, config_hash)):
            raise ValueError("Audio bindings must be SHA-256 hex digests")
        if not isinstance(manifest, dict) or not isinstance(verification, dict):
            raise ValueError("Audio manifest and verification must be objects")
        audio_hash = hashlib.sha256(audio).hexdigest()
        with self.bank._connection() as connection:
            row = connection.execute(
                """INSERT INTO listening_audio
                   (audio_id,item_id,status,source_hash,config_hash,audio_sha256,audio,manifest,verification)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (item_id) DO UPDATE SET
                       status=EXCLUDED.status,source_hash=EXCLUDED.source_hash,
                       config_hash=EXCLUDED.config_hash,audio_sha256=EXCLUDED.audio_sha256,
                       audio=EXCLUDED.audio,manifest=EXCLUDED.manifest,
                       verification=EXCLUDED.verification,updated_at=CURRENT_TIMESTAMP
                   RETURNING audio_id,item_id,status,source_hash,config_hash,audio_sha256,
                             manifest,verification,created_at,updated_at""",
                (str(uuid4()), item_id, status, source_hash, config_hash, audio_hash,
                 audio, Jsonb(manifest), Jsonb(verification)),
            ).fetchone()
            return _record(row, include_audio=False)

    def get(self, item_id: str) -> dict | None:
        with self.bank._connection() as connection:
            row = connection.execute("SELECT * FROM listening_audio WHERE item_id=%s", (item_id,)).fetchone()
            return _record(row, include_audio=True) if row is not None else None
