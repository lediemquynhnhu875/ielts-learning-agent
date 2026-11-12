# Speaking Studio — luyện Part 1/2 và demo thi thử 3 phần

Backend FastAPI và giao diện HTML/JS cùng origin. Trang `/` giữ luồng luyện Part 1/2 với 15 câu hỏi và 6 cue card viết sẵn. Trang `/exam` bổ sung phiên thi ba phần bằng ghi âm — phiên thi thử chỉ nhận câu trả lời nói, gõ chữ chỉ còn là phiên luyện tập `kind=practice` — câu hỏi đào sâu, chấm hai giám khảo và checkpoint local. Module chấm A/B chỉ chạy khi cấu hình model và kho Speaking descriptors; không tạo band từ bộ đếm metrics.

Từ 18/10/2026 repo có sẵn cấu hình chấm: `SPEAKING_GRADER_MODEL=openai/gpt-oss-120b` và `SPEAKING_QUESTION_MODEL=openai/gpt-oss-20b` trong `.env.example`. Bạn chỉ cần `GROQ_API_KEY` của tài khoản có hai model này.

## Phạm vi so với UC04 — cập nhật 18/10/2026

Đã có nền thu âm–STT–VAD, luồng luyện Part 1/2 và demo điều phối phiên thi. [Hướng dẫn demo](demo-uc04.md) mô tả chức năng đang chạy, cấu hình và giới hạn; [meeting-proposal.md](meeting-proposal.md) giữ thiết kế đích và các quyết định cần nhóm chốt.

| Hạng mục UC04 | Hiện trạng |
| --- | --- |
| Part 1: 2–3 chủ đề, tổng 4–6 câu trong phiên | Demo chọn 4 câu chính từ 2 chủ đề; câu quá ngắn được gợi mở thêm tối đa một lần/câu chính. |
| Part 2: cue card, chuẩn bị 60 giây, nói tối đa 120 giây | Đã có trong demo, thêm 1 câu chốt; có thể bắt đầu sớm. |
| Part 3 đào sâu, candidate_points, chặn hỏi trùng nghĩa | Có 4 câu chính, 3 câu sau tham chiếu ý đã trích nếu có. Khi có `SPEAKING_QUESTION_MODEL`, phần thân câu hỏi do LLM viết và phải qua kiểm tra code; câu trích dẫn vẫn do code chèn nguyên văn. Chặn trùng bằng text chuẩn hóa + cosine TF-IDF cục bộ, thêm một lượt hỏi model về trùng nghĩa cho câu do engine tạo. Chưa có evaluator chứng minh độ liên quan. |
| SpeakingSessionState, giới hạn lượt, checkpoint/resume | SQLite local lưu sau mỗi lượt, tối đa 20 lượt; pause/resume và chống gửi trùng bằng request ID/version. |
| Voice → transcript/timestamps/tốc độ/pause | Đã có STT và VAD tách nguồn, kiểm tra chất lượng; chưa giữ confidence từ provider. |
| Chế độ text | Chỉ dành cho phiên luyện tập `kind=practice`; `kind=mock` buộc `mode=voice` và endpoint `/text` từ chối phiên mock. Không tạo metrics audio/timing/confidence, nên không dùng để đánh giá một lần thi thử. |
| RAG Speaking descriptors, A/B độc lập, validator, UC03 | Rubric chính thức, BM25 + LSA + RRF + feature reranking; A/B độc lập, kiểm tra evidence/refs, chấm lại tối đa 2 lần. Chênh ≥1 band chuyển pending_teacher, giải quyết bằng endpoint giáo viên trong demo; chưa nối hệ thống UC03 của nhóm. |
| SpeakingAssessment, điểm tổng, nâng cấp 2 câu yếu | Có contract và pipeline; chỉ trả điểm/gợi ý từ hai grader hợp lệ. Phiên gõ chữ tính trung bình FC/LR/GRA, lưu hai chữ số thập phân theo policy kỹ thuật. Offsets dẫn chứng do code tra trong transcript, không nhận offsets model tự khai. |
| Lưu transcript, hai bản chấm, kết quả cuối và lỗi UC06 | Demo lưu local, audio chỉ lưu khi chọn; chưa nối backend/hồ sơ UC06 của nhóm. |
| Hồ sơ điểm yếu cho Planning Agent | `GET /api/exam/sessions/{id}/weakness-profile` và `extensions.weakness_profile` xếp hạng tiêu chí yếu, kèm dẫn chứng và nguyên văn descriptor của band kế tiếp. Chỉ suy ra từ bản chấm đã qua validator; `write_target` vẫn null vì chưa có database chung. |
| Benchmark band đối chiếu giáo viên và eval UC04 | Chưa chạy; sample STT/test kỹ thuật không chứng minh đạt tiêu chí agent. |

