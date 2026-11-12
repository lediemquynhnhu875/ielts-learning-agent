# Tích hợp Pronunciation và RAG

## Phương pháp đã chọn

Dùng **Azure Pronunciation Assessment, unscripted en-US**, cho feedback âm thanh của câu trả lời Speaking. Groq tiếp tục chép nguyên ngôn ngữ người học nói; VAD đo vùng nói/khoảng không nói. Azure nhận PCM mono 16 kHz, dùng continuous recognition cho mọi clip, bao gồm Part 2 trên 30 giây. `reference_text=""`, `enable_miscue=False`; không biến transcript Groq thành bài đọc chuẩn. Prosody bật cho en-US theo khả năng SDK. Locale này là cấu hình công cụ, không phải yêu cầu người học dùng giọng Mỹ.

Azure phù hợp bước thử nghiệm này vì có Speech SDK, word/phoneme accuracy, stress/intonation feedback và continuous mode. Speechace cũng phù hợp và có thang điểm nhà cung cấp, nhưng chưa tích hợp hai dịch vụ song song khi chưa có bộ đối chiếu để lựa chọn theo chất lượng thực tế. Đây là lựa chọn triển khai đầu tiên, chưa phải kết luận Azure chính xác hơn Speechace trên người Việt.

Nguồn: [Azure pronunciation assessment](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-pronunciation-assessment?pivots=programming-language-python), [Speechace API](https://api-docs.speechace.com/).

Kết quả `analysis.pronunciation` gồm status/provider/locale/mode, scores 0–100, từng segment, từ, âm vị, error type và mốc giây trên clip gốc. Các scores toàn clip là **trung bình score của segment theo số từ**, được ghi rõ bằng `aggregation=word_count_weighted_segment_mean`; không nhận là công thức tổng hợp chính thức của Azure. Một chỉ số không được provider trả về giữ null; lỗi dịch vụ hoặc không có kết quả không tạo điểm 0. Audio có chuyển ngôn ngữ/tên riêng cần nghe lại, không tự coi nhãn `Mispronunciation` là lỗi đã xác nhận. Các đoạn có kết quả không chứng minh toàn clip đã được nhận dạng chính xác.

`recognized_text` của Azure chỉ nằm trong segment phục vụ đối chiếu âm thanh. `transcript` / `ANSWER.response` vẫn là nguyên kết quả Groq; không có bước dịch, thay tên trường hoặc sửa câu dựa trên Azure.

**Chưa chuyển native score sang band IELTS.** `ielts_band=null`, `calibration_status=not_calibrated`; `GRADING_CRITERION` PR vẫn band=null/status not_assessed, voice overall=null. Có chấm phát âm ở thang của công cụ, nhưng chưa có band PR tin cậy. RAG PR trả các descriptor tham khảo, không suy ra band người học từ thứ hạng tìm kiếm hoặc điểm Azure. Không chia điểm 100 cho 10.

## Cấu hình và chạy

```bash
python -m pip install -e '.[speaking,dev]'
.venv/bin/python -m ielts_agent.agents.speaking.ingest_rubric
.venv/bin/python -m uvicorn ielts_agent.agents.speaking.server:app --host 127.0.0.1 --port 8000
```

Điền `.env` bằng trình soạn thảo, không đặt key trong frontend hoặc file JSON xuất:

```dotenv
AZURE_SPEECH_KEY=<key của Azure Speech resource>
AZURE_SPEECH_REGION=<region của resource, ví dụ southeastasia>
SPEAKING_GRADER_MODEL=qwen/qwen3.8-27b
# Không bắt buộc. Grader B chạy model thứ hai để có hạn mức token riêng:
SPEAKING_GRADER_MODEL_B=
# Không bắt buộc. Viết thân câu hỏi Part 3 và kiểm tra trùng nghĩa:
SPEAKING_QUESTION_MODEL=openai/gpt-oss-20b
# Không bắt buộc nếu dùng corpus mặc định từ ingest:
SPEAKING_DESCRIPTORS_PATH=
```

Groq tính hạn mức **theo từng model**: free tier đo được 8000 token/phút và 200000 token/ngày cho mỗi model. Vì vậy engine câu hỏi không ăn vào hạn mức của grader, và đặt `SPEAKING_GRADER_MODEL_B` khác model A cho hai giám khảo hai túi token riêng, không phải chờ nhau.

Số đo trong môi trường này, mỗi lần chấm một phiên 10 lượt (prompt ~5200 token):

| Model | Token/lần chấm | JSON schema | Ghi chú |
| --- | --- | --- | --- |
| `qwen/qwen3.8-27b` | ~5900 | đạt | Không sinh reasoning token nên rẻ nhất; một phiên đủ hai giám khảo ~12k token |
| `openai/gpt-oss-120b` | ~7900 | đạt | Reasoning token chiếm 1300–2000; bản chấm chi tiết hơn |
| `openai/gpt-oss-20b` | — | **hỏng** | Trả `json_validate_failed` với schema chấm; chỉ dùng cho engine câu hỏi |

Khi hết hạn mức ngày, Groq trả 429 với `tokens per day (TPD)`. Chờ trong một request không giải quyết được, nên code báo thẳng thời điểm mở lại và gợi ý đổi model thay vì ngủ chờ; phiên giữ trạng thái `provisional`, `retryable=true` và không được cache.

Groq vẫn cần `GROQ_API_KEY` như trước. Khởi động lại server sau khi đổi cấu hình. `/api/health` và `/api/exam/capabilities` chỉ trả trạng thái configured, không trả key. Chỉ cài requirements cơ bản vẫn chạy STT; nếu thiếu Speech SDK/key/region, UI vô hiệu hóa lựa chọn Azure. Azure Speech resource cần được tạo riêng trong tài khoản nhóm; code không tạo tài nguyên hay phát sinh lời gọi kiểm thử audio tự động.

Trên `/` và `/exam`, chọn **Gửi bản thu tới Azure…** trước khi gửi câu trả lời. Ô mặc định tắt, tách khỏi lựa chọn lưu audio. Chỉ ghi âm/nghe lại không gọi Azure. API form `pronunciation_consent=true` cho phép gửi clip của lượt hiện tại, không áp dụng ngược cho audio đã lưu. Khi false, code dừng trước mọi lời gọi Speech SDK. File WAV tạm được xóa sau xử lý; việc lưu audio lâu dài vẫn theo `save_audio`. Chính sách lưu dữ liệu của nhà cung cấp cần được nhóm xem trong tài khoản dịch vụ.

Nếu Azure lỗi, STT vẫn trả kết quả và pronunciation.status=unavailable. Các trạng thái khác: not_requested, not_configured, no_speech, assessed. Không tự gọi lại service tính phí hoặc chấm lại bản thu cũ khi export/resume.

## Kho rubric và truy xuất

British Council giới thiệu [Speaking descriptors trong trang assessment](https://takeielts.britishcouncil.org/teach-ielts/test-information/assessment). Ingest ưu tiên [PDF British Council](https://takeielts.britishcouncil.org/sites/default/files/%5Bdownloads%5D/ielts_speaking_band_descriptors.pdf); nếu bị chặn/không còn PDF, tải [PDF IELTS.org chính thức](https://ielts.org/cdn/ielts-guides/ielts-speaking-band-descriptors.pdf). Lần chạy trong môi trường này British Council trả HTTP 403, nên corpus dùng URL IELTS.org; không ghi giả rằng file đã tải từ British Council hay đã kiểm chứng hai file giống byte nhau.

Parser tách theo **ô bảng: một tiêu chí × một band**, tổng 40 chunks cho FC/LR/GRA/PR, band 0–9. Band 0 là ô gộp, được giữ nội dung chung cho cả bốn tiêu chí. Parser yêu cầu đủ 40 khóa duy nhất, thiếu ô hoặc layout thay đổi thì báo lỗi thay vì index dữ liệu lệch cột. Đã đối chiếu trực quan trang bảng đầu với text extraction; chưa phải quy trình rà soát thủ công toàn bộ rubric.

Metadata: `chunk_id`, `test_part`, `criterion`, `band`, `version` theo SHA-256 PDF, `source_url` thực tải, `page` (số trang PDF kể cả bìa), `source_sha256`, publisher/rights và reference_url British Council. Manifest ghi rõ fallback_used/thời điểm/hash. PDF/corpus ở `.cache/rag/`, được gitignore; không gán giấy phép mở cho tài liệu IELTS. Có thể nhập PDF đã tải bằng `--pdf <path> --source-url <URL chính thức>` nếu máy không truy cập được nguồn.

Truy vấn dùng BM25 + vector **LSA cục bộ** (SVD trên TF-IDF, tối đa 16 chiều), hợp nhất bằng Reciprocal Rank Fusion, rồi rerank bằng lexical coverage và cosine. Đây là hybrid retrieval nhẹ, không phải pretrained sentence embedding/cross-encoder. Không cần vector database hay gửi transcript tới dịch vụ embedding. Corpus nhỏ nên index được cache trong process; khởi động mới sẽ dựng lại.

Khi chấm A/B, filter `speaking + criterion`, xếp hạng bằng khái niệm tiêu chí và transcript. **Giữ toàn bộ thang band của tiêu chí** trong context vì rubric chỉ có 10 đoạn/tiêu chí; không loại band yếu/mạnh dựa trên độ giống từ vựng. Prompt chỉ nhận `chunk_id`, `criterion`, `band` và `text` của mỗi đoạn: nguồn, SHA-256, trang, publisher và rights không vào prompt mà vẫn đi đủ vào `DESCRIPTOR_CHUNK`, `extensions.rubric_text` và `assessment.descriptor_sources`. Provenance lặp lại 30 lần chiếm phần lớn hạn mức token mà không giúp grader đối chiếu band. RAG giúp lấy đúng tài liệu và dẫn nguồn, không tự tạo điểm. A/B vẫn phải đối chiếu dẫn chứng người học. Validator chỉ chấp nhận chunk thực sự có trong context, đúng tiêu chí; với corpus có band phải viện dẫn mức floor/ceiling của điểm gán. Prompt injection trong transcript vẫn là dữ liệu, không là chỉ dẫn.

PR dùng RAG cho tham khảo các đặc điểm phát âm; các link hiển thị rõ “chưa phải band của bạn”. FC/LR/GRA có link nguồn rubric tại card kết quả chấm. Hai giám khảo độc lập và cơ chế pending_teacher giữ nguyên. Chấm FC từ transcript/VAD vẫn chỉ là ước lượng, chưa được benchmark theo giáo viên.

Panel **Tra rubric Speaking** trên cả hai trang gọi `POST /api/speaking/rubric/search`:

```json
{"query":"word stress rhythm intonation intelligibility","criterion":"PR","top_k":4}
```

Có filter band tùy chọn; trả chunk/text/source/page/version và điểm từng bước retrieval. Panel là tra đoạn rubric, không phải chatbot trả lời mọi câu hỏi IELTS. Query tiếng Anh; chưa có embedding đa ngôn ngữ. Filter ngoài phạm vi và lexical overlap giúp abstain một số trường hợp, nhưng chưa phát hiện được mọi câu không có đáp án.

## Export đúng database-design

Không thêm cột native_score vào bảng thiết kế. DESCRIPTOR_CHUNK/GRADING_CHUNK/CRITERION_REF tiếp tục dùng tên trong ERD. Native report nằm trong `extensions.pronunciation` (answer_id/turn_id, timestamps cục bộ), đồng thời trong `extensions.analysis[].analysis.pronunciation`. Nội dung rubric/provenance mở rộng ở `extensions.rubric_text`; retrieval trace A/B ở `extensions.retrieval_traces`, PR context ở `extensions.rag`. Chỉ descriptor được viện dẫn mới sinh CRITERION_REF; các đoạn PR tham khảo chưa có band máy chấm không sinh điểm PR/FINAL_SCORE giả.

## Kiểm thử và bước tiếp theo

```bash
.venv/bin/python -m pytest backend/tests/speaking -q
.venv/bin/python -m ielts_agent.agents.speaking.evaluate_rag
```

Unit/integration tests dùng provider giả: bảo đảm không gửi khi chưa chọn, continuous mode trên clip dài, score null khi lỗi, timestamp/từ/âm vị, transcript code-switch không bị ghi đè, endpoint voice/practice truyền consent và export không tạo điểm IELTS từ Azure. Speech SDK đã được import và kiểm tra interface, **chưa có kiểm thử chấm audio thật với Azure** vì môi trường chưa cấu hình Speech resource. Các test này không chứng minh độ chính xác phát âm.

RAG có [20 câu golden tự soạn](examples/rag-golden.json), [kết quả JSON](examples/rag-evaluation.json), [bảng hai cấu hình và ca thất bại](rag-evaluation.md). Bộ nhỏ, nhãn nội bộ; cả hai cùng đạt Hit@3=1 trên 16 câu có đáp án, từ chối đúng 3/4 câu không đáp án. Chưa chứng minh hybrid cải thiện hơn BM25; không coi kết quả retrieval là đánh giá chất lượng grader.

Nhóm cần thu 20–30 audio nhiều người Việt, gồm đọc và nói tự do; nhờ 1–2 giáo viên chấm PR trước khi xem điểm máy. Đánh giá lỗi từ/âm vị được Azure chỉ ra, khả năng xếp thứ tự người nói và sai lệch theo code-switch/tên riêng/giọng vùng miền. Nếu hiệu chỉnh IELTS band, tách dữ liệu hiệu chỉnh và kiểm tra; chỉ mở band PR/overall voice sau khi đối chiếu đủ thuyết phục. Khi đó cần version calibration và ngưỡng chuyển giáo viên, không sửa band trực tiếp bằng phép chia.
