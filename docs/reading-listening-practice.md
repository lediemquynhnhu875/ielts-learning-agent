# Làm bài và chấm Reading/Listening

Backend hỗ trợ bắt đầu lượt luyện tập, mở lại, lưu nháp và nộp bài cho **một
`CONTENT_ITEM` đã kiểm chứng**. Chấm bằng code theo đáp án cố định, không gọi LLM.
Bài hiện có 8–13 câu; Listening dùng script, chưa có audio. Luồng này chưa thêm UI,
đề thi đủ 40 câu, tài khoản người học hoặc điểm band IELTS.

## Khởi tạo và xác thực

Chạy PostgreSQL rồi khởi động API:

```powershell
python -m uvicorn ielts_agent.api.main:app --host 127.0.0.1 --port 8000
```

API tự chạy migration còn thiếu trước khi nhận request, kể cả với Docker volume
đã tồn tại. Mặc định `DATABASE_AUTO_MIGRATE=true`; bảng `uc04_schema_migration`
ghi nhận `001_uc04.sql`, `002_practice.sql` để mỗi file chỉ chạy một lần. Nếu tắt
tự động, chạy `python -m ielts_agent.infrastructure.db.cli init` riêng. Xem
[migration CSDL](database-migrations.md). Các bảng phát triển `practice_attempt`/`practice_answer` là
phần mở rộng độc lập, chưa phải migration đầy đủ cho `SESSION`/`ATTEMPT`/`ANSWER`.

Nếu đặt `API_TOKEN`, tất cả endpoint dưới đây yêu cầu
`Authorization: Bearer <API_TOKEN>` như API UC-04. Sau khi tạo lượt làm, các thao
tác đọc/lưu/nộp còn yêu cầu `X-Attempt-Token` riêng của lượt đó. Secret chỉ được
trả **một lần lúc tạo**; CSDL chỉ giữ SHA-256 và so sánh hash theo thời gian hằng.
Client cần giữ secret cùng `attempt_id`; mất secret thì bắt đầu lượt mới.

Token riêng giới hạn truy cập theo lượt làm, chưa liên kết với danh tính người
học. API `/exercises/{id}/answers` và `/traces/{trace_id}` cũ vẫn dành cho công cụ
backend/quản trị, dùng bearer chung và có thể chứa đáp án. Vì chưa có phân quyền
học viên/quản trị, hệ thống hiện không bảo đảm giữ bí mật đáp án trong một kỳ thi
có người cố tình truy cập các API đó.

## API và vòng đời

| Endpoint | Request | Kết quả |
|---|---|---|
| `POST /api/exercises/{item_id}/attempts` | Không cần body | `201`, tạo lượt `in_progress` và trả `attempt_token` |
| `GET /api/attempts/{attempt_id}` | Token riêng trong header | `200`, mở lại nội dung, nháp hoặc kết quả đã lưu |
| `PATCH /api/attempts/{attempt_id}/answers` | `{"answers":{"<question_uuid>":"A"}}` | `200`, gộp câu trả lời vào nháp |
| `POST /api/attempts/{attempt_id}/submit` | Không body, `{}`, hoặc body `answers` | `200`, gộp câu cuối, chấm và khóa lượt làm |

`answers` dùng UUID của câu hỏi, không dùng số thứ tự hiển thị. Mỗi request tối đa
40 câu, mỗi đáp án là chuỗi tối đa 2.000 ký tự hoặc `null`; không nhận số/bool,
ký tự NUL, Unicode không hợp lệ hay trường thừa. UUID được chuẩn hóa; hai cách viết của cùng UUID trong một map bị
từ chối. Khi lưu nháp, các câu không gửi giữ nguyên; `null`, `""` hoặc chuỗi chỉ
có khoảng trắng xóa câu trả lời thành `""`. Câu không thuộc lượt làm làm toàn bộ
request thất bại, không lưu một phần.

Nộp bài không body dùng nháp đã lưu. Câu còn thiếu được ghi thành rỗng và tính
sai. Sau khi nộp, PATCH trả `409`; nộp lại với body hợp lệ schema luôn trả kết quả
đầu tiên, bỏ qua đáp án mới. `started_at`/`submitted_at` do server ghi;
`elapsed_seconds` là thời gian đã trôi qua, chưa áp dụng giới hạn thời gian tự nộp.
Phản hồi thành công và lỗi nghiệp vụ của lượt làm có `Cache-Control: no-store`.

Ví dụ PowerShell với ID của một bài đã sinh:

```powershell
$base = 'http://127.0.0.1:8000'
$itemId = '<UUID bài đã kiểm chứng>'
$headers = @{ Authorization = "Bearer $env:API_TOKEN" }
$attempt = Invoke-RestMethod -Method Post -Uri "$base/api/exercises/$itemId/attempts" -Headers $headers
$headers['X-Attempt-Token'] = $attempt.attempt_token
$attemptId = $attempt.attempt_id
$questionId = $attempt.exercise.question_groups[0].questions[0].id
$body = @{ answers = @{ $questionId = 'TRUE' } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Patch -Uri "$base/api/attempts/$attemptId/answers" -Headers $headers -ContentType 'application/json' -Body $body
$submitted = Invoke-RestMethod -Method Post -Uri "$base/api/attempts/$attemptId/submit" -Headers $headers
$submitted.result | ConvertTo-Json -Depth 10
```

