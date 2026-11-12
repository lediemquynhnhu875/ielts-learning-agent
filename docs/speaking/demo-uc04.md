# Demo thi thử Speaking — cập nhật 18/10/2026

## Chạy demo

Từ thư mục project, dùng cùng môi trường và requirements trong README:

```sh
.venv/bin/python -m uvicorn ielts_agent.agents.speaking.server:app --host 127.0.0.1 --port 8010
```

Mở `http://127.0.0.1:8010/exam`. Trang `/` vẫn luyện từng câu Part 1/2. **Phiên thi thử chỉ nhận câu trả lời ghi âm**: `kind=mock` buộc `mode=voice`, API trả 422 cho cặp mock+text và endpoint `/text` từ chối mọi phiên mock, kể cả checkpoint cũ. Mỗi lượt ghi âm được Groq STT chép lại; chỉ gửi audio khi bấm Gửi câu trả lời. Lựa chọn **Luyện gõ chữ** tạo `kind=practice` để chạy thử toàn bộ luồng khi chưa có API key — đây không phải một lần thi thử và không có chỉ số Pronunciation, tốc độ hay khoảng ngừng. Trang và script phục vụ kèm `Cache-Control: no-cache`, URL asset gắn mtime, nên tải lại trang là thấy bản mới, không cần hard refresh. Chọn lưu audio trước khi tạo phiên nếu muốn nghe lại sau khi tải lại trang. Audio không chọn lưu sẽ không được ghi vào SQLite; bản thu chưa gửi mất khi đóng trang.

Luồng bình thường có 10 câu: 4 câu Part 1 thuộc 2 chủ đề, 1 cue card Part 2 và 1 câu chốt, 4 câu thảo luận Part 3. Với câu dưới 8 từ, hỏi gợi mở thêm tối đa một lần cho mỗi câu chính; tối đa 20 lượt trả lời. Ngưỡng này là quy tắc demo, không phải quy tắc chấm IELTS. Part 2 có 60 giây chuẩn bị và 120 giây nói, tự bắt đầu/dừng ghi âm khi có quyền mic; có thể bắt đầu sớm. Phiên luyện gõ chữ không dùng thời gian nhập làm chỉ số tốc độ nói.

Sau mỗi lượt, backend lưu câu trả lời và câu hỏi kế tiếp trong một transaction. **Tạm dừng** rồi tải lại trang sẽ khôi phục đúng câu hỏi. **Xuất JSON** dùng contract `ielts-speaking-db-1.0`, gồm `tables` cho các bảng database và `extensions` cho checkpoint/analysis/feedback; không nhúng bytes audio. Chi tiết tại [database-mapping.md](database-mapping.md). State public `speaking_turns` giữ metadata, transcript nằm ở nội dung lượt và export `SPEAKING_TURN.transcript`. Tên field runtime đã ánh xạ theo database; SQLite vẫn đọc checkpoint cũ.

## Module và API

| Module | Trách nhiệm |
| --- | --- |
| `database.py` | Model theo database-design, ánh xạ record/UUID/FK, đổi offsets evidence toàn bài và validator export. |
| `sessions.py` | Điều phối ba phần, trích candidate_points nguyên văn, câu hỏi theo intent, giới hạn lượt, checkpoint SQLite. |
| `question_llm.py` | Viết thân câu hỏi Part 3 bằng model tùy chọn và kiểm tra lại bằng code; hỏi model về trùng nghĩa. |
| `similarity.py` | Cosine TF-IDF cục bộ trên thân câu hỏi để chặn câu lặp trước khi gọi model. |
| `planning.py` | Suy ra hồ sơ điểm yếu từ bản chấm đã hợp lệ, kèm descriptor band kế tiếp. |
| `exam_api.py` | Tạo/đọc phiên, pause/resume, voice/text, lưu audio theo lựa chọn, export và gọi grader. |
| `assessment.py` | Contract FC/LR/GRA/PR, kiểm tra quote/offset/reference/descriptor, flags và tính điểm tổng bằng code. |
| `grading.py` | RAG theo Speaking/criterion, hai lần chấm độc lập và retry validator. |
| `rag.py`, `ingest_rubric.py` | Nhập PDF chính thức, BM25 + LSA + RRF + feature reranking, metadata nguồn và phiên bản. |
| `pronunciation.py` | Azure unscripted continuous, từ/âm vị/prosody, điểm native 0–100 tách khỏi band IELTS. |
| `web/exam.*` | Demo responsive, textarea/recorder, đồng hồ Part 2, lịch sử và kết quả. |

