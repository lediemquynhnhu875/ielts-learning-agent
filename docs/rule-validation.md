# UC-04: Validator quy tắc Reading/Listening

`validate_rules()` kiểm tra dữ liệu `ExerciseDraft` bằng code trước bước solver
độc lập. Hàm dùng schema của phần sinh bài và chạy offline, không gọi LLM hoặc
CSDL. Validator không kết luận đáp án đúng ngữ nghĩa hoặc NOT GIVEN là chính xác.

## Các quy tắc

- Reading có 600–900 từ; Listening có 400–700 từ.
- Mỗi bài có 8–13 câu, ít nhất ba dạng câu và ID không trùng nhau.
- `enforce_requested_count=True` yêu cầu số câu bằng `request.question_count`.
- True/False/Not Given dùng đúng `TRUE`, `FALSE`, `NOT GIVEN`. NOT GIVEN có
  `evidence_span=None`; các câu khác có evidence không rỗng, xuất hiện nguyên
  văn và phân biệt hoa thường trong passage/script.
- Multiple Choice và Matching Headings có ít nhất ba lựa chọn không rỗng,
  nội dung không trùng nhau; đáp án phải là một nhãn lựa chọn có tồn tại.
- Completion có một chỗ trống `____`, giới hạn từ khớp request và đáp án không
  vượt giới hạn. Đáp án được trích nguyên văn, đúng ranh giới từ, đồng thời
  xuất hiện trong evidence. Kiểm tra ranh giới dùng cùng quy ước từ với
  `word_count()`: không lấy `known` từ `well-known`, `don` từ `don't` hay
  `3` từ `3.5`. Đáp án đầy đủ vẫn phải khớp đúng hoa thường và khoảng trắng.
- Matching Headings tham chiếu đoạn có nhãn `[A]`, `[B]`… duy nhất, evidence
  thuộc đoạn được hỏi. Các câu liên tiếp dùng cùng một ngân hàng heading
  không được dùng lại đáp án.
- `word_limit`, `paragraph_id` và `options` chỉ được dùng cho dạng câu tương ứng.

Schema Pydantic chịu trách nhiệm kiểm tra kiểu dữ liệu và trường bắt buộc trước
khi gọi validator. Validator kiểm tra thêm quan hệ giữa các trường và nội dung.

## Cách gọi và kết quả

Sau khi lấy `draft` từ `ItemGenerationAgent`, gọi:

```python
from dataclasses import asdict
from ielts_agent.agents.uc04.rules import validate_rules

report = validate_rules(draft, request, enforce_requested_count=True)
print(report.passed)
print(asdict(report))
```

`RuleReport` gồm:

- `exercise_errors`: lỗi cấp bài, ví dụ số từ hoặc số câu ngoài khoảng,
  thiếu dạng câu, trùng ID.
- `items`: ánh xạ ID câu hỏi sang danh sách mã quy tắc bị vi phạm. Câu hợp lệ
  có danh sách rỗng. Mỗi ID trùng có mã `duplicate_question_id` đúng một lần
  ở khóa tương ứng; các lỗi khác của những câu cùng ID vẫn dùng chung khóa đó.
  Mã `duplicate_question_ids` đồng thời xuất hiện ở `exercise_errors`, làm cả
  bài không đạt.
- `passed`: thuộc tính bằng `True` khi cả hai nhóm lỗi đều rỗng.

Ví dụ lỗi của một câu Completion:

```json
{
  "exercise_errors": [],
  "items": {
    "q1": ["completion_answer_exceeds_word_limit", "completion_answer_not_in_evidence"]
  }
}
```

Ví dụ `q1` bị trùng, còn `q2` hợp lệ:

```json
{
  "exercise_errors": ["duplicate_question_ids"],
  "items": {
    "q1": ["duplicate_question_id"],
    "q2": []
  }
}
```

Ứng dụng có thể dùng các mã lỗi làm phản hồi cho generator hoặc thông tin cho
bước xử lý tiếp theo. Quyết định thử lại, loại câu và lưu bài thuộc coordinator;
validator không sửa dữ liệu đầu vào và không tự sinh lại bài. Xem
[pipeline kiểm chứng độc lập](independent-verification.md) để kết hợp validator
với solver và luồng thử lại.

## Kiểm thử

Cài đặt theo [hướng dẫn sinh bài](item-generation.md), sau đó chạy:

```powershell
python -m pytest backend/tests/test_rules.py
```

Tests bao gồm giá trị biên số từ và số câu, xác định từng ID trùng, dạng câu
thiếu, evidence sai/rỗng, NOT GIVEN có evidence, giới hạn và ranh giới từ
Completion (từ ghép, dạng rút gọn và số), lựa chọn sai cấu trúc và kiểm tra
paragraph cho Matching Headings.
