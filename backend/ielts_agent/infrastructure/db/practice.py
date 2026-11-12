"""Transactional PostgreSQL storage for standalone Reading/Listening practice.

Public content and private keys are captured under one database snapshot. Draft
updates and submission share an attempt row lock so independent API instances
cannot race a late save against a completed result.
"""

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.types.json import Jsonb

from .bank import Bank


class PostgresAttemptStore:
    def __init__(self, bank: Bank):
        self.bank = bank

    def load_source(self, item_id: str) -> tuple[dict, dict] | None:
        with self.bank._connection() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            exercise = Bank._get_item(connection, item_id)
            if exercise is None:
                return None
            answers = []
            for row in connection.execute(
                """SELECT id,number,answer_key,evidence_span FROM question
                   WHERE item_id=%s ORDER BY number""", (item_id,)
            ):
                answers.append({
                    "question_id": str(row["id"]), "number": row["number"],
                    "answer_key": row["answer_key"]["answer"],
                    "explanation": row["answer_key"]["explanation"],
                    "evidence_span": row["evidence_span"],
                })
            return exercise, {"item_id": item_id, "answers": answers}

    def create(self, record: dict) -> None:
        with self.bank._connection() as connection:
            connection.execute(
                """INSERT INTO practice_attempt
                   (attempt_id,item_id,skill,status,token_hash,exercise_snapshot,
                    answer_key_snapshot,started_at,submitted_at,raw_score,result)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (record["attempt_id"], record["item_id"], record["skill"],
                 record["status"], record["token_hash"],
                 Jsonb(record["exercise_snapshot"]), Jsonb(record["answer_key_snapshot"]),
                 record["started_at"], record["submitted_at"], record["raw_score"],
                 Jsonb(record["result"]) if record["result"] is not None else None),
            )
            self._save_answers(connection, record)

    @staticmethod
    def _read(connection: psycopg.Connection, attempt_id: str, *, lock: bool = False) -> dict | None:
        query = "SELECT * FROM practice_attempt WHERE attempt_id=%s"
        if lock:
            query += " FOR UPDATE"
        row = connection.execute(query, (attempt_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["attempt_id"] = str(record["attempt_id"])
        record["item_id"] = str(record["item_id"])
        record["answers"] = {
            str(answer["question_id"]): answer["response"]
            for answer in connection.execute(
                "SELECT question_id,response FROM practice_answer WHERE attempt_id=%s",
                (attempt_id,),
            )
        }
        return record

    def get(self, attempt_id: str) -> dict | None:
        with self.bank._connection() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return self._read(connection, attempt_id)

    @staticmethod
    def _save_answers(connection: psycopg.Connection, record: dict) -> None:
        responses = dict(record["answers"])
        correct = {}
        if record["result"] is not None:
            for question in record["result"]["questions"]:
                correct[question["question_id"]] = question["is_correct"]
                responses.setdefault(question["question_id"], "")
        for question_id, response in responses.items():
            connection.execute(
                """INSERT INTO practice_answer(attempt_id,item_id,question_id,response,is_correct)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (attempt_id,question_id) DO UPDATE
                   SET response=EXCLUDED.response,is_correct=EXCLUDED.is_correct""",
                (record["attempt_id"], record["item_id"], question_id,
                 response, correct.get(question_id)),
            )

    @contextmanager
    def edit(self, attempt_id: str) -> Iterator[dict | None]:
        with self.bank._connection() as connection:
            record = self._read(connection, attempt_id, lock=True)
            was_submitted = record is not None and record["status"] == "submitted"
            yield record
            if record is None or was_submitted:
                return
            connection.execute(
                """UPDATE practice_attempt SET status=%s,submitted_at=%s,raw_score=%s,result=%s
                   WHERE attempt_id=%s""",
                (record["status"], record["submitted_at"], record["raw_score"],
                 Jsonb(record["result"]) if record["result"] is not None else None,
                 attempt_id),
            )
            self._save_answers(connection, record)
