import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
import time

import av
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, Groq, RateLimitError
import numpy as np
from starlette.concurrency import run_in_threadpool

from ielts_agent.agents.speaking.analysis import analyze, tokens
from ielts_agent.agents.speaking.questions import CUE_CARDS, PART2_SPEAKING_SECONDS, PREPARATION_SECONDS, QUESTIONS, question_bank
from ielts_agent.agents.speaking.vad import detect_activity
from ielts_agent.agents.speaking.pronunciation import assess_audio, capabilities as pronunciation_capabilities
from ielts_agent.agents.speaking.grading import load_descriptors
from ielts_agent.agents.speaking.rag import search as rubric_search
from ielts_agent.agents.speaking.test_whisper import groq_stt_model, transcribe_groq
from ielts_agent.agents.speaking.exam_api import install_exam_routes, stamped_page
from ielts_agent.agents.speaking.database import SCHEMA_VERSION, TABLE_MODELS, practice_export
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[3]
# Bản thu mẫu là giọng thật nên không nằm trong repo; trỏ bằng biến môi trường.
SAMPLES = Path(os.environ.get("SPEAKING_SAMPLES_DIR") or ROOT / "audio-sample")
load_dotenv(ROOT / ".env", override=False)
MAX_BYTES = 24 * 1024 * 1024
MAX_SECONDS = 180
SUFFIXES = {".wav", ".m4a", ".mp4", ".webm", ".mp3", ".ogg", ".flac"}
app = FastAPI(title="Speaking Agent — Practice & Mock Exam", version="0.5.0")