API dưới `/api/exam`:

- `GET /capabilities`: trạng thái grader/corpus và giới hạn của engine.
- `POST /sessions`: `{mode: voice|text, topic_id, save_audio, learner_id?, kind?, thread_id?}`; mặc định `mode=voice`, `kind=mock`, và `kind=mock` chỉ hợp lệ với `mode=voice`; response session có `id`, `attempt_id`, `item_id`. Demo cấp ID khi chưa có ID người học từ backend.
- `GET /sessions/{id}`: state hiện tại và câu trả lời đã gửi; không trả kế hoạch câu hỏi tương lai.
- `POST /sessions/{id}/actions`: `{action, version}`; action=pause/resume/prepare/speak/preview_part3. Yêu cầu preview bị từ chối bằng thông báo, không làm tiến phiên.
- `POST /sessions/{id}/text`: `{question_id, request_id, version, text}`; question_id là `current_question.question_id` (QUESTION.id), khác `current_question.id` (ASKED_QUESTION.id).
- `POST /sessions/{id}/voice`: multipart audio/question_id/request_id/version/keep_fillers.
- `GET /sessions/{id}/audio/{answer_id}`: chỉ trả audio đã được chọn lưu.
- `POST /sessions/{id}/assessment`: chỉ chấm sau khi phiên kết thúc, lưu hai bản chấm và kết quả cuối. Lỗi provider hoặc hết hạn mức token trả `retryable=true`, giữ `status=provisional` và **không** cache, để bấm chấm lại.
- `POST /sessions/{id}/teacher-review`: `{teacher_id, action: approve|edit|reject, note, bands?}` để giải quyết `pending_teacher`. `approve` lấy trung bình A/B, `edit` dùng band giáo viên nhập, `reject` không công bố điểm. Mỗi phiên chỉ nhận một lần.
- `GET /sessions/{id}/weakness-profile`: hồ sơ điểm yếu cho Planning Agent, suy ra từ bản chấm đã hợp lệ.
- `GET /sessions/{id}/export`: dữ liệu phiên, analysis và grading để tích hợp.

Request ID dùng lại cho cùng câu hỏi không tạo thêm lượt trả lời. Version cũ hoặc question_id không đúng trả 409; tải lại phiên trước khi gửi tiếp. SQLite mặc định ở `backend/ielts_agent/agents/speaking/data/sessions.sqlite3`, được gitignore, có thể đổi bằng `SPEAKING_DB_PATH`. Phiên cũ vẫn lưu khi tạo phiên khác; chưa có chính sách hết hạn tự động. Đây là kho demo local, chưa phải kho/trace/hồ sơ UC06 của nhóm. Session UUID là reference riêng của demo, chưa có phân quyền tài khoản; chạy ở loopback theo lệnh trên.

## Cấu hình chấm điểm thật

Chưa cấu hình thì demo vẫn chạy phiên thi, nhưng mọi band=null và nêu rõ lý do. Không có fixture band được hiển thị như kết quả thực.

