# DATABASE_CONTEXT — IELTS Learning Agent

> Tài liệu định hướng cho coding agents. Nguồn: `Thiet_ke_CSDL_IELTS_Learning_Agent.md`. Đây là bản tóm tắt **mô hình nghiệp vụ**, không phải migration SQL hay danh sách cột đầy đủ. Khi triển khai, đối chiếu schema thực tế và tài liệu gốc; không tự suy diễn kiểu dữ liệu, FK hay constraint chưa được xác nhận.

## 1. System overview

Hệ thống hỗ trợ người học IELTS: quản lý ngân hàng nội dung, làm bài/phiên học, kiểm định câu hỏi, chấm và đối chiếu Writing/Speaking, lưu điểm yếu, kiểm tra đầu vào, lập kế hoạch và ôn tập SRS.

Ba miền dữ liệu:

1. **ERD 1 — Content & Attempts:** người học, phiên, ngân hàng nội dung, nhóm/câu hỏi, audio, lượt làm và câu trả lời, hội thoại Speaking.
2. **ERD 2 — Assessment:** hai lượt AI chấm độc lập, tiêu chí và bằng chứng, đối chiếu, giáo viên duyệt, điểm cuối.
3. **ERD 3 — Personalization:** mục tiêu, taxonomy lỗi, memory, thẻ SRS, kế hoạch học, placement.

## 2. Entity map

### ERD 1 — Content & Attempts

| Entity | Vai trò / liên kết chính |
|---|---|
| `LEARNER` | Người học; `id` PK |
| `SESSION` | Phiên học/kiểm tra; `id` PK, `learner_id` FK; `kind`: placement/practice/mock; `status`: in_progress/paused/finished; `thread_id` cho LangGraph |
| `EXAM` | Đề thi; được đề cập trong cấu trúc Reading/Listening nhưng **không có bảng thuộc tính chi tiết** trong tài liệu nguồn |
| `EXAM_ITEM` | Bài kỹ năng thuộc đề hoặc bài luyện độc lập (`exam_id` nullable); **chưa có đặc tả đầy đủ** |
| `CONTENT_ITEM` | Nội dung Reading passage / Listening part hoặc nội dung Writing/Speaking; `item_id` PK, `skill`, `topic`, `target_band`, `source`, `license`, `author`, `model`, `prompt_version`, `status`, `body` JSONB, `created_at`, `position` |
| `QUESTION_GROUP` | Nhóm câu hỏi của Reading/Listening; `group_id` PK, `item_id` FK, `position`, `question_type`, `instructions`, `prompt`, `response_mode`, `options` JSONB, `response_limits` JSONB, `layout` JSONB, `allow_reuse` |
| `QUESTION` | Câu hỏi/vị trí trả lời; `id` PK, `item_id` FK, `group_id` FK nullable, `position`, `number`, `prompt`, `options` JSONB, `target` JSONB, `question_type`, `answer_key`, `evidence_span`, `excluded` |
| `VALIDATION_RESULT` | Kiểm định nội dung/câu hỏi; `id`, `item_id`, `question_id`, `layer`, `passed`, `details` |
| `AUDIO_ASSET` | Audio của nội dung; `id`, `item_id`, `voice`, `accent`, `uri` |
| `QUESTION_REPORT` | Báo cáo lỗi/chất lượng câu hỏi; `id`, `question_id`, `status` |
| `ATTEMPT` | Lượt làm bài; `attempt_id`, `session_id`, `item_id`, `skill`, `mode`, `text_or_transcript`, `audio_uri`, `audio_deleted_at`, `submitted_at`, `raw_score` |
| `ANSWER` | Câu trả lời; `id`, `attempt_id`, `question_id`, `block_no`, `response`, `is_correct` |
| `SPEAKING_TURN` | Lượt nói; `id`, `attempt_id`, `turn_no`, `part`, `transcript`, `stt_confidence`, `duration_s`, `t_start_s` |
| `CANDIDATE_POINT` | Ý chính trích xuất từ lượt nói; `id`, `turn_id`, `point` |
| `ASKED_QUESTION` | Câu hệ thống hỏi; `id`, `attempt_id`, `part`, `text`, `refs_point_id` nullable |

### ERD 2 — Assessment