Chọn đáp án phù hợp dạng câu thực tế; `'TRUE'` chỉ minh họa cách gửi chuỗi. Có thể
gửi `null` thay chuỗi để xóa nháp, hoặc gọi GET để mở lại lượt làm.

## Dữ liệu trả về và cách chấm

Mỗi phản hồi lượt làm có `attempt_id`, `item_id`, `skill`, `status`, thời điểm,
`elapsed_seconds`, `exercise`, `answers` và `result`. `exercise` chỉ chứa passage/
script, thông tin bài và nhóm/câu hỏi; không có key, giải thích, bằng chứng hoặc
trace/model metadata. Trước khi nộp, `result=null`; `attempt_token` chỉ có trong
phản hồi tạo lượt.

Kết quả sau khi nộp gồm:

| Trường | Ý nghĩa |
|---|---|
| `grading_version` | Quy tắc chấm, hiện là `fixed-key-v1` |
| `raw_score`, `total_questions` | Số câu đúng và tổng số câu; mỗi câu tối đa một điểm |
| `answered_questions` | Số câu có nội dung trả lời |
| `wrong_count`, `unanswered_count` | Số câu đã trả lời sai và số câu bỏ trống, tách riêng |
| `percentage` | `raw_score / total_questions * 100`, làm tròn hai chữ số |
| `band`, `band_reason` | `null`, `partial_practice`: không suy band từ bài ngắn |
| `questions[]` | ID, số câu, dạng, đáp án đã nộp, đáp án đúng, đúng/sai, lý do, giải thích và bằng chứng |

Tổng `raw_score + wrong_count + unanswered_count` bằng `total_questions`.

Quy tắc chung: chuẩn hóa Unicode NFKC, chữ hoa/thường và khoảng trắng. Không chấm
mờ, sửa chính tả, tự bỏ dấu câu hoặc dùng AI để thay đáp án đã kiểm chứng.

| Dạng câu | Quy tắc |
|---|---|
| `true_false_not_given` | Chỉ nhận các nhãn `TRUE`, `FALSE`, `NOT GIVEN`; không nhận `T`/`F`/`NG` |
| `multiple_choice` | So nhãn lựa chọn như `A`, không so với toàn bộ nội dung lựa chọn |
| `matching_headings` | So nhãn tiêu đề đúng của từng câu; không cộng điểm khi chọn sai nhãn |
| `sentence_completion` | So chuỗi đáp án sau chuẩn hóa và kiểm tra `response_limits.max_words` |

Giới hạn từ dùng cùng bộ đếm của validator: từ có gạch nối và từ rút gọn tính một
từ; các giá trị như `1,000`/`3.5` cũng tính một từ. Trường `reason` có thể là
`correct`, `unanswered`, `word_limit_exceeded`, `invalid_option`,
`invalid_classification` hoặc `incorrect`. Bằng chứng có thể là `null`, đặc biệt
với `NOT GIVEN`.

## Lưu trữ và lỗi

Nội dung công khai và key được chụp trong cùng transaction `REPEATABLE READ` lúc
bắt đầu. Lượt đã tạo tiếp tục dùng bản chụp đó nếu bài gốc bị sửa, loại câu hoặc
chuyển trạng thái; bài gốc không còn hợp lệ sẽ không tạo được lượt mới. Xóa một
câu gốc không làm hỏng việc nộp bản chụp cũ; xóa content item đang có lịch sử bị
FK chặn. Nháp, điểm, đáp án từng câu và kết quả lưu trong PostgreSQL, mở lại được
sau khi khởi động lại API. Row lock tuần tự hóa lưu/nộp đồng thời và kết quả đã
nộp không bị cập nhật bởi một lần lưu muộn.

| HTTP | Mã / tình huống |
|---|---|
| `401` | Thiếu/sai bearer khi bật `API_TOKEN` |
| `404` | `exercise_not_found`: không có bài khả dụng; `attempt_not_found`: không có lượt hoặc thiếu/sai token riêng |
| `409` | `exercise_not_gradable`: bản chụp/key không chấm được; `attempt_submitted`: sửa lượt đã nộp |
| `422` | Sai UUID/body/giới hạn, `unknown_question` hoặc `invalid_answer` khi lưu/nộp lần đầu |
| `503` | `database_unavailable`: PostgreSQL/schema chưa sẵn sàng |

Lỗi nghiệp vụ có dạng `{"error":"attempt_submitted","message":"..."}`; lỗi
schema trả `detail` với `type`, `loc`, `msg`, không phản chiếu đáp án/token đầu vào.
Hướng dẫn sinh bài nằm tại [UC-04](uc04.md).
API chuẩn bị dữ liệu cho audio được mô tả tại
[tách script thành lượt người nói](listening-speaker-turns.md).