`.env.example` đã điền sẵn `SPEAKING_GRADER_MODEL=openai/gpt-oss-120b`; chỉ cần `GROQ_API_KEY` là chấm được. Có thể đổi sang chat model khác mà tài khoản Groq có, miễn là model hỗ trợ JSON schema output. Dùng `SPEAKING_DESCRIPTORS_PATH` nếu muốn chỉ định file JSON của nhóm thay cho corpus ingest sẵn. Khởi động lại server sau khi thay cấu hình. Transcript/analysis và descriptors được gửi đến Groq khi bấm **Chạy hai giám khảo**. Adapter dùng **JSON Schema mode** (`response_format={"type":"json_schema"}`) nên cấu trúc phản hồi được provider ràng buộc, rồi code kiểm tra lại; tham khảo [Groq structured outputs](https://console.groq.com/docs/structured-outputs).

### Payload gửi grader và hạn mức token

Prompt chỉ chứa thứ grader cần: với mỗi câu trả lời là transcript nguyên văn, câu hỏi, flags, trạng thái quality và vài số đo tổng hợp; với rubric là `chunk_id`/`criterion`/`band`/`text`. Word timestamps, đoạn VAD, báo cáo âm vị Azure và provenance rubric **không** vào prompt — chúng vẫn nằm đủ trong JSON xuất. Nhờ vậy một phiên 10 câu còn khoảng 4.800 token prompt thay vì vượt hạn mức.

Groq tính `prompt + max_completion_tokens` vào hạn mức token mỗi phút. Trên hạn mức miễn phí 8.000 TPM, hai lượt chấm phải chờ bucket hồi, nên một lần chấm phiên text đo được **khoảng 45–115 giây**; phiên voice có transcript dài hơn nên lâu hơn, và nếu bucket vừa bị việc khác rút cạn thì lần chấm trả về `retryable` thay vì chờ mãi. Code đọc header `x-ratelimit-*` để chờ chủ động, và khi vẫn bị 429 thì chờ theo `retry-after`, tối đa 150 giây cho cả lần chấm; lần chờ đó không tính là một lượt chấm lại. Nếu hạn mức vẫn không đủ, kết quả là `retryable` chứ không phải `pending_teacher`, và không có gì được cache. Chỉnh `SPEAKING_GRADER_MAX_COMPLETION_TOKENS` nếu tài khoản có hạn mức khác.

### Dẫn chứng do code xác định

Grader chỉ trả `answer_id` và `quote`. Code tìm nguyên văn quote trong transcript của chính câu đó để tính `start_char`/`end_char`, điền `turn_id`/`transcript_ref`, và với voice thì lấy `t_start_s` từ timestamp của từ mở đầu quote. Quote không tìm thấy nguyên văn bị trả lại cho grader sửa, không được nắn cho khớp. Lý do: LLM đếm offset Unicode không đáng tin, và đây là chỗ mọi lần chấm thử đầu tiên đều hỏng.

### Phương sai giữa hai giám khảo

Đo thực tế trên cùng một model, cùng payload: hai lượt chấm thường lệch 0–1 band mỗi tiêu chí, và vì ngưỡng UC03 là **lệch từ 1.0 là escalate**, phần lớn phiên thật rơi vào `pending_teacher`. Đó là hành vi đúng thiết kế, không phải lỗi. Vì vậy đường giáo viên xem lại bên dưới là bắt buộc để một phiên thật có điểm. Chưa có benchmark đối chiếu giáo viên nên không kết luận band máy chấm đúng hay sai.

### Kho descriptors

Corpus phải là array các object có `chunk_id` duy nhất, `test_part="speaking"`, `criterion` thuộc FC/LR/GRA/PR, `text` là nội dung descriptor và `version` không rỗng. Có thể bổ sung `band`, nguồn tài liệu hoặc metadata khác. Phải có ít nhất dữ liệu cho FC/LR/GRA. Nhóm chịu trách nhiệm nạp đúng nội dung/band của rubric; module không tự tạo descriptors và kiểm tra metadata không chứng minh tài liệu là chuẩn. Corpus mặc định được nhập bằng `python -m ielts_agent.agents.speaking.ingest_rubric`; có BM25 + vector LSA, RRF và feature reranking theo Speaking/criterion, chưa cần vector database. Xem [pronunciation/RAG](pronunciation-rag.md).

STT mặc định Groq V3 từ 16/10/2026, vẫn tự nhận diện ngôn ngữ. API voice thêm `vocabulary` (tối đa 400 ký tự); giao diện có ô tên riêng để gợi ý cách viết. Đây không phải đáp án tham chiếu. Tên gợi ý chưa khớp transcript sẽ có warning để nghe lại; không tự sửa output. Kiểm tra audio thực và giới hạn tại [báo cáo code-switch](stt-results/user-tests/code-switch-school-review.md).

A/B không xem kết quả của nhau, nhận cùng corpus và dữ liệu phiên. Validator kiểm tra đủ 4 tiêu chí, quote nguyên văn, char offsets Unicode code points 0-based/end-exclusive, turn/reference/version và descriptor refs đúng criterion. Text không được có timestamp. Với voice, timestamp phải trong audio; chưa xác minh căn chỉnh từng quote với âm thanh. GRA chỉ bị chặn khi **transcript không qua được kiểm tra văn bản** (`text_checks_passed=false`) hoặc câu có cờ `low_stt_confidence`; mỗi câu trả lời mang sẵn `usable_for_grammar_evidence` trong payload để grader biết câu nào được trích. Cảnh báo về timestamps (từ quá dài, mốc thời gian lùi) không chặn GRA vì chúng không đụng tới chữ trong transcript — bản trước chặn theo `quality.status=needs_review` khiến **mọi phiên voice thật đều không chấm được**: 6/10 bản thu mẫu là needs_review chỉ vì timing dù transcript đạt hết kiểm tra văn bản. Nếu sai evidence/schema/refs, chấm lại tối đa 2 lần sau lần đầu; lỗi provider không retry hàng loạt. Sau đó chưa đạt trả pending_teacher, không phát hành điểm tổng. Hai band lệch ≥1 ở bất kỳ tiêu chí được chấm nào cũng pending_teacher để nối UC03.

### Giáo viên xem lại

Khi `status=pending_teacher`, trang `/exam` hiện ô **Giáo viên xem lại · UC03**. `approve` công bố trung bình A/B, `edit` công bố band giáo viên nhập, `reject` giữ nguyên chưa công bố. Kết quả ghi `TEACHER_REVIEW`, `RECONCILIATION`, `RECON_CRITERION` và `FINAL_SCORE` với `source=teacher`, `status=final`, `version=2`. Band do giáo viên công bố thay cho cặp máy chấm, kể cả cặp đã lệch quá ngưỡng.

**Demo này không có tài khoản giáo viên.** Endpoint chạy loopback và chỉ dựa vào UUID phiên như mọi endpoint khác, nên bất kỳ ai có link phiên cũng gửi được quyết định. Trước khi dùng thật, nhóm phải gắn xác thực và phân quyền giáo viên.

Trên đường escalate, dẫn chứng đã qua validator, flags và hai gợi ý sửa câu của grader A vẫn được giữ và hiển thị, kèm band riêng của A và B cho từng tiêu chí; chỉ band công bố là bị giữ lại. Khi cả hai bản chấm hợp lệ và lệch dưới ngưỡng, demo lấy trung bình A/B từng tiêu chí. Text lấy trung bình FC/LR/GRA, giữ 2 chữ số thập phân và nhãn tạm tính; đây là policy kỹ thuật chưa hiệu chuẩn. Voice có feedback Azure 0–100 khi được chọn, nhưng PR IELTS vẫn not_assessed/band=null và overall_band=null cho tới khi hiệu chỉnh. Trả gợi ý nâng cấp hai câu khác nhau do grader chọn, cùng vocabulary. Không gọi điểm tạm tính là band IELTS chính thức. Grading hợp lệ/đã chuyển giáo viên được cache theo phiên; cấu hình thiếu không cache để có thể cấu hình rồi thử lại.

## Giới hạn còn lại so với UC04

- Part 3 gắn câu trích từ Part 2/3. Khi có `SPEAKING_QUESTION_MODEL`, thân câu hỏi do model viết và phải qua kiểm tra code (một câu hỏi tiếng Anh 8–30 từ, không hỏi dữ liệu cá nhân, không nhắc band/rubric, không trùng câu đã hỏi); câu trích vẫn do code chèn nguyên văn nên dẫn chứng không bao giờ là chữ của model. Hỏng hoặc bị từ chối thì quay về template, phiên thi không phụ thuộc provider. Chỉ trích tối đa 3 câu đầu mỗi lượt làm candidate_points; chưa tóm tắt ý bằng LLM.
- Chặn trùng ba lớp: text chuẩn hóa, cosine TF-IDF cục bộ trên thân câu hỏi (bỏ phần trích dẫn), và với câu do engine tạo thì hỏi thêm model. Hai câu hỏi chỉ được so với nhau khi trích cùng một đoạn, vì nhiều góc hỏi Part 3 cố ý dùng chung một ý người học. Cosine cục bộ chỉ bắt được câu lặp dùng lại từ vựng; đo trên bộ câu hiện có, các cách diễn đạt lại khác hẳn từ vựng chỉ đạt 0,13–0,58 nên không vượt ngưỡng — lớp model mới là lớp xử lý trùng nghĩa thật, và nó chỉ chạy khi được cấu hình. Chưa có evaluator chứng minh câu hỏi hợp lý. Không tuyên bố đạt mục tiêu 0 câu trùng nghĩa.
- Engine câu hỏi gọi provider ngay trong transaction ghi checkpoint, với timeout 8 giây và fallback template. Chấp nhận được cho demo một người dùng; nếu nhiều người học dùng chung, cần tách lời gọi ra ngoài transaction.
- Flags trả lời ngắn/chuyển tiếng Việt/injection là heuristic; off_topic có thể được grader trả cuối phiên, chưa có agent nhận diện và nhắc ngay. Chưa hỗ trợ UC01 rút gọn.
- Confidence STT hiện null/not_available. Warning chất lượng không được chuyển thành xác suất confidence. Chưa có confidence theo segment từ provider và ngưỡng hiệu chuẩn.
- Voice đã có Azure phân tích âm thanh khi người học chọn gửi; chưa có hiệu chỉnh band PR và benchmark giáo viên. Không dùng điểm native làm band IELTS.
- Có endpoint và ô nhập cho giáo viên xử lý pending_teacher, nhưng **không có xác thực giáo viên**; chưa nối reconciler UC03 và hồ sơ UC06 của nhóm.
- Hồ sơ điểm yếu đã sẵn cho Planning Agent qua API và export, nhưng `write_target=null`: chưa ghi vào database chung hay cập nhật hồ sơ người học của nhóm.
- Chưa có benchmark so giáo viên, đánh giá chất lượng câu hỏi hoặc chứng minh đạt các tỷ lệ UC04. Corpus/model chưa được tự cấu hình bằng tài liệu hoặc model ID đoán trước.

## Kiểm thử

```sh
.venv/bin/python -m pytest backend/tests/speaking -q
.venv/bin/python backend/tests/speaking/browser_exam.py
```

Unit test không gọi Groq: các module chạy phiên thi đặt `SPEAKING_QUESTION_MODEL=""` trong `setUpModule`, vì `ielts_agent.agents.speaking.server` nạp `.env` lúc import. Bộ test chạy bằng `pytest` theo cấu hình `testpaths` trong `pyproject.toml`.

Browser exam mặc định dùng server cổng 8010, có thể đổi `SPEAKING_TEST_BASE`. Test đi qua endpoint text thật, pause/reload/resume, Part 2, Part 3, export, viewport mobile và ghi âm bằng microphone giả. Không gửi audio thật hoặc gọi grader Groq; pipeline voice/grade được kiểm tra bằng stub trong unit tests. Bộ browser luyện cũ chạy bằng `SPEAKING_TEST_BASE=http://127.0.0.1:8010 .venv/bin/python backend/tests/speaking/browser_smoke.py`. Screenshots ở `backend/ielts_agent/agents/speaking/qa/exam-*.png`.