Theo UC04, phiên luyện gõ chữ bỏ PR và tính điểm tổng tạm tính từ FC/LR/GRA khi đủ dữ liệu; voice chấm PR với limitations về nguồn dữ liệu. Demo đã tích hợp feedback âm thanh Azure unscripted tùy chọn, thang 0–100. PR chưa hiệu chỉnh sang band IELTS nên PR band/overall voice vẫn null. RAG có corpus chính thức sau khi ingest; chấm A/B cần thêm model Groq. Xem [cấu hình pronunciation và RAG](pronunciation-rag.md), cùng [đánh giá retrieval](rag-evaluation.md).

`quality.status=ok` không phải confidence cao và không chứng minh transcript đúng audio. Schema STT vẫn là 1.2, thêm confidence=null/source=not_available; contract assessment/export `ielts-speaking-db-1.0` thuộc API thi thử, không thay cấu trúc chính của `/api/transcribe`.

### Chấm lại và tải audio

Trạng thái chấm hiển thị ngay cạnh nút và kèm mã lần chấm đang xem. Lần thử
thất bại được lưu trong `session.last_grading_attempt` để xem lại sau khi tải
trang; kết quả cũ vẫn giữ nguyên. Bước chọn tool dùng schema nhỏ riêng; sau khi
đọc đủ dữ liệu, model trả trực tiếp schema SpeakingAssessment. Ngân sách output
Qwen được tách khỏi model reasoning; GPT-OSS mặc định reasoning thấp nếu chưa
cấu hình. Payload bỏ trường rỗng và định dạng JSON gọn, giữ nguyên transcript
và nội dung descriptors.

- **Chấm lại bằng loop mới** chạy lại hai giám khảo trên transcript đã lưu,
  kể cả phiên không giữ audio. API: `POST /api/exam/sessions/{id}/assessment`
  với JSON `{"force": true}`. Không truyền body thì vẫn dùng bản chấm đã lưu.
- Khi chấm lại thành công, bản cũ và quyết định giáo viên chuyển vào
  `grading_history`; quyết định cũ không áp dụng cho bản mới. Lấy lịch sử qua
  `GET /api/exam/sessions/{id}/assessment-history`. Nếu model lỗi hoặc thiếu hai
  bản chấm hợp lệ, kết quả cũ được giữ nguyên. Nếu có người duyệt/chấm đồng thời,
  API trả 409 thay vì ghi đè kết quả vừa thay đổi.
- Chọn lưu audio lúc tạo phiên, hoặc bật **Lưu audio cho các câu trả lời tiếp
  theo** trong phiên đang làm. Không tự bật lưu; tắt chỉ dừng lưu các lượt sau,
  không xoá bản đã đồng ý giữ. API đổi lựa chọn: `POST .../audio-preference`,
  JSON `{"enabled": true, "version": <session.version>}`.
- Mở từng câu trong **Câu trả lời đã gửi** để nghe và bấm **Tải audio câu này**.
  Nếu mọi câu đều có audio, có thêm **Tải audio cả phiên (WAV)**. Có thể tải bản
  thu nháp bằng **Tải bản thu này** trước khi gửi.
- Audio của các lượt đã gửi khi không bật lưu không thể khôi phục từ transcript.
  Không cần audio để chấm lại FC/LR/GRA; chính sách không chấm PR vẫn giữ nguyên.

### Vòng lặp giám khảo Speaking

Từ phiên bản prompt `speaking-grader-agent-0.5`, mỗi giám khảo A/B chạy một
vòng lặp riêng trong `grader_agent.py`: model chọn tool → code thực thi → model
đọc kết quả → chọn tool tiếp hoặc nộp bản chấm. Giao thức là JSON action có
schema (`tools` hoặc `final`), sử dụng transport Groq hiện có, chưa dùng LangGraph.