class Revalidated(StaticFiles):
    """Serve the UI with no-cache so an edited page or script is never a stale
    browser copy. The files are local and tiny; the ETag still saves the body."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


PAGE_HEADERS = {"Cache-Control": "no-cache"}
app.mount("/static", Revalidated(directory=PKG / "web"), name="static")
slots = asyncio.Semaphore(2)


class PracticeExport(BaseModel):
    session_id: UUID
    learner_id: UUID | None = None
    created_at: datetime
    answers: list[dict] = Field(min_length=1, max_length=200)


@app.get("/api/speaking/database-schema")
def database_schema():
    return {"schema_version": SCHEMA_VERSION,
            "tables": {name: model.model_json_schema() for name, model in TABLE_MODELS.items()}}


@app.post("/api/speaking/export")
def export_practice(body: PracticeExport):
    try:
        return practice_export(body.model_dump(mode="json", exclude_none=True))
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(422, "Dữ liệu luyện Speaking không đúng contract xuất database.") from error


@app.middleware("http")
async def limit_declared_upload(request: Request, call_next):
    if request.url.path == "/api/transcribe" or request.url.path.endswith("/voice"):
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_BYTES + 65536):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "File quá lớn. Giới hạn audio là 24 MB."}, status_code=413)
    return await call_next(request)


@app.get("/")
def index():
    return stamped_page(PKG / "web" / "index.html")


@app.get("/api/health")
def health():
    load_dotenv(ROOT / ".env", override=False)
    return {"status": "ok", "groq_configured": bool(os.environ.get("GROQ_API_KEY")),
            "model": groq_stt_model(), "max_audio_seconds": MAX_SECONDS,
            "transcription_policy": "original_language_context_v2", "database_schema_version": SCHEMA_VERSION,
            "pronunciation": pronunciation_capabilities()}


class RubricQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    criterion: str = Field(pattern="^(FC|LR|GRA|PR)$")
    band: int | None = Field(default=None, ge=0, le=9)
    top_k: int = Field(default=4, ge=1, le=10)


@app.post("/api/speaking/rubric/search")
def search_rubric(body: RubricQuery):
    try:
        corpus = load_descriptors()
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "Kho rubric chưa sẵn sàng; chạy lệnh ingest trước.") from None
    hits = rubric_search(corpus, body.query, criterion=body.criterion, band=body.band, top_k=body.top_k)
    return {"status": "ok" if hits else "no_evidence", "method": "bm25_lsa_rrf_feature_rerank", "chunks": hits}


@app.get("/api/questions")
def questions():
    return {"topics": question_bank()}


@app.get("/api/cue-cards")
def cue_cards():
    return {"cards": CUE_CARDS, "preparation_seconds": PREPARATION_SECONDS,
            "speaking_seconds": PART2_SPEAKING_SECONDS}


def audio_info(content, max_seconds=MAX_SECONDS):
    count, square_sum, chunks = 0, 0.0, []
    try:
        with av.open(BytesIO(content)) as container:
            if not container.streams.audio:
                raise ValueError("No audio stream")
            resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    samples = converted.to_ndarray().reshape(-1)
                    count += len(samples)
                    chunks.append(samples.copy())
                    square_sum += float(np.dot(samples, samples))
                    if count / 16000 > max_seconds:
                        raise HTTPException(413, f"Audio dài quá {int(max_seconds)} giây. Hãy gửi một câu trả lời ngắn hơn.")
            for converted in resampler.resample(None):
                samples = converted.to_ndarray().reshape(-1)
                count += len(samples)
                chunks.append(samples.copy())
                square_sum += float(np.dot(samples, samples))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Không đọc được audio. Hãy chọn file ghi âm WAV, M4A, MP3 hoặc WebM hợp lệ.") from None
    seconds = count / 16000
    if seconds > max_seconds:
        raise HTTPException(413, f"Audio dài quá {int(max_seconds)} giây.")
    if seconds < 0.5:
        raise HTTPException(422, "Audio quá ngắn. Hãy thu ít nhất nửa giây.")
    if (square_sum / count) ** 0.5 < 0.00001:
        raise HTTPException(422, "Audio gần như im lặng. Hãy kiểm tra mic và thu lại.")
    return seconds, np.concatenate(chunks)


def safe_activity(samples):
    try:
        return detect_activity(samples)
    except Exception:
        return {"status": "unavailable", "source": "silero_vad_v6", "words_per_minute": None}


def process_audio(content, suffix, keep_fillers, question_id, preparation_seconds=0, notes="", question=None, vocabulary="", pronunciation_consent=False):
    pipeline_started = time.perf_counter()
    question = question or QUESTIONS[question_id]
    part = question.get("part", 1)
    # Allow the final MediaRecorder chunk to end just after the 120-second stop.
    seconds, samples = audio_info(content, PART2_SPEAKING_SECONDS + 0.5 if part == 2 else MAX_SECONDS)
    load_dotenv(ROOT / ".env", override=False)
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(503, "Backend chưa có GROQ_API_KEY. Cấu hình key rồi khởi động lại server.")
    with tempfile.TemporaryDirectory(prefix="speaking-") as folder:
        path = Path(folder) / f"answer{suffix}"
        path.write_bytes(content)
        started = time.perf_counter()
        try:
            with Groq(timeout=45, max_retries=1) as client:
                transcript, words = transcribe_groq(path, keep_fillers, client=client, vocabulary=vocabulary)
        except AuthenticationError:
            raise HTTPException(503, "Groq API key không hợp lệ. Hãy kiểm tra cấu hình backend.") from None
        except RateLimitError:
            raise HTTPException(429, "Groq đang giới hạn số lượt gọi. Hãy đợi rồi gửi lại.") from None
        except (APIConnectionError, APITimeoutError):
            raise HTTPException(504, "Không kết nối được Groq hoặc yêu cầu đã quá thời gian. Audio vẫn còn để gửi lại.") from None
        except APIStatusError:
            raise HTTPException(502, "Groq chưa xử lý được audio này. Hãy thử lại hoặc thu một bản mới.") from None
        except (KeyError, TypeError, ValueError):
            raise HTTPException(502, "Groq trả về dữ liệu chưa hợp lệ. Hãy thử lại hoặc thu một bản mới.") from None
    stt_seconds = round(time.perf_counter() - started, 3)
    activity = safe_activity(samples)
    pronunciation = assess_audio(samples, consent=pronunciation_consent)
    if pronunciation["status"] == "assessed":
        try:
            pronunciation["rubric_context"] = rubric_search(load_descriptors(), "pronunciation stress rhythm intonation intelligibility sounds", criterion="PR", top_k=4)
        except (OSError, ValueError, TypeError):
            pronunciation["rubric_context"] = []
    result = {"schema_version": "1.2", "source": "live", "backend": "groq", "part": part,
            "model": groq_stt_model(), "question": question,
            "keep_fillers": keep_fillers, "audio_seconds": round(seconds, 3), "audio_sample_count": len(samples),
            "processing_seconds": stt_seconds,
            "transcript": transcript, "words": words,
            "stt_confidence": None, "confidence_source": "not_available",
            "transcription_policy": "original_language_context_v2", "vocabulary": vocabulary,
            "pronunciation": pronunciation,
            **analyze(transcript, words, seconds, activity)}
    if vocabulary.strip():
        # A spelling hint is not proof that the learner said the name. Warn if
        # any comma/semicolon/newline-separated hint is absent; never replace
        # recognized words or manufacture matching timestamps/evidence.
        normalized = " ".join(tokens(transcript))
        hints = [hint.strip() for hint in re.split(r"[,;\n]+", vocabulary) if hint.strip()]
        unmatched = [hint for hint in hints if f" {' '.join(tokens(hint))} " not in f" {normalized} "]
        if unmatched:
            result["quality"]["status"] = "needs_review"
            result["quality"]["issues"].append({
                "code": "vocabulary_needs_review", "severity": "warning", "word_indices": [],
                "message": "Tên riêng gợi ý chưa xuất hiện nguyên văn trong transcript. Hãy nghe lại audio để xác nhận; hệ thống không tự thay từ.",
            })
    result["pipeline_processing_seconds"] = round(time.perf_counter() - pipeline_started, 3)
    if part == 2:
        result["preparation"] = {"seconds": preparation_seconds, "notes": notes,
                                 "limit_seconds": PREPARATION_SECONDS}
        result["speaking_limit_seconds"] = PART2_SPEAKING_SECONDS
    return result


install_exam_routes(app, PKG, process_audio, SUFFIXES, MAX_BYTES, slots, audio_info)


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), question_id: str = Form(...), keep_fillers: bool = Form(False),
                     preparation_seconds: float = Form(0, ge=0, le=PREPARATION_SECONDS),
                     notes: str = Form("", max_length=2000), vocabulary: str = Form("", max_length=400),
                     pronunciation_consent: bool = Form(False)):
    try:
        if question_id not in QUESTIONS:
            raise HTTPException(422, "Câu hỏi không tồn tại.")
        suffix = Path(audio.filename or "").suffix.lower()
        if suffix not in SUFFIXES:
            raise HTTPException(415, "Định dạng audio chưa được hỗ trợ.")
        chunks, size = [], 0
        while chunk := await audio.read(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "File quá lớn. Giới hạn audio là 24 MB.")
            chunks.append(chunk)
        if not size:
            raise HTTPException(422, "File audio trống.")
        async with slots:
            return await run_in_threadpool(process_audio, b"".join(chunks), suffix, keep_fillers,
                                          question_id, preparation_seconds, notes, None, vocabulary, pronunciation_consent)
    finally:
        await audio.close()


def benchmark_results():
    path = ROOT / "docs" / "speaking" / "stt-results" / "groq" / "results.json"
    return json.loads(path.read_text())["results"] if path.exists() else []


@app.get("/api/samples")
def samples():
    return {"samples": sorted({r["sample"] for r in benchmark_results() if r["status"] == "ok"})}


@app.get("/api/samples/{sample}")
def sample_result(sample: str, keep_fillers: bool = False):
    result = next((r for r in benchmark_results() if r["sample"] == sample
                   and r["keep_fillers"] == keep_fillers and r["status"] == "ok"), None)
    if result is None:
        raise HTTPException(404, "Không có kết quả mẫu này.")
    activity = {"status": "unavailable", "source": "silero_vad_v6", "words_per_minute": None}
    path = SAMPLES / f"{sample}.m4a"
    if re_safe_sample(sample) and path.exists():
        try:
            _, decoded = audio_info(path.read_bytes())
            activity = safe_activity(decoded)
        except HTTPException:
            pass
    return {"schema_version": "1.2", "source": "benchmark", "sample": sample,
            "backend": "groq", "model": "whisper-large-v3-turbo", "question": None,
            **{key: result[key] for key in ["transcript", "words", "audio_seconds", "processing_seconds", "keep_fillers"]},
            **analyze(result["transcript"], result["words"], result["audio_seconds"], activity)}


@app.get("/api/samples/{sample}/audio")
def sample_audio(sample: str):
    available = {r["sample"] for r in benchmark_results()}
    if sample not in available or not re_safe_sample(sample):
        raise HTTPException(404, "Không có audio mẫu này.")
    path = SAMPLES / f"{sample}.m4a"
    if not path.exists():
        raise HTTPException(404, "Không có audio mẫu này.")
    return FileResponse(path, media_type="audio/mp4")


def re_safe_sample(sample):
    import re
    return bool(re.fullmatch(r"sample-\d{2}", sample))