| Entity | Vai trò / liên kết chính |
|---|---|
| `ASSESSMENT` | Phiên đánh giá của `ATTEMPT`; `run_id`, `attempt_id`, `purpose`, `status`, `overall_band`, `word_count`, `limitations`, `descriptors_version`, `trace_id`, `cost_usd`, `latency_ms` |
| `GRADING` | Lượt chấm AI A/B; `id`, `run_id`, `grader_role`, `model`, `prompt_version`, `trace_id` |
| `GRADING_CRITERION` | Điểm/nhận xét theo tiêu chí; `id`, `grading_id`, `criterion`, `band`, `band_raw`, `cap_reason`, `comment` |
| `EVIDENCE_SPAN` | Bằng chứng văn bản/audio; `id`, `criterion_id`, `start_char`, `end_char`, `t_start_s`, `quote`, `verified` |
| `DESCRIPTOR_CHUNK` | Đoạn rubric; `chunk_id`, `test_part`, `criterion`, `band`, `version`, `source_url` |
| `GRADING_CHUNK` | N–N `GRADING` ↔ `DESCRIPTOR_CHUNK`; PK ghép `grading_id`, `chunk_id` |
| `CRITERION_REF` | N–N tiêu chí chấm ↔ descriptor; PK ghép `criterion_id`, `chunk_id` |
| `ASSESSMENT_FLAG` | Cảnh báo; `id`, `run_id`, `flag`, `set_by`, `details` |
| `RECONCILIATION` | Đối chiếu hai AI; `id`, `run_id`, `model`, `prompt_version`, `trace_id`, `self_confidence`, `escalated`, `escalate_reason` |
| `RECON_CRITERION` | Kết quả từng tiêu chí; `id`, `reconciliation_id`, `criterion`, `final_band`, `chosen`, `reason` |
| `TEACHER_REVIEW` | Giáo viên duyệt; `id`, `run_id`, `teacher_id`, `action`, `note`, `at` |
| `FINAL_SCORE` | Điểm cuối; `id`, `run_id`, `reconciliation_id`, `review_id`, `criterion`, `band`, `status`, `source`, `visible_to_learner`, `version` |

`ATTEMPT` là thực thể dùng chung từ ERD 1, không phải bảng mới của ERD 2.

### ERD 3 — Personalization

| Entity | Vai trò / liên kết chính |
|---|---|
| `LEARNER_GOAL` | Mục tiêu; `id`, `learner_id`, `target_band`, `exam_date`, `hours_per_week`, `rest_days` |
| `TAXONOMY_ERROR` | Danh mục lỗi; `code` PK, `node_code`, `taxonomy_version`, `deprecated`, `replaced_by` |
| `MEMORY_ENTRY` | Điểm yếu của người học; `id`, `learner_id`, `weakness_key`, `skill`, `category`, `weakness`, `count`, `mastery`, `status`, `first_seen`, `last_seen` |
| `MEMORY_EVIDENCE` | Bằng chứng điểm yếu; `id`, `entry_id`, `attempt_id`, `quote_or_item_id`, `recorded_at` |
| `DELETED_MEMORY_KEY` | Tombstone dữ liệu xóa; PK ghép `learner_id`, `key_hash` |
| `SRS_CARD` | Thẻ ôn tập; `id`, `learner_id`, `entry_id` nullable, `word`, `meaning`, `collocation`, `example`, `ease`, `repetitions`, `interval_days`, `due_date` |
| `STUDY_PLAN` | Kế hoạch; `id`, `learner_id`, `version`, `status`, `reject_reason` |
| `PLAN_ITEM` | Hoạt động trong kế hoạch; `id`, `plan_id`, `week`, `day`, `activity`, `duration_min`, `item_id` |
| `PLAN_ITEM_TARGET` | N–N hoạt động ↔ điểm yếu; PK ghép `plan_item_id`, `entry_id` |
| `PLACEMENT_RESULT` | Tổng kết đầu vào; `run_id`, `learner_id`, `session_id`, `overall_estimate`, `items_answered`, `path`, `recommended_focus` |
| `PLACEMENT_SKILL_RESULT` | Band từng kỹ năng; `id`, `run_id`, `skill`, `band_estimate`, `band_low`, `band_high`, `confidence`, `provisional` |

`LEARNER` dùng chung với ERD 1.

## 3. Critical Reading / Listening structure

