# UC-04: Kiểm chứng bằng solver độc lập

`VerifiedGenerationPipeline` kết hợp `ItemGenerationAgent`, validator quy tắc
và `BlindSolverAgent` để sinh bài, kiểm chứng rồi thử lại khi cần. Pipeline chạy
độc lập với API và lưu trữ; cài đặt theo [hướng dẫn sinh bài](item-generation.md).

## Cấu hình và cách gọi

Generator dùng `PROVIDER`, `GENERATOR_MODEL` và API key tương ứng. Solver có
thể dùng `SOLVER_PROVIDER` và `SOLVER_MODEL` riêng. Nếu không đặt
`SOLVER_PROVIDER`, solver dùng provider của generator; nếu không đặt
`SOLVER_MODEL`, solver dùng model mặc định của provider đó, không kế thừa
`GENERATOR_MODEL`. Khi dùng hai provider, cần cấu hình API key cho cả hai.

```python
from ielts_agent.agents.uc04.generator import ItemGenerationAgent
from ielts_agent.agents.uc04.models import GenerateRequest
from ielts_agent.agents.uc04.pipeline import (
    VerificationError, VerifiedGenerationPipeline,
)
from ielts_agent.agents.uc04.solver import BlindSolverAgent
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.llm.client import JsonLLMClient

settings = Settings.from_env()
generator_runtime = JsonLLMClient(settings, "generator")
solver_runtime = JsonLLMClient(settings, "solver")
try:
    pipeline = VerifiedGenerationPipeline(
        ItemGenerationAgent(generator_runtime),
        BlindSolverAgent(solver_runtime),
    )
    result = pipeline.run(GenerateRequest(
        skill="reading",  # Hoặc "listening" để sinh script.
        topic="Can Gio mangroves",
        target_band=6.0,
        question_count=10,
        completion_word_limit=2,
    ))
    print(result.draft.model_dump_json(indent=2))
    print(result.trace)
except VerificationError as exc:
    print(exc.code)
    print(exc.trace)
finally:
    generator_runtime.close()
    solver_runtime.close()
```

Mỗi lần solver chạy là một lời gọi stateless riêng. Solver chỉ nhận passage/script
và các trường câu hỏi trong danh sách cho phép: `id`, `kind`, `prompt`, `options`,
`word_limit`, `paragraph_id`. Payload không chứa đáp án, evidence hoặc giải thích
của generator. Solver tự trả đáp án, evidence và lý do cho từng ID câu hỏi.

## Luồng kiểm chứng và thử lại

1. Generator sinh ứng viên theo request. [Validator quy tắc](rule-validation.md)
   kiểm tra bài, bao gồm số câu đúng bằng `question_count`. Lỗi cấp bài khiến
   pipeline gửi phản hồi cho generator và sinh lại trước khi gọi solver.
2. Solver giải bài độc lập. Kết quả thiếu ID, thừa ID hoặc trùng ID làm ứng viên
   không đạt; pipeline không chấp nhận một phần kết quả sai giao thức.
3. Đối chiếu đáp án và kiểm tra evidence của solver. Khi so sánh câu trả lời tự
   do, hệ thống chuẩn hoá khoảng trắng và hoa thường; nhãn Multiple Choice và
   Matching Headings phải khớp chính xác. Quy tắc trích nguyên văn, giới hạn từ,
   đoạn được hỏi và evidence null cho Not Given vẫn được kiểm tra riêng.
4. Loại các câu không đạt validator hoặc đối chiếu solver, rồi kiểm tra lại bài
   còn lại. Bài vẫn phải có 8–13 câu và ít nhất ba dạng câu. Nếu loại **hơn 20%**
   số câu ban đầu, phải sinh lại; đúng 20% có thể được giữ nếu bài còn lại đạt
   mọi quy tắc. Sau khi loại câu, số câu không bắt buộc bằng request ban đầu.
5. Trả về `VerifiedExercise` gồm `draft` và `trace`. Với câu được giữ, evidence
   và giải thích được lấy từ evidence và lý do của solver độc lập.

Pipeline cho phép tối đa **ba lần sinh**: lần đầu và hai lần sinh lại. JSON sai
schema hoặc phản hồi model chưa hoàn tất được ghi vào trace và thử lại trong
giới hạn này. Lỗi provider dừng ngay với `VerificationError.code="provider_error"`;
hết ba lần vẫn không đạt trả `code="generation_exhausted"`.

Trace nằm trong bộ nhớ, chứa metadata, request, từng lần thử, báo cáo quy tắc,
kết quả solver và lý do loại câu/thử lại. Trace đi cùng kết quả thành công hoặc
`VerificationError`; pipeline này không tự lưu trace hay bài vào CSDL.

Đây là kiểm chứng bằng một lời gọi model độc lập, chưa phải bằng chứng thực
nghiệm rằng mọi đáp án đều chính xác. API, safety, PostgreSQL và chống trùng
thuộc phần tích hợp sau; tổng hợp audio nằm ngoài pipeline này.

## Kiểm thử offline

```powershell
python -m pytest backend/tests/test_solver.py backend/tests/test_verified_generation.py
```

Tests dùng provider giả lập, kiểm tra payload không lộ đáp án, giao thức ID,
evidence, đối chiếu đáp án, ngưỡng loại câu, thử lại và trace; không gọi API thật.