Hai tool chỉ đọc:

- `get_transcript_evidence`: lấy nguyên văn và thông tin chất lượng của các
  answer ID thuộc attempt hiện tại; không nhận learner ID hay đường dẫn tùy ý.
- `retrieve_descriptors`: lấy Speaking descriptors FC/LR/GRA đã được RAG xếp
  hạng, giữ toàn bộ thang band cho mỗi tiêu chí được yêu cầu.

Model có thể yêu cầu cả hai tool trong một bước. Chưa đọc đủ câu trả lời và
rubric của ba tiêu chí thì code từ chối kết thúc. Mỗi lượt sửa có tối đa 6 bước
model và 12 tool call; bản chấm không hợp lệ được sửa tối đa 2 lần. Hết giới hạn
thì chuyển trạng thái cần giáo viên xem; lỗi provider vẫn giữ khả năng thử lại.
Validator evidence/refs và cách tính điểm tổng giữ nguyên; PR vẫn không chấm band.

Skill được nạp từ `skills/speaking-assessment/SKILL.md`. Mỗi bản chấm có
`graders[].attempts[].agent_trace`: hash skill, lượt model, token usage nếu
provider cung cấp, tên tool, ID bằng chứng/chunk, lỗi và thời gian. Trace này
không ghi transcript hay nội dung rubric; các trường kết quả/export khác vẫn
theo chính sách dữ liệu hiện có. `/api/exam/capabilities` công bố cấu hình loop.

Loop bật mặc định, không cần biến môi trường mới. Cần khởi động lại server.
Luồng thành công thông thường dùng ít nhất 2 lời gọi model mỗi giám khảo nên
tốn thêm token/thời gian so với chấm một lần. Test offline:

```sh
.venv/bin/python -m pytest backend/tests/speaking/test_grader_agent.py -v
```

### Bộ sinh dữ liệu giả lập

`backend/ielts_agent/agents/speaking/synth/` hiện thực phần Speaking của
`generate-format.docx`: ngân hàng đề do LLM sinh (10 bộ đề), 18 phiên benchmark,
54 bộ placement, judge lọc mẫu và phiếu chấm mù cho giáo viên. Output đã sinh nằm
trong `synth/out/`; nhật ký gốc `gen_jobs.sqlite3` và các lần chạy cũ
`archive-v*` không đẩy lên repo, audit trail là `out/gen_jobs.jsonl`. Cách chạy,
quy tắc chọn đề và các chỗ lệch so với đặc tả xem
[README của synth](../../backend/ielts_agent/agents/speaking/synth/README.md).

## Contract dữ liệu theo database-design

Từ 16/10/2026, cả hai nút xuất JSON dùng `schema_version=ielts-speaking-db-1.0`: `tables` chứa các row SESSION/ATTEMPT/ANSWER/SPEAKING_TURN và các bảng chấm điểm đúng tên cột trong `database-design.docx`. Metrics, checkpoint và gợi ý sửa câu nằm riêng trong `extensions`. Đây là thay đổi định dạng export; JSON cũ được giữ nguyên.

Xem [bảng ánh xạ database](database-mapping.md), [JSON Schema](database-schema.json) và [ví dụ text giả lập](examples/database-export-text.json). Module contract ở `database.py`; endpoint `GET /api/speaking/database-schema` cung cấp schema máy đọc được. Endpoint export chưa ghi vào database chung của nhóm.

API phiên thi đổi khóa chính thành `session.id`, bổ sung `attempt_id`, `item_id`, `kind`, `thread_id`. Câu trả lời dùng `id/response`, lượt nói ở `speaking_turn.id`, câu hỏi có `id` của ASKED_QUESTION và `question_id` của QUESTION. UI đã cập nhật; checkpoint cũ được đọc qua adapter để giữ phiên và audio. Tạo phiên có thể truyền learner_id/thread_id của backend nhóm.

## Khởi động

Từ thư mục project:

```sh
python -m pip install -e '.[speaking,dev]'
```

Backend đọc `GROQ_API_KEY` từ biến môi trường hoặc `.env` ở thư mục project. Key chỉ được sử dụng ở backend, không gửi tới frontend, không xuất trong JSON và không được commit. Biến môi trường có ưu tiên hơn `.env`.

