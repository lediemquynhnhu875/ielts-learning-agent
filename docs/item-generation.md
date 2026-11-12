# UC-04: Agent sinh bài Reading và Listening

`ItemGenerationAgent` nhận kỹ năng, chủ đề, band mục tiêu, số câu và giới hạn từ
Completion; trả về `ExerciseDraft` đã parse bằng Pydantic. Reading yêu cầu
600–900 từ, Listening yêu cầu script 400–700 từ. Prompt yêu cầu 8–13 câu,
ít nhất ba dạng câu, kèm đáp án, evidence và giải thích.

## Cài đặt và cấu hình

Cần Python 3.11 trở lên. Chạy các lệnh PowerShell từ thư mục gốc repo:

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e '.[dev]'
Copy-Item .env.example .env
```

Điền key trong `.env`; không commit file này. `Settings.from_env()` tự nạp `.env`
và ưu tiên các biến đã đặt trong shell. Chọn `PROVIDER=openai` với
`OPENAI_API_KEY`, hoặc `PROVIDER=deepseek` với `DEEPSEEK_API_KEY`.
`GENERATOR_MODEL` ghi đè model mặc định của provider; `LLM_TIMEOUT_SECONDS`
đặt thời gian chờ cho mỗi lời gọi. Khi dịch vụ báo model không khả dụng,
đặt `GENERATOR_MODEL` thành model mà tài khoản của bạn được phép sử dụng.

## Gọi agent

Chạy ví dụ sau trong Python từ thư mục gốc repo sau khi cài đặt:

```python
from ielts_agent.agents.uc04.generator import ItemGenerationAgent
from ielts_agent.agents.uc04.models import GenerateRequest
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.llm.client import JsonLLMClient

runtime = JsonLLMClient(Settings.from_env())
try:
    agent = ItemGenerationAgent(runtime)
    request = GenerateRequest(
        skill="reading",  # Đổi thành "listening" để sinh script.
        topic="Can Gio mangroves",
        target_band=6.0,
        question_count=10,
        completion_word_limit=2,
    )
    draft = agent.run(request, feedback=[])
    print(draft.model_dump_json(indent=2))
    print(agent.metadata)
finally:
    runtime.close()
```

`ExerciseDraft` gồm `title`, `text`, `questions`. Mỗi câu có `id`, `kind`,
`prompt`, `options`, `word_limit`, `paragraph_id`, `answer`, `evidence_span`
và `explanation`. Các dạng câu: True/False/Not Given, Multiple Choice,
Sentence Completion và Matching Headings. Not Given dùng evidence null;
các câu khác phải trích nguyên văn nội dung làm bằng chứng theo
[skill](../backend/ielts_agent/agents/uc04/skills/reading-item-generation/SKILL.md).

`agent.metadata` chứa provider, model cấu hình, phiên bản prompt và SHA-256
của nội dung skill. Lưu metadata này cùng kết quả để truy vết lần sinh bài.
`feedback` là danh sách phản hồi cho lần sinh kế tiếp; mỗi lời gọi dùng lịch sử
riêng. Agent báo `InvalidAgentOutput` khi JSON/schema sai hoặc kết quả chưa
hoàn tất; lỗi API được chuyển thành `ProviderError` với thông báo đã lược bỏ
nội dung lỗi gốc.

Schema kiểm tra cấu trúc và kiểu dữ liệu. Dùng
[validator quy tắc](rule-validation.md) để kiểm tra độ dài passage/script,
số lượng và loại câu, định dạng đáp án và evidence sau khi sinh bài.
Để đối chiếu đáp án và thử lại, dùng
[pipeline kiểm chứng bằng solver độc lập](independent-verification.md).
Agent sinh bài riêng lẻ chưa chứng nhận bài đủ điều kiện phát hành. Audio,
API và lưu trữ PostgreSQL thuộc các phần sau.

## Kiểm thử offline

```powershell
python -m pytest backend/tests/test_generation.py
```

Tests dùng HTTP transport giả lập, không gọi provider thật và không cần API key.
Tests kiểm tra hai kỹ năng với hai provider, schema sai, lỗi provider, giới hạn
đầu vào, metadata, prompt và việc không ghi thông tin bí mật vào thông báo lỗi.