```text
EXAM (optional for independent practice)
  └── EXAM_ITEM (one skill)
        └── CONTENT_ITEM [position] (Reading passage / Listening part)
              └── QUESTION_GROUP [position] (shared instructions, type, options)
                    └── QUESTION [position, number] (one answer slot)
```

- `CONTENT_ITEM.position`: thứ tự passage/part trong `EXAM_ITEM`, bắt đầu 1, unique `(exam_item_id, position)` theo tài liệu; tuy nhiên danh sách cột `CONTENT_ITEM` **chưa liệt kê `exam_item_id`**.
- `QUESTION_GROUP.position`: thứ tự nhóm trong item, bắt đầu 1, unique `(item_id, position)`.
- `QUESTION.position`: thứ tự trong nhóm, bắt đầu 1, unique `(group_id, position)`.
- `QUESTION.number`: đúng **một** số câu 1–40, duy nhất trong `EXAM_ITEM`; không dùng `numbers[]`.
- Reading Academic đầy đủ: 3 content items / 40 câu. Listening đầy đủ: 4 content items / 10 câu mỗi part. Luyện tập độc lập không cần đủ 40 câu.
- `QUESTION.group_id` bắt buộc đối với Reading/Listening, không bắt buộc với Writing/Speaking.
- `QUESTION.item_id` phải bằng `QUESTION_GROUP.item_id` cha.
- Reading/Listening lấy `question_type` từ `QUESTION_GROUP`, để NULL ở `CONTENT_ITEM` và `QUESTION`; Writing/Speaking giữ cách dùng hiện có.
- Hướng dẫn chung, ngân hàng options dùng chung, layout và giới hạn câu trả lời đặt tại group; câu riêng có thể có `prompt`, `options`, `target`.
- `response_mode` của group: `text`, `options`, `classification`.
- `body` của item chứa passage/transcript/part, **không nhân bản** các nhóm/câu đã lưu ở bảng riêng.
- `QUESTION.target` có thể chỉ đến paragraph trong passage; tham chiếu phải thuộc item cha.
- `QUESTION.excluded` và `evidence_span` vẫn được giữ.

### Answer keys / answer sets

- Mỗi câu có đúng một nguồn đáp án: `QUESTION.answer_key` **hoặc** một `QUESTION_GROUP.answer_sets`.
- Với dạng *Choose TWO letters* (ví dụ câu 11–12): hai `QUESTION`, một answer set chứa hai đáp án, `order=any`; A/C và C/A tương đương, A/A không được tính trùng.
- Với `text_set`, mỗi concept được ghép và tính điểm tối đa một lần.
- Một question không được nằm trong hai answer sets; mọi `question_id` trong set phải thuộc cùng group.
- Nếu câu thuộc answer set bị `excluded`, dừng chấm tự động cả set cho đến khi kiểm định lại.
- **Khoảng trống nguồn:** `QUESTION_GROUP.answer_sets` được mô tả trong quy tắc nhưng **không xuất hiện trong bảng thuộc tính QUESTION_GROUP**. Cần xác minh cách lưu và schema JSONB trước khi code.

### Answering / grading constraints

- `ATTEMPT.item_id` vẫn trỏ đến **một CONTENT_ITEM**, không tự đổi thành `exam_item_id`.
- `ANSWER` liên kết từng `QUESTION` với `ATTEMPT`; `block_no` không thay `group_id`/`position`.
- Reading/Listening có đáp án cố định: **chấm bằng code**, không giao LLM quyết định đúng/sai. Có thể dùng AI để nhận xét tổng kết sau khi chấm (quy tắc dự án được người dùng xác lập, không phải nội dung khẳng định trong tài liệu nguồn).
- `ANSWER.is_correct` lưu kết quả; khi chấm set phải tránh cộng điểm trùng.

## 4. Main data flows

