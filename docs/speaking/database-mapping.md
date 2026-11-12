# Contract Speaking theo database-design.docx

Cập nhật 16/10/2026. Nguồn: [database-design.docx](https://github.com/se373agenticengineering/nhom-05) (tài liệu thiết kế của nhóm, không nằm trong repo), cả bảng thuộc tính và sơ đồ ERD 1/2. File nguồn được giữ nguyên. Contract có version `ielts-speaking-db-1.0`; các model và bộ ánh xạ ở `database.py` trong package.

[JSON Schema](database-schema.json) định nghĩa các trường/kiểu của từng bảng. [Ví dụ xuất phiên text](examples/database-export-text.json) dùng dữ liệu giả lập và chưa chấm điểm, không chứa người học hoặc audio thật.

## Định dạng output

Cả **Xuất kết quả** ở trang luyện `/` và **Xuất JSON** ở `/exam` đều dùng cùng envelope:

```json
{
  "schema_version": "ielts-speaking-db-1.0",
  "tables": {
    "LEARNER": [],
    "SESSION": [],
    "CONTENT_ITEM": [],
    "QUESTION": [],
    "ATTEMPT": [],
    "ANSWER": [],
    "SPEAKING_TURN": [],
    "CANDIDATE_POINT": [],
    "ASKED_QUESTION": [],
    "ASSESSMENT": [],
    "GRADING": [],
    "GRADING_CRITERION": [],
    "EVIDENCE_SPAN": [],
    "DESCRIPTOR_CHUNK": [],
    "GRADING_CHUNK": [],
    "CRITERION_REF": [],
    "ASSESSMENT_FLAG": [],
    "RECONCILIATION": [],
    "RECON_CRITERION": [],
    "TEACHER_REVIEW": [],
    "FINAL_SCORE": []
  },
  "external_references": {"descriptor_chunk_ids": []},
  "extensions": {}
}
```

Mỗi array chứa các row có tên cột đúng như tài liệu. Bảng chưa phát sinh dữ liệu là array rỗng; không tạo một lượt chấm, quyết định giáo viên hoặc điểm mẫu để lấp đầy output. `skill` là `Speaking`, part là `part1/part2/part3`, UUID là chuỗi UUID, thời gian là ISO 8601 UTC. Đánh số `turn_no` và `block_no` bắt đầu từ 1.

Chỉ import các row trong `tables`. `extensions` chứa analysis STT/VAD, warning theo lượt, checkpoint, gợi ý sửa câu, disclaimer và dữ liệu vận hành chưa có cột tương ứng. Phần này không được insert nguyên object vào bảng quan hệ. JSON Schema bật `extra=forbid`, nên row thêm cột không có trong thiết kế sẽ bị từ chối.

## Định danh và thuộc tính phiên thi

| Dữ liệu trước đây | Dữ liệu theo thiết kế |
| --- | --- |
| `session_id` là khóa chính trong response phiên | `SESSION.id`; `ATTEMPT.session_id` là FK đến ID này. |
| Chưa có lượt làm riêng | `ATTEMPT.attempt_id`, khác `SESSION.id`; một phiên demo hiện có một lượt Speaking. |
| ID cue card / ngân hàng dạng `part2-skill` | Là mã nguồn đề, không dùng làm UUID PK. Snapshot đề có `CONTENT_ITEM.item_id`; mã gốc giữ trong `body.questions[].bank_question_id`. |
| `q_id` của câu đã hỏi | `ASKED_QUESTION.id`; có `attempt_id`, `part`, `text`, `refs_point_id`. |
| Câu hỏi để ANSWER tham chiếu | `QUESTION.id` riêng, liên kết `CONTENT_ITEM.item_id`; response câu hỏi có `question_id` để gửi lại khi trả lời. |
| `answer_id` là khóa chính câu trả lời | `ANSWER.id`, cùng `attempt_id`, `question_id`, `block_no`, `response`, `is_correct`. |
| `turn_id` là khóa chính lượt nói | `SPEAKING_TURN.id`; `CANDIDATE_POINT.turn_id` là FK đến lượt nói. |
| Ý `{point, source_turn, part}` | `CANDIDATE_POINT {id, turn_id, point}`; phần thi được suy ra từ lượt nói. |
| Embedded `candidate_point_ref` trong câu hỏi | `ASKED_QUESTION.refs_point_id`; null nếu không có ý làm nguồn. |
| Corpus descriptor dùng `id` | `DESCRIPTOR_CHUNK.chunk_id`; adapter đọc được `id` cũ nhưng chuẩn hóa thành `chunk_id`. |
| `grader_id=grader-a/grader-b` | `GRADING.id` là UUID, `grader_role=A/B`, liên kết `run_id`. |

`SESSION` có `id`, `learner_id`, `kind`, `status`, `thread_id`. Request tạo phiên hỗ trợ `learner_id` UUID của backend nhóm, `kind=mock/practice` và `thread_id`; nếu thiếu, demo cấp định danh local. `thread_id` của demo là khóa checkpoint, chưa khẳng định đã có LangGraph. Speaking rút gọn/placement vẫn cần tích hợp với UC01.

Response `/api/exam/sessions/{id}` có `session.id`, `session.attempt_id`, `session.item_id`, `session.speaking_turns`, `session.candidate_points`. Câu hỏi hiện tại có `id` (ASKED_QUESTION), `question_id` (QUESTION), `refs_point_id`. Gửi `current_question.question_id` trong field `question_id` khi trả lời. Response câu trả lời có `id`, `attempt_id`, `question_id`, `block_no`, `response`, `is_correct`, kèm object `speaking_turn` và analysis phục vụ demo. Đây là DTO runtime; để insert database dùng endpoint export đã tách bảng.

Private SQLite checkpoint vẫn đọc được tên field cũ để giữ phiên/audio đã lưu. ID cũ của phiên, câu trả lời và lượt nói được giữ nguyên; ID mới còn thiếu được suy ra UUID5 ổn định, không đổi sau mỗi lần xuất. Cache local không được coi là schema database chung của nhóm.

## Nội dung đề và lượt làm

Một snapshot Speaking có một `CONTENT_ITEM` chứa toàn bộ câu hỏi đã thực sự hỏi. Văn bản câu hỏi, cue card và liên kết `asked_question_id` nằm trong `CONTENT_ITEM.body.questions`; bảng `QUESTION` không có cột `text` trong thiết kế nguồn. Không xuất các câu hỏi Part 3 chưa hỏi.

Đề hiện dùng template tự viết, nên source=self_written, model/prompt_version=null. Snapshot chưa qua kiểm duyệt của nhóm được ghi status=spare. Chưa xác nhận license/author thì ghi `unconfirmed`; không tự khai open_license hoặc verified. Nhóm cần hoàn thiện metadata trước khi đưa snapshot thành đề dùng chung.

`ANSWER.response` và `SPEAKING_TURN.transcript` giữ nguyên lời của lượt. Speaking là câu hỏi mở nên `ANSWER.is_correct=null`, không biến việc có transcript thành câu trả lời đúng. `ANSWER.block_no` và `SPEAKING_TURN.turn_no` cùng thứ tự trong attempt. Vì ERD chưa có FK trực tiếp giữa ANSWER và SPEAKING_TURN, `extensions.analysis` ghi cả answer_id/turn_id để adapter nhóm đối chiếu.

`ATTEMPT.text_or_transcript` là các transcript theo thứ tự lượt, nối bằng đúng hai ký tự LF (`\n\n`), không thêm nhãn câu hỏi/Part vào văn bản này. `ATTEMPT.raw_score=null`: band IELTS/ước lượng không tự được coi là điểm thô. `submitted_at` của lượt làm được ghi khi phiên thi kết thúc; export snapshot luyện đang tiếp tục thì vẫn null.

## Audio và timestamps

Khi người học đồng ý lưu toàn bộ audio, `ATTEMPT.audio_uri` trỏ đến endpoint WAV thực `/api/exam/sessions/{id}/attempt-audio`. Endpoint giải mã và ghép các clip theo thứ tự thành mono PCM 16 kHz, không chèn thêm khoảng lặng. Đây là chuỗi bản thu ghép, không phải timeline thời gian thực gồm chuẩn bị/chờ mạng.

`SPEAKING_TURN.t_start_s` tính từ đầu audio ghép, `duration_s` là thời lượng audio của lượt. Lượt mới lưu số sample để tính thời gian chính xác; lượt cũ chỉ có duration làm tròn thì giữ độ chính xác hiện có. Word timestamps và metrics trong extensions vẫn tương đối với từng clip. `extensions.audio_segments` giữ URI clip để nghe lại riêng.

Không đồng ý lưu hoặc chưa đủ audio: `ATTEMPT.audio_uri=null`, `SPEAKING_TURN.t_start_s=null`. Export trang luyện `/` không biến blob URL của tab thành URI database; audio_uri vẫn null vì các clip chưa được persist ở backend. `audio_deleted_at` chỉ dùng khi có thao tác xóa thực tế, không dùng nó thay trạng thái chưa lưu. URI demo là đường dẫn local có thể tải được, chưa phải URI object storage của nhóm; cần ánh xạ khi tích hợp kho lưu chính thức.

## Chấm điểm và dẫn chứng

- `ASSESSMENT` liên kết attempt bằng attempt_id; chứa purpose/status/overall_band/word_count/limitations/descriptors_version/trace_id/cost_usd/latency_ms đúng ERD. Word count do code tính. Chi phí và trace chưa đo thì null; latency_ms là thời gian pipeline chấm thực đo, không phải STT latency.
- Mỗi A/B là một `GRADING`; mỗi tiêu chí là một `GRADING_CRITERION` với band, band_raw, cap_reason, comment. PR chưa đánh giá dùng band=null, cap_reason=not_assessed; không tạo điểm PR=0.
- `EVIDENCE_SPAN.start_char/end_char` là Unicode code points, 0-based, end-exclusive trên **ATTEMPT.text_or_transcript**. Span model trả theo từng câu được kiểm tra rồi cộng offset của lượt. Export kiểm tra lại quote nguyên văn trên văn bản toàn bài. `verified=true` nghĩa là xác minh vị trí/quote trong transcript, không chứng minh STT đúng audio hoặc phát âm đúng.
- `EVIDENCE_SPAN.t_start_s` cộng offset audio của lượt khi có audio bài ghép và timestamp hợp lệ; không có timeline audio thì null, không tạo mốc giả.
- `GRADING_CHUNK` ghi các chunk thực sự truy xuất; `CRITERION_REF` ghi các chunk được viện dẫn cho tiêu chí. Không dùng một danh sách thay cả hai quan hệ. Bản chấm mới giữ snapshot descriptors để export đủ metadata đã sử dụng. Cache cũ thiếu snapshot ghi các chunk cần có sẵn trong `external_references.descriptor_chunk_ids`; backend phải giải quyết chúng trước khi insert FK.
- `ASSESSMENT_FLAG` tách flag thành row với run_id, set_by=code/judge và details. Warning kỹ thuật STT không thuộc enum flag vẫn ở extensions.
- `FINAL_SCORE` chỉ tạo từ hai bản chấm hợp lệ đã được tổng hợp, source=average. Điểm text là provisional; voice vẫn thiếu PR nên không tạo score overall. Thiếu tiêu chí không được tự gán 0.
- Chuyển pending_teacher tạo `RECONCILIATION` với escalated=true và lý do. Chưa có moderator/giáo viên xử lý thì `RECON_CRITERION` và `TEACHER_REVIEW` rỗng, không tạo quyết định giả. Điểm pending không được phát hành thành FINAL_SCORE hiển thị cho người học.

Không tự tạo `MEMORY_ENTRY`, mastery/count hoặc SRS từ flags/corrections: ERD 3 cần taxonomy/weakness_key và cơ chế cập nhật của Planning. Gợi ý nâng cấp câu/từ vựng vẫn trong extensions.feedback để nhóm nối UC06 sau.

## API và kiểm tra tích hợp

- `GET /api/speaking/database-schema`: JSON Schema các bảng, cùng version của file schema.
- `GET /api/exam/sessions/{id}/export`: export database cho phiên thi, đọc được cả checkpoint cũ.
- `POST /api/speaking/export`: chuyển lịch sử luyện Part 1/2 thành cùng contract; input có session_id UUID, created_at và answers từ demo. Có thể truyền learner_id của backend.
- `GET /api/exam/sessions/{id}/attempt-audio`: WAV ghép khi đã có đồng ý lưu.

Import theo thứ tự cha trước con: LEARNER → SESSION → CONTENT_ITEM → QUESTION → ATTEMPT → ANSWER/SPEAKING_TURN → CANDIDATE_POINT → ASKED_QUESTION → ASSESSMENT → GRADING/DESCRIPTOR_CHUNK → GRADING_CRITERION → EVIDENCE_SPAN/GRADING_CHUNK/CRITERION_REF/ASSESSMENT_FLAG → RECONCILIATION/RECON_CRITERION/TEACHER_REVIEW → FINAL_SCORE. Resolve external descriptor references trước khi insert các bảng liên kết. Dùng upsert theo PK vì cùng snapshot có ID ổn định.

`validate_export` kiểm tra model/cột/enum, UUID, giá trị không hữu hạn, trùng PK, khóa ngoại và quote toàn bài. Unit tests đọc trực tiếp bảng thuộc tính trong DOCX để đối chiếu tập tên cột, thêm test offsets Unicode, điểm chưa chấm, corpus cũ, audio thật ghép, export luyện/thi thử và checkpoint cũ. Hiện 60 tests và hai bộ browser test đã qua, không gọi Groq trong kiểm tra này. Đã kiểm tra 7 checkpoint cũ bằng kết nối chỉ đọc.

Đây là contract và adapter output, chưa phải migration hay thao tác insert vào database chung. Repo chỉ có tài liệu thiết kế, chưa có DDL/connection database nhóm; backend cần đối chiếu nullable/default/unique thực tế trước khi triển khai importer. Ví dụ snapshot `CONTENT_ITEM` có license/author chưa xác nhận là dữ liệu cần hoàn thiện, không phải xác nhận bản quyền/kiểm duyệt.

## Pronunciation và RAG

Azure native scores 0–100 được giữ trong `extensions.pronunciation` và analysis của từng answer, chưa chuyển sang band IELTS. PR band vẫn null, không tạo FINAL_SCORE PR/overall voice. RAG dùng các bảng DESCRIPTOR_CHUNK/GRADING_CHUNK/CRITERION_REF như trước; text/page/hash/provenance và trace xếp hạng nằm trong extensions, không tự thêm cột vào thiết kế chung. Xem [hướng dẫn tích hợp](pronunciation-rag.md).