Để nhập key trong terminal zsh mà không lưu key vào lịch sử lệnh:

```zsh
read -s "GROQ_API_KEY?Nhập Groq API key: "
export GROQ_API_KEY
echo
.venv/bin/python -m uvicorn ielts_agent.agents.speaking.server:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`. Nếu cổng đang được dùng, chọn cổng khác. Nếu muốn giữ key qua các lần khởi động, điền `GROQ_API_KEY=...` vào `.env` bằng trình soạn thảo; `.env.example` là mẫu và `.gitignore` đã loại `.env`. Nếu server chưa có key, thêm `.env` rồi tải lại trang để backend nhận key mới. Nếu thay key đã nạp hoặc thay biến môi trường, khởi động lại server; biến môi trường đã tồn tại không bị `.env` ghi đè.

Khi backend chưa có key, vẫn xem được các kết quả Groq đã lưu trong **Mẫu đối chiếu đã lưu**. Các mẫu này có nhãn riêng và không được thêm vào lịch sử câu trả lời mới. Khi gửi audio thật mà chưa có key, backend trả lỗi 503, giữ bản thu ở trình duyệt để gửi lại.

## Luồng sử dụng

1. Chọn chủ đề và câu hỏi. Có 15 câu hỏi, 5 câu/chủ đề.
2. Ghi âm bằng MediaRecorder hoặc chọn audio có sẵn. Trình duyệt yêu cầu quyền microphone; localhost hoặc HTTPS là cần thiết cho ghi âm. Hỗ trợ WebM, M4A, MP4 audio, WAV, MP3, OGG và FLAC.
3. Nghe lại bản thu. Chọn prompt giữ filler nếu đang thử nghiệm, sau đó gửi câu trả lời. Audio được gửi đến Groq, không tự động gửi khi chỉ ghi âm hoặc nghe lại.
4. Xem transcript, metrics và các cảnh báo. Với timestamps hợp lệ, bấm từng từ trong transcript để nghe từ vị trí đó.
5. Chuyển câu và tiếp tục phiên. **Xuất kết quả** tải JSON database của mọi lượt trả lời đã gửi; câu hỏi, transcript và các FK nằm trong `tables`, analysis STT/VAD và thời gian xử lý nằm trong `extensions.analysis`.

Lịch sử và audio chỉ giữ trong bộ nhớ của tab; đóng hoặc tải lại trang sẽ mất phiên. JSON xuất không chứa audio. Backend xử lý audio bằng file tạm rồi xóa sau lời gọi Groq/Azure được chọn, không tạo kho audio lâu dài. Chức năng lưu vào hồ sơ người học cần tích hợp với backend của nhóm ở bước sau.

Để giữ audio, bấm nút biểu tượng tải xuống **Tải audio** ở bên phải tên bản thu, phía trên thanh nghe lại. Nút hoạt động với bản thu nháp, câu trả lời đã gửi (mở từ lịch sử) và audio mẫu. Định dạng được giữ theo audio gốc, không chuyển đổi nội dung. Audio được tải riêng, còn **Xuất kết quả** tải JSON. Tải audio trước khi đóng hoặc tải lại trang; menu mặc định của thanh nghe lại có thể không cung cấp nút tải trên một số trình duyệt.

## Part 2

1. Chọn tab **Part 2**, rồi chọn cue card hoặc dùng nút đổi đề ngẫu nhiên. Mỗi đề gồm chủ đề chính, 3 gợi ý và yêu cầu giải thích.
2. Bấm **Chuẩn bị 1 phút**. Trình duyệt xin quyền mic trước khi bộ đếm bắt đầu; mic chưa được thu âm trong giai đoạn chuẩn bị. Có thể ghi chú tối đa 2.000 ký tự.
3. Khi hết 60 giây, hệ thống tự bắt đầu thu âm. Có thể bấm **Bắt đầu nói** sớm hoặc hủy chuẩn bị. Bấm **Bắt đầu nói** ngay từ đầu sẽ bỏ bước chuẩn bị và ghi nhận thời gian chuẩn bị bằng 0.
4. Đồng hồ nói đếm ngược từ 2 phút; hết giờ hệ thống tự dừng. Có thể dừng sớm, nghe lại và gửi bài bằng luồng Groq hiện có.
5. Có thể dùng audio thu sẵn để thử Part 2. Backend giới hạn 120 giây, cho phép thêm tối đa 0,5 giây để nhận đoạn MediaRecorder cuối; bản thu dài hơn bị từ chối trước khi gọi Groq.

