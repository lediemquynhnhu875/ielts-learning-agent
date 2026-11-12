"""Hàng đợi gen_job: idempotent, có checkpoint, resume và hạn mức token.

Thiết kế theo mục 8.4 của generate-format.docx. Mọi lệnh gọi LLM đi qua đây để
raw output không bao giờ bị ghi đè và chạy lại không tốn quota cho job đã ok.
Groq đo riêng từng model: 8.000 token/phút và 200.000 token/ngày, và một request
tính prompt_tokens + max_completion_tokens, nên bộ đếm phải tính theo trần đó.
"""

import hashlib
import json
import os
import random
import re
import sqlite3
import time
from datetime import datetime, timezone

import prompts

SCHEMA = """
CREATE TABLE IF NOT EXISTS gen_job (
    job_id         TEXT PRIMARY KEY,
    prompt_id      TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    input_hash     TEXT NOT NULL,
    input_json     TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN
                       ('pending','running','ok','failed','rejected')),
    attempts       INTEGER NOT NULL DEFAULT 0,
    output_raw     TEXT,
    output_json    TEXT,
    error          TEXT,
    tokens_in      INTEGER,
    tokens_out     INTEGER,
    started_at     TEXT,
    finished_at    TEXT
);
CREATE TABLE IF NOT EXISTS token_spend (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    model        TEXT NOT NULL,
    day          TEXT NOT NULL,
    at           REAL NOT NULL,
    reserved     INTEGER NOT NULL,
    out_reserved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS token_spend_model_day ON token_spend (model, day);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def job_id(prompt_version, payload, seed):
    """Băm version + input + seed: chạy lại cùng tham số cho đúng một job."""
    blob = json.dumps({"v": prompt_version, "in": payload, "seed": seed},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def enqueue(db, prompt_id, payload, seed, model):
    version = prompts.VERSIONS[prompt_id]
    jid = job_id(version, payload, seed)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    db.execute(
        "INSERT OR IGNORE INTO gen_job (job_id, prompt_id, prompt_version, model,"
        " input_hash, input_json, status) VALUES (?,?,?,?,?,?, 'pending')",
        (jid, prompt_id, version, model,
         hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16], blob))
    db.commit()
    return jid


def pending(db, prompt_id=None):
    sql = "SELECT * FROM gen_job WHERE status IN ('pending','running','failed')"
    args = ()
    if prompt_id:
        sql += " AND prompt_id = ?"
        args = (prompt_id,)
    return db.execute(sql + " ORDER BY rowid", args).fetchall()


def done(db, prompt_id=None):
    sql = "SELECT * FROM gen_job WHERE status = 'ok'"
    args = ()
    if prompt_id:
        sql += " AND prompt_id = ?"
        args = (prompt_id,)
    return db.execute(sql + " ORDER BY rowid", args).fetchall()


class Budget:
    """Ba hạn mức của Groq free tier, đo riêng theo từng model.

      * TPM  — tổng token mỗi phút (8.000)
      * OTPM — token ĐẦU RA mỗi phút (1.000); đây là hạn mức chặt nhất và không
               có trong .env, phát hiện qua 429 "on output tokens per minute"
      * TPD  — tổng token mỗi ngày (200.000)

    Reserve trước khi gọi vì Groq tính cả max_completion_tokens; có usage thật
    thì chỉnh lại để cửa sổ phút hồi phục chứ không giữ phí quota.
    """

    def __init__(self, db, per_minute, per_day, output_per_minute=1000):
        self.db = db
        self.per_minute = per_minute
        self.per_day = per_day
        self.output_per_minute = output_per_minute

    def _spent(self, model):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cutoff = time.time() - 60
        row = self.db.execute(
            "SELECT COALESCE(SUM(reserved),0) AS d,"
            " COALESCE(SUM(CASE WHEN at > ? THEN reserved ELSE 0 END),0) AS m,"
            " COALESCE(SUM(CASE WHEN at > ? THEN out_reserved ELSE 0 END),0) AS o"
            " FROM token_spend WHERE model = ? AND day = ?",
            (cutoff, cutoff, model, day)).fetchone()
        return row["m"], row["o"], row["d"]

    def headroom(self, model, need, need_out):
        """Chờ bao nhiêu giây nữa thì model này gọi được. 0 là gọi được ngay.

        Tính theo thời điểm từng reservation hết hiệu lực, không theo mốc phút
        đồng hồ: một reservation đặt ở giây thứ 30 chỉ rời cửa sổ 60 giây sau
        đó, nên chờ tới đầu phút kế tiếp vẫn còn bị chặn và phải ngủ thêm một
        phút nữa.
        """
        now_ts = time.time()
        rows = self.db.execute(
            "SELECT at, reserved, out_reserved FROM token_spend"
            " WHERE model = ? AND at > ? ORDER BY at",
            (model, now_ts - 60)).fetchall()
        total = sum(r["reserved"] for r in rows)
        total_out = sum(r["out_reserved"] for r in rows)
        if total + need <= self.per_minute and \
                total_out + need_out <= self.output_per_minute:
            return 0.0
        if need > self.per_minute or need_out > self.output_per_minute:
            raise ValueError(
                f"request {need} token ({need_out} đầu ra) vượt hạn mức phút"
                f" {self.per_minute}/{self.output_per_minute}")
        expires = 60.0
        for row in rows:
            total -= row["reserved"]
            total_out -= row["out_reserved"]
            expires = row["at"] + 60 - now_ts
            if total + need <= self.per_minute and \
                    total_out + need_out <= self.output_per_minute:
                break
        return max(0.0, expires + 0.5)

    def check_day(self, model, need):
        _, _, day_total = self._spent(model)
        if day_total + need > self.per_day:
            raise RuntimeError(
                f"{model} đã dùng {day_total}/{self.per_day} token hôm nay;"
                " dừng lại, mai chạy tiếp (job đã ok sẽ được bỏ qua)")

    def wait_for(self, model, need, need_out, log=print):
        if need > self.per_minute or need_out > self.output_per_minute:
            raise ValueError(
                f"request {need} token ({need_out} đầu ra) vượt hạn mức phút"
                f" {self.per_minute}/{self.output_per_minute}")
        while True:
            self.check_day(model, need)
            sleep = self.headroom(model, need, need_out)
            if not sleep:
                self.db.execute(
                    "INSERT INTO token_spend (model, day, at, reserved, out_reserved)"
                    " VALUES (?,?,?,?,?)",
                    (model, datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                     time.time(), need, need_out))
                self.db.commit()
                return self.db.execute(
                    "SELECT last_insert_rowid() AS id").fetchone()["id"]
            minute, out_minute, _ = self._spent(model)
            log(f"  chờ {sleep:.0f}s: {model} giữ {minute}/{self.per_minute} TPM,"
                f" {out_minute}/{self.output_per_minute} OTPM")
            time.sleep(sleep)

    def settle(self, row_id, actual, actual_out):
        self.db.execute(
            "UPDATE token_spend SET reserved = ?, out_reserved = ? WHERE id = ?",
            (actual, actual_out, row_id))
        self.db.commit()

    def report(self, model):
        minute, out_minute, day_total = self._spent(model)
        return {"model": model, "minute": minute, "out_minute": out_minute,
                "day": day_total, "day_limit": self.per_day}


FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_json(raw):
    """Model free hay bọc JSON trong fence hoặc thêm lời dẫn. Gỡ rồi mới parse."""
    text = FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("đầu ra không chứa JSON")
    for end in range(len(text), start, -1):
        chunk = text[start:end]
        if chunk[-1] not in "}]":
            continue
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    raise ValueError("không parse được JSON sau khi gỡ fence")


def client():
    from groq import Groq
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("thiếu GROQ_API_KEY; nạp .env trước khi chạy")
    return Groq(api_key=key)


# Model họ gpt-oss tính reasoning vào completion_tokens. Để mặc định, cả trần
# token bị reasoning ăn hết và JSON trả về bị cắt (400 json_validate_failed).
REASONING_MODELS = ("openai/gpt-oss",)


def model_kwargs(model):
    if model.startswith(REASONING_MODELS):
        return {"reasoning_effort": "low"}
    return {}


def pick_model(budget, candidates, need, need_out, strikes=None):
    """Chọn model gọi được ngay, trừ những model vừa lỗi trong cùng job này.

    Mỗi model có cửa sổ OTPM riêng, nên luân phiên giữa các generator cho thông
    lượng gấp đôi. `strikes` đếm lỗi API theo model: không có nó, một model lỗi
    liên tục nhưng không tốn quota sẽ được chọn lại mãi.
    """
    strikes = strikes or {}
    waits = []
    for order, model in enumerate(candidates):
        try:
            budget.check_day(model, need)
        except RuntimeError:
            continue
        # Thế hoà phá bằng thứ tự ưu tiên trong `candidates`, không bằng tên
        # model: xếp theo tên thì model đứng đầu bảng chữ cái luôn thắng và
        # model còn lại không bao giờ được dùng.
        waits.append((strikes.get(model, 0),
                      budget.headroom(model, need, need_out), order, model))
    if not waits:
        raise RuntimeError("mọi model đã hết hạn mức ngày")
    waits.sort()
    return waits[0][3]


def run(db, job, budget, validate, groq, models=None, log=print):
    """Một job: repair loop cho JSON lỗi, feedback loop cho validator lỗi.

    `models` là danh sách model được phép dùng cho job này, xếp theo thứ tự ưu
    tiên. Mỗi vòng chọn lại model rảnh nhất, nên hết attempt là đã thử cả danh
    sách chứ không chỉ một model.
    """
    if job["status"] == "ok":
        return json.loads(job["output_json"])

    payload = json.loads(job["input_json"])
    prompt_id = job["prompt_id"]
    candidates = models or [job["model"]]
    max_attempts = 4
    feedback = []
    db.execute("UPDATE gen_job SET status='running', started_at=? WHERE job_id=?",
               (now(), job["job_id"]))
    db.commit()

    cap = prompts.MAX_TOKENS[prompt_id]
    last_error = None
    strikes = {}
    for attempt in range(max_attempts):
        body = prompts.render(prompt_id, payload)
        if feedback:
            body += ("\n\nYour previous output was rejected. Fix exactly these"
                     " problems and output the full JSON again:\n- "
                     + "\n- ".join(feedback))
        need_in = (len(prompts.P0) + len(body)) // 3
        model = pick_model(budget, candidates, need_in + cap, cap, strikes)
        reservation = budget.wait_for(model, need_in + cap, cap, log=log)
        try:
            reply = groq.chat.completions.create(
                model=model,
                temperature=prompts.TEMPERATURES[prompt_id],
                top_p=0.95 if prompts.TEMPERATURES[prompt_id] >= 0.7 else 1.0,
                max_completion_tokens=cap,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": prompts.P0},
                          {"role": "user", "content": body}],
                **model_kwargs(model))
        except Exception as exc:                      # 429, 5xx, 413, 400
            last_error = f"{type(exc).__name__}: {exc}"
            strikes[model] = strikes.get(model, 0) + 1
            # Giữ nguyên phần đã đặt khi bị OTPM chặn: cửa sổ phút đã tính rồi.
            budget.settle(reservation, 0, cap if "OTPM" in last_error else 0)
            wait = min(45, 2 ** attempt * 5) + random.uniform(0, 3)
            log(f"  lỗi gọi API trên {model} ({last_error[:80]}), chờ {wait:.0f}s")
            time.sleep(wait)
            continue

        usage = reply.usage
        budget.settle(reservation, usage.prompt_tokens + usage.completion_tokens,
                      usage.completion_tokens)
        raw = reply.choices[0].message.content or ""
        db.execute(
            "UPDATE gen_job SET attempts = attempts + 1, model = ?, output_raw = ?,"
            " tokens_in = ?, tokens_out = ? WHERE job_id = ?",
            (model, raw, usage.prompt_tokens, usage.completion_tokens,
             job["job_id"]))
        db.commit()

        try:
            data = parse_json(raw)
        except ValueError as exc:
            last_error = f"json: {exc}"
            feedback = ["Output valid JSON only, with no prose and no code fences."]
            log(f"  {last_error}")
            continue

        errors = validate(prompt_id, data, payload)
        if not errors:
            db.execute(
                "UPDATE gen_job SET status='ok', output_json=?, error=NULL,"
                " finished_at=? WHERE job_id=?",
                (json.dumps(data, ensure_ascii=False), now(), job["job_id"]))
            db.commit()
            return data
        last_error = "; ".join(errors)
        feedback = errors
        log(f"  validator chặn ({model}): {last_error[:130]}")

    db.execute("UPDATE gen_job SET status='failed', error=?, finished_at=? WHERE job_id=?",
               (last_error, now(), job["job_id"]))
    db.commit()
    return None


def P0_AND(body):
    return prompts.P0 + body