```text
Learner -> SESSION
Select skill/content -> EXAM_ITEM -> CONTENT_ITEM -> QUESTION_GROUP -> QUESTION
Start/submit -> ATTEMPT -> ANSWER
Speaking -> ATTEMPT -> SPEAKING_TURN -> CANDIDATE_POINT
                                └── ASKED_QUESTION

ATTEMPT -> ASSESSMENT -> GRADING A + GRADING B
                              -> GRADING_CRITERION -> EVIDENCE_SPAN
                              -> descriptors (GRADING_CHUNK / CRITERION_REF)
                       -> ASSESSMENT_FLAG
                       -> RECONCILIATION -> RECON_CRITERION
                       -> TEACHER_REVIEW (if needed)
                       -> FINAL_SCORE

LEARNER -> LEARNER_GOAL
        -> PLACEMENT_RESULT -> PLACEMENT_SKILL_RESULT
        -> MEMORY_ENTRY -> MEMORY_EVIDENCE
        -> STUDY_PLAN -> PLAN_ITEM -> PLAN_ITEM_TARGET
        -> SRS_CARD
```

## 5. Enumerations explicitly mentioned

- `CONTENT_ITEM.skill`: Listening, Reading, Writing, Speaking.
- `CONTENT_ITEM.source`: self_written, llm_generated_verified, open_license.
- `CONTENT_ITEM.status`: verified, rejected, spare.
- `VALIDATION_RESULT.layer`: rules, solver, dedup.
- `ATTEMPT.mode`: text, voice.
- `ASSESSMENT.purpose`: live, eval; `status`: final, provisional, pending_teacher, failed.
- `GRADING.grader_role`: A, B.
- `RECONCILIATION.self_confidence`: low, medium, high.
- `RECON_CRITERION.chosen`: A, B, middle.
- `TEACHER_REVIEW.action`: approve, edit, reject.
- `FINAL_SCORE.source`: average, moderator, teacher; `status`: final, provisional, pending_teacher.
- `MEMORY_ENTRY.status`: active, improving, resolved; `mastery`: 0..1.
- `STUDY_PLAN.status`: proposed, active, rejected, superseded.
- Grading criteria: TA, TR, CC, LR, GRA, FC, PR (dùng theo kỹ năng phù hợp).

## 6. Agent implementation checklist

1. Đọc tài liệu này để nắm miền dữ liệu, sau đó kiểm tra migrations/models/schema thực tế.
2. Không giả định các cột chỉ xuất hiện trong mô tả quan hệ đã có trong DB.
3. Không thay đổi Writing/Speaking hoặc cơ chế cá nhân hóa chỉ để bổ sung Reading/Listening.
4. Khi query Reading/Listening, sắp theo `CONTENT_ITEM.position`, `QUESTION_GROUP.position`, `QUESTION.position`; hiển thị `QUESTION.number`.
5. Validate uniqueness, consistency of parent IDs, answer ownership, and contiguous positions trước khi xuất bản nội dung.
6. Không nhân bản ngân hàng options chung xuống từng câu, hoặc question groups vào `CONTENT_ITEM.body`.
7. Chấm câu có đáp án cố định bằng code; AI không thay thế answer key.
8. Không tạo migration hoặc tự điền cấu trúc `EXAM`, `EXAM_ITEM`, `answer_sets` khi chưa kiểm tra repo và làm rõ yêu cầu.
9. Nếu tài liệu và code khác nhau, báo rõ chênh lệch, đề xuất cách xử lý và yêu cầu xác nhận trước khi thay đổi dữ liệu.

## 7. Known ambiguities to resolve

- `EXAM` / `EXAM_ITEM` có quan hệ được mô tả nhưng thiếu đặc tả bảng/cột đầy đủ.
- `CONTENT_ITEM.position` có unique theo `exam_item_id`, song `exam_item_id` chưa có trong bảng thuộc tính được liệt kê.
- `QUESTION_GROUP.answer_sets` được sử dụng trong business rules nhưng chưa có định nghĩa cột và cấu trúc JSON.
- Cách nhóm các `ATTEMPT` theo content item thành một lượt thi kỹ năng đầy đủ chưa được đặc tả tường minh; không tự giả định `SESSION` giải quyết mọi trường hợp.
- Tài liệu gốc ghi `EXAM`/`EXAM_ITEM` được bổ sung; cần xác minh với phiên bản schema hiện đang triển khai trước khi tạo lại.

## 8. Source of truth

`Thiet_ke_CSDL_IELTS_Learning_Agent.md` là bản mô tả chi tiết nguồn của tóm tắt này. Repo migrations và model hiện hành là nguồn để xác nhận cấu trúc đã triển khai. Nếu có xung đột, **không âm thầm chọn một bên**: báo lại để người phụ trách quyết định.
