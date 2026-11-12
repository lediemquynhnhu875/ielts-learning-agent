# Kết quả thử nghiệm Speaking STT — 12/10/2026

## Phạm vi kết luận so với UC04

Báo cáo ghi lại thử nghiệm tầng STT và các lần cập nhật prototype Part 1/2; các kết quả/test đã chạy bên dưới được giữ theo từng mốc. Bộ 10 audio đọc sẵn chưa phải benchmark phiên thi Speaking nói tự do, chưa có điểm giáo viên để xác nhận mục tiêu ≥80% transcript lệch ≤1,0 band, và chưa kiểm chứng Part 3 đào sâu, chặn hỏi trùng nghĩa, RAG hoặc SpeakingAssessment.

Đối chiếu UC04 ngày 15/10/2026: [README](../speaking/README.md#phạm-vi-so-với-uc04--cập-nhật-15102026) ghi phần đã có/chưa có; [proposal](../speaking/docs/meeting-proposal.md) mô tả thiết kế tích hợp và kế hoạch eval chưa chạy. Cảnh báo chất lượng hiện tại không tương đương confidence STT. Các mục “cần thêm” trong phần thử nghiệm ban đầu là kế hoạch tại thời điểm đó; phần cập nhật cuối báo cáo ghi những kiểm tra STT/VAD đã triển khai sau này.

## Phạm vi đã chạy

- 10 file `.m4a` trong `audio-sample`, tổng thời lượng 261,24 giây; mỗi file dài 17,39–34,49 giây.
- faster-whisper 1.2.1, model Large v3 Turbo, CPU int8 trên macOS ARM64, 4 luồng; tiếng Anh, temperature 0, tắt VAD.
- Mỗi file chạy 2 chế độ: không prompt và có prompt giữ filler (`--keep-fillers`), trên cả local và Groq. Tổng cộng **40 lượt trả về transcript**, 20 lượt cho mỗi backend.
- Local: 19 lượt có word timestamps và chỉ số fluency. Sample 05 có prompt bị lỗi thư viện khi căn chỉnh timestamps; chạy lại vẫn lỗi, phải lấy transcript không kèm timestamps. Lượt này không có chỉ số fluency.
- Groq: dùng API `whisper-large-v3-turbo`, tiếng Anh, temperature 0, yêu cầu word/segment timestamps. Cả 20 lượt trả về timestamps, nhưng có các bất thường thời gian cần kiểm tra trước khi sử dụng metrics.

## Tốc độ

19 lượt có timestamps mất trung bình **6,72 giây/lượt**, dao động **5,00–11,16 giây**. Trung bình tỉ lệ thời gian xử lý/thời lượng audio (RTF) là **0,257**; mỗi lượt đều xử lý nhanh hơn thời lượng đoạn thu âm. Trung bình cả 20 lượt là 7,42 giây; riêng lượt fallback của sample 05 mất 20,64 giây, gồm lần thử có timestamps và lần lấy transcript không timestamps.

Groq mất trung bình **1,89 giây/lượt**, trung vị **1,91 giây**, dao động **0,92–4,39 giây**. Không prompt trung bình 1,77 giây; có prompt trung bình 2,02 giây. Thời gian Groq đo quanh lời gọi API nên bao gồm upload audio, mạng và xử lý phía dịch vụ.

Đối chiếu đúng **19 cặp sample/chế độ**, loại cặp sample 05 có prompt vì local phải fallback: local trung bình **6,72 giây**, Groq **1,94 giây**, tức Groq nhanh hơn khoảng **3,47 lần** trong phép đo này. Đây là so sánh thời gian trả kết quả, không có nghĩa chất lượng transcript hoặc timestamps tương đương.

Thời gian local không bao gồm tải hoặc nạp model. Chưa đo độ trễ toàn bộ vòng Speaking gồm upload, STT, tạo câu hỏi tiếp nối và TTS; cũng chưa kiểm tra độ ổn định qua nhiều lần chạy. Hai backend được chạy ở các thời điểm khác nhau; kết quả mạng và tải máy có thể thay đổi.

## Những điểm đáng chú ý trên local

| Sample | Kết quả quan sát | Ý nghĩa cho Speaking Agent |
| --- | --- | --- |
| 01 | Cả hai transcript khớp kịch bản khi bỏ qua viết hoa và dấu câu. | Mẫu đúng cơ bản được nhận nhất quán trong hai chế độ. |
| 02 | Cả hai chế độ có `lives`, `goes`, `finishes`, `asks`, `doesn't understand` thay cho các dạng sai trong kịch bản. `He don't` vẫn còn. | Có dấu hiệu làm mất một số lỗi ngữ pháp; prompt giữ filler không đảm bảo giữ lỗi. |
| 03 | `didn't went` thành `didn't go`, `readed` thành `read`; nhiều động từ hiện tại khác vẫn được giữ. | Transcript có thể giữ và sửa lỗi không đồng đều. |
| 04 | `advices` thành `advice`, `informations` thành `information`, và nhiều danh từ được thêm số nhiều. Chế độ prompt còn đổi `teacher ... gives` thành `teachers ... give`. | Cần nghe lại các chỗ có đuôi âm để xác nhận lời thực tế. |
| 05 | Không prompt: `interested on` thành `interested in`. Có prompt: lỗi timestamps; bản fallback giữ `interested on` nhưng lặp nhiều lần câu `I have a friend who lives in the same building`, không có trong kịch bản. | Không dùng bản fallback này làm đầu vào chấm điểm khi chưa xác minh audio. |
| 06 | Không prompt không nhận filler nào; có prompt nhận 3 từ `um`, còn kịch bản có 5 filler. Số khoảng dừng suy ra từ timestamps lần lượt là 3 và 5. | Prompt có ảnh hưởng rõ, nhưng số filler nhận được chưa phải số filler thực sự đã nói. |
| 07 | Không prompt bỏ nhiều chỗ lặp và lần đổi ý `Monday ... no, on Tuesday`. Có prompt giữ được lần đổi ý và nhiều chỗ lặp, đồng thời có thêm các từ `uh` so với kịch bản. | Cần đối chiếu audio để phân biệt giữ lời thực tế với thêm lời ngoài audio. |
| 08 | Không prompt dùng `vocabulary`, có prompt dùng `vocabularies`. Cả hai nhận `a better world` thay vì `a better work`. | Prompt đôi khi giữ được lỗi từ vựng, nhưng không loại bỏ lỗi nhận dạng. |
| 09 | Cả hai dùng `parents were`, `studied`, `more confident` thay các dạng sai trong kịch bản. Chế độ prompt giữ thêm filler và `I, I`. | Giữ ngập ngừng tốt hơn không đồng nghĩa giữ lỗi ngữ pháp tốt hơn. |
| 10 | Cả hai giữ các giá trị 15, 50.000, 13, 30.000 nhưng viết tiền thành `$50,000` và `$30,000`, thay vì `dong`. Các từ có hướng dẫn đọc sai vẫn được viết đúng. | Phải kiểm tra đơn vị tiền và phân tích audio riêng khi đánh giá phát âm. |

## Đối chiếu transcript Groq với local

| Sample | Kết quả Groq so với local |
| --- | --- |
| 01 | Cả hai chế độ khớp kịch bản sau khi bỏ qua viết hoa/dấu câu, giống local. |
| 02 | Không prompt giống local. Có prompt giữ `He go`, còn local dùng `He goes`; nhiều dạng sai khác vẫn được chuyển thành dạng đúng. |
| 03 | Hai chế độ có nội dung giống local, gồm `didn't go` và `read` thay các dạng sai trong kịch bản. |
| 04 | Cả hai chế độ Groq dùng `teacher ... gives`; không có thay đổi thành `teachers ... give` như local có prompt. Các dạng `advices`, `informations` vẫn chuyển thành dạng đúng. |
| 05 | Groq trả timestamps trong cả hai chế độ. Có prompt giữ `interested on`, không lặp câu như bản fallback local. Không prompt dùng `interested in`. |
| 06 | Không prompt bỏ các filler trong kịch bản và thêm `Thank you.` ở cuối. Có prompt nhận 3 từ `um`, thêm câu `I'm not going to be a good one.` ngoài kịch bản và có timestamps vượt quá audio. |
| 07 | Không prompt giữ lần đổi ý `Monday ... No, on Tuesday` và lặp `a book`, nhưng bỏ một số chỗ lặp khác. Có prompt giữ thêm chỗ lặp, có nhiều filler ngoài kịch bản và đổi `finished` thành `finish`. |
| 08 | Cả hai chế độ nhận `a better work`, sát kịch bản hơn `a better world` của local; tuy nhiên đều dùng `vocabulary` thay `vocabularies`. |
| 09 | Không prompt dùng `more clearly`, trong khi local giữ `more clear`. Có prompt giữ `more clear`, filler và `I, I`; cả hai backend vẫn dùng `were`, `studied`, `confident`. |
| 10 | Groq viết `50,000 don` và `30,000 don`, còn local viết `$50,000` và `$30,000`. Groq không đổi đơn vị thành dollar, nhưng vẫn nhận thiếu chữ cuối của `dong`. |

Có **8/20 cặp transcript giống nhau** sau khi chuẩn hóa viết hoa/dấu câu bằng bộ tách token hiện tại. Con số này chỉ thể hiện mức tương đồng giữa hai backend, không phải độ chính xác. Prompt giữ filler thay đổi kết quả ở cả hai backend, nhưng chưa chứng minh mọi filler bổ sung đều có trong audio.

**Mức độ chắc chắn:** Những điểm trên là so sánh transcript với kịch bản thu âm. Chưa có transcript chuẩn được người nghe xác nhận từ từng audio, nên chưa thể quy mọi khác biệt cho STT, kết luận chắc chắn Whisper tự sửa lỗi, hoặc tính WER đáng tin cậy. Cách viết số bằng chữ/chữ số là khác biệt định dạng; đổi đơn vị tiền là khác biệt nội dung cần kiểm tra.

## Kiểm tra timestamps Groq

**Sample 06 có prompt không đủ điều kiện sử dụng fluency metrics:** audio dài **30,524 giây**, nhưng từ cuối kết thúc tại **49,8 giây**. Có 8 từ vượt quá độ dài audio, bắt đầu từ `I'm` trong câu bổ sung ở cuối. Metrics hiện tại suy ra thời lượng nói 47,5 giây và tốc độ 65,7 từ/phút; những giá trị này không hợp lệ vì dựa trên timestamps vượt audio.

Bốn lượt **không prompt** khác có thời điểm bắt đầu từ sau nhỏ hơn thời điểm bắt đầu từ trước:

| Sample | Ví dụ timestamp bị lùi (giây) |
| --- | --- |
| 03 | `novel.` bắt đầu 15,92; từ kế tiếp `I` bắt đầu 15,50. |
| 07 | `book` bắt đầu 25,92; từ kế tiếp `A` bắt đầu 25,82. |
| 08 | `proud.` bắt đầu 10,64; từ kế tiếp `My` bắt đầu 10,50. |
| 10 | `make` bắt đầu 5,50; `mistakes,` bắt đầu 5,26. Một trường hợp khác: `affects` 10,82; `the` 10,78. |

Các timestamp bị lùi này cần được xác minh trước khi dùng để suy ra khoảng dừng. Local không có hai loại bất thường trên trong 19 lượt trả timestamps. Việc timestamps nằm trong audio và không lùi chỉ là kiểm tra sơ bộ, chưa chứng minh chúng khớp thời điểm thực tế người nói.

Dữ liệu gốc trong JSON/CSV và hai báo cáo backend được giữ nguyên. Cột `Timestamps=True` chỉ nghĩa là có dữ liệu timestamps, không có nghĩa timestamps đã được xác nhận đúng.

## Giới hạn của chỉ số hiện tại

- Pause được suy ra từ khoảng cách timestamps giữa hai từ, không phải phép đo khoảng lặng độc lập trên audio.
- Bộ đếm filler trong `test_whisper.py` coi mọi `like` là filler. Vì vậy `don't like cooking` ở sample 02 và `don't like speaking` ở sample 09 cũng bị đếm; các số này chưa nên dùng trực tiếp để chấm Fluency.
- Bộ đếm lặp chỉ phát hiện hai từ giống nhau đứng liền nhau. Nó không bắt đầy đủ lặp cụm từ hoặc các lần tự sửa câu.
- Chưa chấm Pronunciation hoặc band IELTS. Transcript đúng chính tả không chứng minh phát âm đúng.
- Script hiện chưa tự loại timestamps vượt audio hoặc bị lùi trước khi tính fluency. Không dùng trực tiếp các metrics bất thường nêu trên để chấm điểm.

## Hướng triển khai sau thử nghiệm

**Có thể ưu tiên Groq để tích hợp bản thử nghiệm Speaking Part 1**, dựa trên tốc độ và việc trả timestamps cho cả 20 lượt trong bộ audio này. Đây là lựa chọn ban đầu cho prototype, chưa phải kết luận Groq chính xác hơn hoặc ổn định hơn trên mọi người học.

Trước khi dùng kết quả STT để chấm điểm, cần thêm kiểm tra timestamps theo độ dài audio và thứ tự từ, xử lý transcript lặp bất thường, và xác nhận các lỗi ngữ pháp từ audio. Giữ prompt filler thành tùy chọn thử nghiệm; chưa bật mặc định cho chấm điểm khi chưa đo độ trung thực. Pronunciation vẫn cần xử lý audio riêng.

## File kết quả và chạy lại

- `local/report.md`: transcript của từng lượt, bảng thời gian và các khác biệt với kịch bản.
- `local/results.json`: dữ liệu đầy đủ, word timestamps, metrics, thông tin môi trường và lỗi của lần chạy trước.
- `local/summary.csv`: bảng số liệu để mở trong Excel hoặc Google Sheets.
- `groq/report.md`, `groq/results.json`, `groq/summary.csv`: cùng loại kết quả cho 20 lượt Groq.

Chạy lại local với model đã tải trong project:

```sh
.venv/bin/python run_stt_benchmark.py --backend local
```

Để chạy lại Groq sau khi cấu hình `GROQ_API_KEY` trong môi trường:

```sh
.venv/bin/python run_stt_benchmark.py --backend groq --output stt-results/groq
```

Lệnh Groq gửi audio tới dịch vụ Groq. API key không được lưu vào báo cáo.

**Bước tiếp theo:** Nghe và xác nhận transcript chuẩn của 10 audio, đặc biệt samples 02–09; đánh dấu những lỗi người thu thực sự đã nói, các filler và chỗ lặp. Sau đó đo độ chính xác, tỉ lệ giữ lỗi ngữ pháp và hiệu quả của prompt trên cả hai backend. Song song, bổ sung kiểm tra dữ liệu STT trước khi nối vào luồng ghi âm → transcript → feedback của Speaking Part 1.

## Prototype Part 1 đã triển khai

Đã có backend FastAPI và giao diện local trong `speaking/`: 15 câu hỏi theo 3 chủ đề, ghi âm bằng mic, chọn audio có sẵn, nghe lại, gửi tới Groq, xem transcript/metrics và xuất JSON của phiên. Backend đo thời lượng audio thực tế, kiểm tra timestamps vượt audio hoặc bị lùi, nội dung lặp và sự khớp giữa transcript với danh sách từ; khi có vấn đề sẽ không trả metrics theo thời gian.

Ở lần kiểm thử Part 1 ban đầu, đã chạy 13 test backend/validation và kiểm tra trình duyệt trên desktop/mobile, gồm mic giả, từ chối quyền mic, playback, bản thu được giữ khi chuyển câu, cảnh báo timestamps, thiếu key, xuất JSON và bắt đầu phiên mới. Lượt gửi thành công trong test dùng stub vì môi trường lúc đó chưa có API key. Các benchmark Groq ở trên là kết quả API thực tế đã chạy trước đó.

Hướng dẫn cấu hình và schema: [speaking/README.md](../speaking/README.md). Chưa tích hợp chấm band, Pronunciation hoặc lưu vào hồ sơ người học; lịch sử của prototype nằm trong tab hiện tại và có thể xuất JSON.

## Prototype Part 2 đã triển khai

Đã thêm tab Part 2 với 6 cue card gốc từ bộ đề viết sẵn, chọn đề/ngẫu nhiên, ghi chú chuẩn bị, đồng hồ 60 giây chuẩn bị và 120 giây nói. Khi hết chuẩn bị sẽ tự thu âm, hết giờ nói sẽ tự dừng; cũng có thể hủy chuẩn bị hoặc bắt đầu/dừng nói sớm. Backend giới hạn audio Part 2 ở 120 giây với dung sai 0,5 giây cho đoạn MediaRecorder cuối. JSON của phiên giữ được cả Part 1/2, cue card và metadata chuẩn bị.

17 test backend/validation và browser smoke test desktop/mobile đã qua, gồm các mốc thời gian tự động, hủy/bắt đầu sớm và xuất phiên hỗn hợp. Browser test dùng mic giả, đồng hồ tăng tốc và stub response; không phải một bài Speaking thật kéo dài 2 phút.

Sau khi key được cấu hình, đã gọi **Groq thật** qua endpoint Part 2 với `sample-01.m4a` (23,36 giây), gán đề `part2-skill` để kiểm tra kỹ thuật. API trả HTTP 200, transcript và timestamps qua kiểm tra sơ bộ; thời gian lời gọi STT là 0,606 giây trong lượt này. Audio mẫu không được thu để trả lời cue card đó, nên kết quả này chỉ xác nhận đường truyền API, không đánh giá chất lượng bài nói. Dữ liệu lưu tại `speaking/qa/groq-part2-smoke.json`.

## Cập nhật metrics — 14/10/2026

Đã tích hợp Silero VAD v6 local trên audio, giữ riêng metrics theo audio và theo timestamps STT trong schema 1.2; không cắt audio gửi Groq. UI bổ sung bảng đối chiếu, danh sách khoảng không nói, dấu hiệu lặp cụm/tự sửa và cảnh báo căn chỉnh từ. Metrics VAD không phải chấm Pronunciation hoặc band IELTS.

26 test backend/validation và browser smoke test Part 1/2 desktop/mobile đã qua. Phân tích lại bản thu 85,5 giây và transcript đã lưu cho ra 13 khoảng không nói VAD (11,168 giây), so với 7 pause STT (5,9 giây). Không gọi lại Groq, không sửa bản xuất gốc. Bản mới tại `stt-results/user-tests/part2-skill-test-01-metrics-v1.2.json`.

Đề xuất schema cho Writing/Planning và phạm vi Pronunciation MVP: [meeting-proposal.md](../speaking/docs/meeting-proposal.md). Đây là đề xuất cho nhóm, chưa tích hợp grader hoặc dịch vụ Pronunciation.

## Cập nhật demo UC04 — 15/10/2026

Đã bổ sung `/exam` với luồng ba phần, text/voice, Part 2 và câu chốt, Part 3 theo mẫu tham chiếu candidate_points, checkpoint SQLite, pause/resume và xuất phiên. Có adapter chấm A/B với corpus Speaking theo metadata, validator evidence/descriptor và điểm text tạm tính; chỉ chạy khi cấu hình model/corpus, chưa có kết quả chấm Groq thật trong lần kiểm tra này. Voice theo MVP hoãn PR, chưa đáp ứng nhánh PR proxy của UC04.

41 test backend/validation đã qua, gồm 26 test cũ và 15 test phiên thi/grading mới. Hai bộ browser test luyện Part 1/2 và thi thử đã qua trên desktop/mobile; có mic giả và stub, không gọi Groq. Đã sửa thanh điều hướng tràn ở màn hình nhỏ. Đây là xác minh kỹ thuật, chưa phải benchmark band hoặc chất lượng câu hỏi. Hướng dẫn, API, cấu hình và giới hạn tại [demo-uc04.md](../speaking/docs/demo-uc04.md). Dữ liệu STT gốc và các số liệu thử nghiệm trước đó được giữ nguyên.

## Sửa cấu hình ngôn ngữ STT — 15/10/2026

Phát hiện wrapper Groq/local đang ép `language="en"` dù audio có thể chứa tiếng Việt. Đã bỏ ép tiếng Anh trên Groq transcription; local dùng language=None, task=transcribe, multilingual=True. Prompt filler được đổi sang ví dụ Việt/Anh; tokenizer analysis giữ Unicode. Cả endpoint luyện và thi thử dùng chung wrapper đã sửa.

46 test đã qua, gồm thêm 5 test cấu hình/pipeline ngôn ngữ với provider stub. Chưa chạy lại benchmark hoặc đo trên audio Việt/Anh thực; không dùng kết quả stub để kết luận STT luôn giữ chính xác từng từ. Các bản thu/báo cáo gốc vẫn phản ánh cấu hình cũ. Lượt benchmark mới ghi transcription_policy=original_language_auto_v1 ở từng result để phân biệt.

## Tái hiện code-switch trên audio thực — 16/10/2026

Đã kiểm tra bản thu 8,28 giây chứa tên trường tiếng Việt, gồm 4 lượt Groq được người học đồng ý và 3 cấu hình local. Turbo tái hiện lỗi dịch sang tiếng Việt; Groq V3 giữ phần tiếng Anh nhưng vẫn nhận sai tên riêng. Vì chưa có transcript chuẩn xác nhận bằng nghe và các output chưa khớp nguyên văn câu người học báo, không kết luận đã sửa hoàn toàn STT. Kết quả từng lượt và giới hạn tại [code-switch-school-review.md](user-tests/code-switch-school-review.md).

Đã đổi mặc định Groq sang V3, thêm gợi ý tên riêng, bỏ câu ví dụ khỏi prompt filler và trả warning khi gợi ý chưa xuất hiện trong transcript. Policy mới original_language_context_v2; 50 unit/API tests qua. Các kết quả thử nghiệm cũ được giữ nguyên; không dùng một clip để kết luận model tốt hơn trên mọi trường hợp.

## Chuẩn hóa output database — 16/10/2026

Đã đọc các bảng và sơ đồ trong `database-design.docx`, bổ sung contract `ielts-speaking-db-1.0` và cập nhật API/demo/export. Output tách các bảng SESSION/ATTEMPT/ANSWER/SPEAKING_TURN, candidate points/câu hỏi và toàn bộ nhóm bảng chấm điểm; metrics nằm riêng trong extensions. Span evidence được chuyển sang offsets của transcript toàn attempt. Audio được đồng ý lưu có thể tải thành WAV ghép với timeline tương ứng, không dùng blob URL làm URI database.

60 unit/API tests đã qua, gồm 10 test database/export và test đối chiếu tên cột trực tiếp với DOCX. Hai bộ browser test luyện/thi thử qua với định dạng export mới. Đã kiểm tra đọc 7 checkpoint hiện có mà không sửa nội dung gốc. Không gọi Groq trong lần kiểm tra schema; chưa insert vào database chung vì repo chưa có DDL/kết nối của nhóm. Xem [database-mapping.md](../speaking/docs/database-mapping.md), [JSON Schema](../speaking/docs/database-schema.json) và [ví dụ text giả lập](../speaking/docs/examples/database-export-text.json).