Ghi chú và thời gian chuẩn bị được chụp lại khi bắt đầu thu âm, kèm trong kết quả và JSON xuất. Thời gian chuẩn bị là số liệu trình duyệt gửi, chưa dùng làm căn cứ chấm điểm. Ghi chú không được thêm vào prompt STT. Khi dùng file có sẵn, thời gian chuẩn bị là 0.

Chuyển Part/cue card giữ bản thu nháp và ghi chú theo từng đề trong tab. Trong khi chuẩn bị hoặc ghi âm, điều khiển đổi đề/Part bị khóa để tránh gán audio cho sai đề. Đổi sang Part 1 để tiếp tục luyện mà vẫn giữ lịch sử chung.

JSON xuất mới dùng `tables.SPEAKING_TURN[].part` để xác định từng phần; không còn `parts/part` ở top-level. Đề/cue card nằm trong `tables.CONTENT_ITEM[].body.questions`. Đóng tab/tải lại vẫn làm mất phiên chưa xuất, như Part 1.

## Metrics VAD và kiểm tra STT

### Giữ ngôn ngữ gốc khi chép lời

STT tự nhận diện ngôn ngữ thay vì ép `language="en"`. Groq dùng endpoint `audio.transcriptions`, không dùng translations; local dùng `task="transcribe"`, `language=None` và `multilingual=True` để nhận diện lại theo segment. Từ 16/10/2026, Groq mặc định `whisper-large-v3` sau khi tái hiện lỗi Turbo dịch câu có tên trường tiếng Việt trên bản thu thực. Có thể đổi model bằng `SPEAKING_STT_MODEL`; đây không phải cam kết V3 đúng mọi audio. Prompt filler chỉ còn danh sách tiếng đệm, không dùng câu ví dụ đầy đủ. Tham khảo [Groq speech-to-text](https://console.groq.com/docs/speech-to-text) và [faster-whisper](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py).

Không có bước dịch hoặc sửa tiếng Việt thành tiếng Anh trong pipeline. Transcript và word timestamps giữ nội dung provider trả về; analysis dùng Unicode để không làm mất dấu tiếng Việt. Response live và `/api/health` có `transcription_policy=original_language_context_v2` cùng model thực tế để kiểm tra server đã nạp bản sửa. Chính sách này áp dụng cho cả luyện từng câu và thi thử `/exam`.

STT vẫn có thể nhận sai hoặc bỏ từ, nhất là khi chuyển ngôn ngữ rất ngắn; auto-detection không bảo đảm chép chính xác mọi từ. Cần nghe lại audio để xác nhận. Kết quả benchmark cũ được thu với cấu hình ép tiếng Anh/prompt cũ và không được viết lại; muốn kiểm tra bản sửa phải gửi lại audio. Sau khi cập nhật code, khởi động lại server để nạp cấu hình mới.

Trong cả hai giao diện có ô **Tên riêng cần nhận dạng (tùy chọn)**, ví dụ chỉ nhập `Ngô Gia Tự`. Field `vocabulary` tối đa 400 ký tự được gửi làm gợi ý cách viết trước STT, không thay thế transcript sau nhận dạng. Ngăn cách nhiều tên bằng dấu phẩy/chấm phẩy/xuống dòng. Nếu tên gợi ý chưa xuất hiện nguyên văn, response có warning `vocabulary_needs_review`; điều đó không chứng minh người học đã nói tên này hoặc model sai. Không nhập cả câu đáp án vào prompt.

Kết quả kiểm tra bản thu 8,28 giây: [báo cáo code-switch](../stt-results/user-tests/code-switch-school-review.md). Turbo tái hiện lỗi dịch sang tiếng Việt; V3 giữ phần tiếng Anh nhưng tên trường vẫn chưa chính xác. Auto-detect, prompt và unit test chưa giải quyết hoàn toàn khả năng chép nguyên văn; cần đối chiếu audio trước khi dùng làm dẫn chứng chấm.

### Chất lượng và chỉ số

- Đo thời lượng audio bằng giải mã audio thực tế, không tin duration do STT trả về.
- Giới hạn audio 24 MB; Part 1 tối đa 180 giây, Part 2 tối đa 120 giây với dung sai 0,5 giây; từ chối file không đọc được, quá ngắn hoặc gần như im lặng.
- Kiểm tra timestamps không phải số, NaN/Infinity, thời gian âm, end trước start, vượt audio hơn 0,1 giây và start bị lùi hơn 0,02 giây.
- Kiểm tra transcript không khớp danh sách từ hoặc câu từ 4 từ trở lên lặp ít nhất 3 lần. Đây là dấu hiệu cần xem lại, không phải bằng chứng chắc chắn STT bịa nội dung. Không tự xóa/sửa transcript.
- Từ có thời lượng bằng 0 khiến metrics STT bị bỏ. Từ kéo dài ≥ 1,5 giây hoặc bao gồm phần lớn khoảng không nói theo VAD được cảnh báo để kiểm tra.
- Lỗi nghiêm trọng: `quality.timing_valid=false`, `metrics.timing=null`. Cảnh báo nhẹ có thể giữ STT để đối chiếu nhưng `quality.status=needs_review`. Không cắt hoặc sắp xếp timestamps để tạo dữ liệu có vẻ hợp lệ.
- Filler chỉ đếm các tiếng đệm được nhận dạng; không coi mọi `like` là filler. Lặp từ chỉ đếm từ giống nhau liền nhau. Cả hai còn phụ thuộc chất lượng STT.
- `metrics.timing` giữ pause/tốc độ theo timestamps STT. `metrics.audio_timing` dùng Silero VAD v6 trên mono 16 kHz để đo khoảng không nói nội bộ ≥ 0,5 giây; phần đầu/cuối và vùng giọng nói giữ riêng. Không cắt audio gửi Groq.
- Tốc độ VAD dùng cửa sổ đầu–cuối giọng nói, gồm pause nội bộ, không chia cho thời gian phát âm thuần. Nó vẫn dùng số từ STT; khi nội dung có vấn đề, tốc độ có thể null trong khi pause VAD vẫn hiển thị.
- VAD lỗi hoặc không phát hiện lời nói: unavailable/no_speech, không giả số liệu bằng 0. VAD cũng chỉ là ước lượng; xem đối chiếu VAD/STT trên UI.
- `metrics.disfluency_candidates` nhận lặp cụm 2–4 token và dấu hiệu như `I mean`, `sorry` hoặc từ nối được dùng lại. Đây là candidate cần xác minh, không phải lỗi đã kết luận. Token indices không tự tương đương word indices.
- `quality.status=ok` / `text_checks_passed=true` chỉ nghĩa là qua kiểm tra sơ bộ, không chứng minh transcript hoặc phát âm chính xác. `evidence_review_word_indices` chỉ từ cần nghe lại trước khi dùng làm dẫn chứng.
- Metrics STT/VAD không tự tính band hoặc chấm âm vị. Feedback pronunciation dùng Azure khi được chọn; không dùng transcript làm bằng chứng ngữ pháp chắc chắn khi chưa xác minh audio.

## API để thống nhất với nhóm

FastAPI cung cấp tài liệu ở `/docs`.

- `GET /api/health`: trạng thái backend và key đã được cấu hình hay chưa, không trả key.
- `GET /api/questions`: các chủ đề và câu hỏi Part 1.
- `GET /api/cue-cards`: 6 cue card Part 2 và giới hạn thời gian chuẩn bị/nói.
- `POST /api/transcribe`: multipart `audio`, `question_id`, `keep_fillers`; Part 2 thêm `preparation_seconds` (0–60) và `notes` (tối đa 2.000 ký tự); cả hai phần hỗ trợ `vocabulary` (tối đa 400 ký tự). Part 1 vẫn dùng request cũ được.
- `GET /api/samples`: danh sách benchmark sẵn có.
- `GET /api/samples/{sample}?keep_fillers=false`: kết quả benchmark được kiểm tra lại.
- `GET /api/samples/{sample}/audio`: nghe audio mẫu.

Ví dụ rút gọn kết quả `/api/transcribe` (không phải dữ liệu của một lượt thu thật):

```json
{
  "schema_version": "1.2",
  "part": 1,
  "source": "live",
  "backend": "groq",
  "model": "whisper-large-v3-turbo",
  "question": {"id": "study-1", "text": "Do you work or are you a student?"},
  "keep_fillers": false,
  "audio_seconds": 23.36,
  "processing_seconds": 1.89,
  "transcript": "...",
  "words": [{"word": "I", "start": 0.1, "end": 0.3}],
  "quality": {
    "status": "needs_review",
    "timing_valid": false,
    "text_checks_passed": false,
    "issues": [{"code": "transcript_word_mismatch", "severity": "error", "message": "...", "word_indices": []}],
    "evidence_review_word_indices": [],
    "repeated_sentences": []
  },
  "metrics": {
    "word_count": 1,
    "filler_count": 0,
    "adjacent_repetitions": [],
    "timing": null,
    "audio_timing": null,
    "disfluency_candidates": {"repeated_phrases": [], "repair_candidates": []}
  }
}
```

Khi hợp lệ, `metrics.timing` có `speech_seconds`, `words_per_minute`, `pause_count`, `pause_seconds`, `longest_pause_seconds`, `pauses`. `pauses` giữ cấu trúc của script thử nghiệm hiện có: `after`, `at`, `length`.

Response Part 2 có `part: 2`; `question` chứa đầy đủ `id`, `part`, `title`, `text`, `points`, `explain`; thêm `preparation: {seconds, notes, limit_seconds: 60}` và `speaking_limit_seconds: 120`. Các trường transcript, words, quality và metrics dùng cùng schema với Part 1.

Schema 1.2 bổ sung audio_timing, disfluency_candidates, severity của issue và các fields quality mới. processing_seconds đo riêng STT; pipeline_processing_seconds là tổng xử lý backend; VAD có thời gian riêng. JSON xuất mới giữ riêng hai nguồn metrics. File xuất cũ không bị ghi đè.

Đề xuất trao đổi với Writing/Planning: [docs/meeting-proposal.md](meeting-proposal.md). Phần đã triển khai và API thi thử được ghi riêng trong [hướng dẫn demo](demo-uc04.md); chưa nối backend nhóm hoặc dịch vụ pronunciation.

## Kiểm thử

```sh
.venv/bin/python -m pytest backend/tests/speaking -q
```

200 test dùng dữ liệu benchmark, audio người dùng, SQLite tạm và stub nhà cung cấp; không gọi Groq thật. Ngoài các nhóm STT/VAD/API, phiên thi, pronunciation/RAG, ngôn ngữ, database contract/export, engine câu hỏi và payload chấm/dẫn chứng/hạn mức token/giáo viên/planning, có 11 test vòng lặp giám khảo, 7 test chấm lại/tải audio và 57 test bộ sinh dữ liệu. Các module test chạy phiên thi đặt `SPEAKING_QUESTION_MODEL=""` trong `setUpModule` vì `ielts_agent.agents.speaking.server` nạp `.env` khi import; nếu không, engine câu hỏi sẽ gọi Groq thật trong lúc test. Test ngôn ngữ kiểm tra request không ép tiếng Anh/không gọi translations, local dùng transcription đa ngôn ngữ, Unicode và giữ output Việt/Anh qua cả hai API. Unit tests dùng provider stub; kiểm tra audio thực riêng được ghi trong báo cáo code-switch, không suy ra độ chính xác chung từ một bản thu. Hướng dẫn browser test thi thử tại [demo-uc04.md](demo-uc04.md#kiểm-thử).

Kiểm tra giao diện với server đang chạy ở cổng 8000:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python backend/tests/speaking/browser_smoke.py
```

Browser test dùng microphone giả và stub response thành công ở frontend; kiểm tra thêm lỗi thiếu key trên backend thật khi chưa cấu hình key. Part 2 dùng đồng hồ tăng tốc để kiểm tra chuẩn bị 60 giây, tự bắt đầu ghi âm, tự dừng sau 120 giây, hủy chuẩn bị, bắt đầu nói sớm và xuất JSON phiên hỗn hợp. Test không gửi audio tới Groq. Screenshot desktop/mobile được lưu trong `backend/ielts_agent/agents/speaking/qa`.
