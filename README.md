# IELTS Learning Agent

Hệ thống đa agent hỗ trợ luyện thi IELTS cả bốn kỹ năng: sinh đề Reading/Listening có kiểm định độc lập, thi thử Speaking với giám khảo AI, chấm Writing theo band descriptors, cùng giao diện web cho người học và quản trị viên.

> Đồ án môn **SE373 – Agentic Engineering** (UIT), đề tài 06. Repo cá nhân, phát triển từ repo nhóm [`se373agenticengineering/nhom-05`](https://github.com/se373agenticengineering/nhom-05). Tôi phụ trách chính **agent Speaking**.

## Bài toán

Người tự học IELTS thường thiếu hai thứ: đề luyện chất lượng ổn định và phản hồi chấm điểm đáng tin cho hai kỹ năng nói/viết. Dự án dùng LLM để giải quyết cả hai, nhưng không tin vào một lần gọi model duy nhất:

- **Đề sinh ra phải được kiểm chứng.** Một agent khác tự giải đề mà không thấy đáp án. Đề chỉ được lưu khi lời giải khớp key và qua kiểm duyệt nội dung.
- **Điểm chấm phải có đối chứng.** Hai giám khảo AI chấm độc lập, dựa trên band descriptors chính thức. Khi hai điểm lệch nhau từ 1 band trở lên, bài được chuyển cho giáo viên duyệt.

## Chức năng chính

| Kỹ năng | Chức năng | Trạng thái |
|---|---|---|
| Reading / Listening (UC-04) | Sinh bài luyện bằng pipeline generator → blind solver → safety; validator quy tắc bằng code; lưu ngân hàng đề PostgreSQL | Đã có |
| Listening | Sinh audio nhiều giọng (Azure Speech), tách lượt hội thoại, kiểm tra audio bằng STT | Đã có |
| Speaking | Thi thử đủ 3 part, ghi âm trên trình duyệt, STT, hai giám khảo độc lập, chấm lại, tải audio | Đã có |
| Writing | Prototype chấm bài theo rubric | Prototype |
| Frontend | Danh sách bài, luyện tập và mock test Reading/Listening, trang quản trị | Đang phát triển |

### Agent Speaking

Đây là phần tôi phụ trách. Mã nguồn nằm ở [`backend/ielts_agent/agents/speaking/`](backend/ielts_agent/agents/speaking/), tài liệu chi tiết ở [`docs/speaking/`](docs/speaking/).

- **Phiên thi có trạng thái.** Ba part theo đúng format IELTS. Phiên được lưu checkpoint SQLite nên có thể tạm dừng và tiếp tục.
- **Speech-to-text.** Dùng Groq Whisper, có VAD để cắt khoảng lặng; có bộ benchmark so sánh nhiều cấu hình STT.
- **RAG trên band descriptors.** Truy hồi lai BM25 + LSA, hợp nhất bằng Reciprocal Rank Fusion.
- **Vòng lặp giám khảo (grader agent).** Giám khảo không trả điểm ngay mà chạy một vòng lặp hành động JSON với hai công cụ: `retrieve_descriptors` (tra descriptor) và `get_transcript_evidence` (lấy dẫn chứng trong transcript). Vòng lặp có giới hạn số bước và số lần gọi công cụ.
- **Hai giám khảo độc lập (A/B), có leo thang.** Điểm lệch ≥ 1 band thì bài được chuyển giáo viên duyệt.
- **Chấm lại có lịch sử.** Mỗi lần chấm được lưu vào `grading_history`; người học có thể chọn giữ hoặc không giữ audio.
- **Bộ sinh dữ liệu giả lập** ([`synth/`](backend/ielts_agent/agents/speaking/synth/)). Sinh ngân hàng câu hỏi, phiên thi và bài nói mẫu theo từng band, kèm bộ gold label để đánh giá giám khảo.

## Kiến trúc

```text
┌──────────────────────┐      /api/backend/*      ┌─────────────────────────────┐
│ Frontend (Next.js 16)│ ───────────────────────▶ │ Backend UC-04 (FastAPI)     │ :8000
│ :3000                │                          │  generator · solver · safety│──▶ PostgreSQL 17 :55432
└──────────────────────┘                          └─────────────────────────────┘
           │                                      ┌─────────────────────────────┐
           └────────────────────────────────────▶ │ Speaking agent (FastAPI)    │ :8010
                                                  │  STT · RAG · grader A/B     │──▶ SQLite checkpoint
                                                  └─────────────────────────────┘
```

| Thư mục | Nội dung |
|---|---|
| `backend/ielts_agent/api` | Khởi tạo FastAPI và các route mỏng |
| `backend/ielts_agent/agents/uc04` | Agent sinh và kiểm định đề Reading/Listening |
| `backend/ielts_agent/agents/speaking` | Agent Speaking: server, STT, RAG, grader, web thi thử, synth |
| `backend/ielts_agent/listening` | Sinh và kiểm tra audio Listening |
| `backend/ielts_agent/infrastructure` | PostgreSQL (migration tự động), client LLM |
| `backend/tests` | Bộ test backend |
| `frontend/` | Ứng dụng Next.js |
| `prototypes/writing` | Prototype chấm Writing |
| `docs/`, `plans/` | Tài liệu thiết kế và kế hoạch triển khai |
| `DATABASE_CONTEXT.md` | Tóm tắt mô hình dữ liệu (3 ERD: nội dung, chấm điểm, cá nhân hoá) |

## Công nghệ

- **Backend:** Python 3.11+, FastAPI, Pydantic, psycopg 3, PostgreSQL 17 (Docker)
- **LLM:** OpenAI / DeepSeek (UC-04), Groq (Speaking: Whisper STT và model chấm)
- **Speech:** Groq Whisper, faster-whisper, Azure Cognitive Services Speech
- **Frontend:** Next.js 16, React 19, Tailwind CSS 4, Vitest

## Chạy cục bộ

Yêu cầu: Python 3.11+, Node.js 20+, Docker.

```sh
# 1. Cài đặt
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,speaking]"
cp .env.example .env                 # điền OPENAI_API_KEY, GROQ_API_KEY, ...
cp frontend/.env.example frontend/.env.local
(cd frontend && npm install)

# 2. Cơ sở dữ liệu
docker compose up -d --wait

# 3. Mỗi lệnh chạy trong một terminal riêng
DATABASE_URL=postgresql://ielts:ielts_dev_password@localhost:55432/ielts \
  PYTHONPATH=backend python -m uvicorn ielts_agent.api.main:app --port 8000
PYTHONPATH=backend python -m uvicorn ielts_agent.agents.speaking.server:app --port 8010
cd frontend && npm run dev
```

Sau khi chạy:

- Giao diện chính: <http://localhost:3000>
- Thi thử Speaking: <http://127.0.0.1:8010/exam>

## Kiểm thử

```sh
pytest                                # toàn bộ backend
pytest backend/tests/speaking         # riêng agent Speaking
cd frontend && npm test
```

## Lưu ý về dữ liệu

Repo không chứa các dữ liệu sau (đã liệt kê trong `.gitignore`):

- File `.env` chứa API key.
- Corpus band descriptors tải về trong `.cache/`, vì có bản quyền của IELTS Partners.
- Audio thật của người học và checkpoint phiên thi.
