# Phân tích part2-skill-test-01

Nguồn: `part2-skill-test-01.json`, gồm 1 câu trả lời Part 2 cho cue card **A useful skill**. File là kết quả Groq thật (`source=live`), bật prompt giữ filler. Đã nhận thêm `part2-skill-test-01.webm` và xác nhận giải mã đúng 85,5 giây. Ngoài đối chiếu với mẫu trong chat, đã chạy nhận dạng local và Silero VAD trên audio. Phiên phân tích không hỗ trợ nghe trực tiếp; các đối chiếu tự động bên dưới không phải transcript chuẩn do người nghe xác nhận.

## Kết quả kiểm tra kỹ thuật

| Mục | Giá trị | Nhận xét |
| --- | --- | --- |
| Thời lượng audio do backend đo | 85,5 giây | 1 phút 25,5 giây; nằm trong giới hạn Part 2. |
| Thời gian gọi STT | 1,488 giây | Lời gọi Groq nhanh trong lượt này; không bao gồm toàn bộ phiên luyện nói. |
| Từ được nhận dạng | 188 | Danh sách timestamps khớp nội dung transcript sau chuẩn hóa. |
| Khoảng từ đầu đến từ cuối | 84,12 giây | Giao diện làm tròn thành 84,1 giây. Đây là khoảng thời gian gồm cả các lần dừng, không phải tổng thời gian phát âm thực sự. |
| Tốc độ theo timestamps | 134,1 từ/phút | Tính lại: 188 × 60 / 84,12 ≈ 134,094. Đúng với công thức hiện tại; độ chính xác còn phụ thuộc timestamps. |
| Khoảng dừng ≥ 0,5 giây | 7 | Tổng các khoảng dừng 5,88 giây, làm tròn thành 5,9; dài nhất 1,16 giây. |
| Filler được nhận dạng | 0 | Transcript không có filler thuộc bộ đếm. Không chứng minh audio không có filler, dù đã bật prompt. |
| Từ giống nhau liền nhau | 0 | Đúng với bộ đếm hiện tại, nhưng không bao quát tự sửa câu hoặc lặp cụm từ. |
| Chuẩn bị được ghi nhận | 0 giây, không có ghi chú | Có thể bắt đầu nói ngay hoặc dùng audio có sẵn; JSON không phân biệt hai trường hợp. Lượt này chưa kiểm chứng bước chuẩn bị đủ 1 phút. |

Đã chạy lại hàm `analyze()` trên dữ liệu xuất: **quality và metrics khớp toàn bộ kết quả trong file**. Timestamps đều nằm trong audio, không lùi và không chồng lấn. Từ cuối kết thúc ở 84,14 giây, còn audio kết thúc ở 85,5 giây. Không phát hiện câu dài lặp ít nhất 3 lần theo quy tắc hiện tại.

`quality.status=ok` chỉ có nghĩa là qua các kiểm tra sơ bộ này, không xác nhận transcript đúng hoàn toàn hoặc bài nói đủ tốt để chấm IELTS. Audio dừng trước 120 giây nên lượt này không xác nhận chức năng tự dừng khi hết 2 phút.

## Những chỗ khác câu trả lời mẫu

Mẫu trong chat có 186 token theo bộ tách token hiện tại, transcript có 188. Các khác biệt dưới đây là **kịch bản so với transcript**, chưa phải lỗi STT đã được xác minh. Không tính WER từ kịch bản khi chưa xác nhận lời nói thực tế trong audio.

| Vị trí gần đúng trong audio | Mẫu trong chat | Transcript | Điều cần kiểm tra |
| --- | --- | --- | --- |
| 0,02–3,18 s | `I'd like` | `I like` | Kiểm tra người nói có đọc âm rút gọn `I'd` không. Hai câu có sắc thái khác nhau; `I like` không tự nó là lỗi ngữ pháp. |
| 17,74–18,04 s | `found` | `felt` | Nhận khác động từ trong câu `I ... it quite difficult`; cần nghe audio trước khi quy là lỗi diễn đạt của người học. |
| 23,68–24,60 s | `write a program` | `write programming` | Khác cách dùng từ; có thể ảnh hưởng phản hồi Lexical Resource nếu dùng transcript mà không kiểm chứng. |
| 28,78–29,20 s | `watched` | `watch` | Đuôi quá khứ không xuất hiện trong transcript. Chưa biết người nói bỏ đuôi hay STT nhận thiếu. |
| 30,82–31,32 s | `practiced` | `practice` | Cùng vấn đề về đuôi quá khứ. |
| 41,44–42,30 s | `built` | `used to build` | Thay cả cấu trúc, từ một lần xây website sang sắc thái thói quen trong quá khứ. |
| 46,04–47,42 s | `some of its functions` | `some dysfunctions` | **Ưu tiên nghe lại.** `Dysfunctions` nói đến sự trục trặc/rối loạn, khác với các chức năng của website. Chấm thẳng transcript có thể quy sai lỗi dùng từ. |
| 50,70–50,82 s | `the problem` | `a problem` | Khác mạo từ; không nên tự động coi đây là lỗi ngữ pháp. |
| 80,92–83,24 s | `than when` | `than I would, than when` | Có dấu hiệu đổi ý/tự sửa trong transcript. Bộ đếm lặp từ liền nhau bằng 0 vẫn đúng, nhưng chưa mô tả được hiện tượng này. |

## Giới hạn timestamps trong lượt này

Từ đầu **`I` được gán 0,02–2,86 giây**, tức kéo dài **2,84 giây**. Đây là khoảng đáng kiểm tra: có thể có khoảng lặng đầu bản thu được gán vào từ, cũng có thể do cách người nói phát âm hoặc căn chỉnh của STT. Không thể kết luận chỉ từ JSON.

Có 180/187 cặp từ có end của từ trước bằng start của từ sau. Chỉ 7 cặp có khoảng trống, chính là các pause đang đếm. Điều này không tự chứng minh timestamps sai, nhưng cho thấy phép đo pause phụ thuộc mạnh vào cách STT phân chia thời gian; khoảng ngập ngừng có thể nằm trong thời lượng của một từ và không được bộ đếm phát hiện.

Các khoảng dừng nhận được chủ yếu nằm ở cuối câu, ví dụ sau `day.`, `project.`, `solutions.` và `work.`. Không nên mặc định mọi khoảng dừng này đều là vấn đề fluency; khi đọc một bài mẫu, dừng giữa câu/đoạn là điều có thể xảy ra.

## Đánh giá cho đồ án

**Luồng Part 2 hoạt động trong lượt thử này:** nhận audio, gọi Groq, trả transcript/timestamps, tính metrics và xuất JSON có cue card cùng metadata chuẩn bị. Nội dung transcript đề cập đủ các ý của cue card: lập trình là kỹ năng gì, học ở năm đầu đại học và qua luyện tập, dùng cho bài tập/dự án hiện tại, và ý nghĩa đối với công việc tương lai.

**Chưa đủ cơ sở chấm band hoặc Pronunciation.** Đây là đọc mẫu, chưa phản ánh khả năng tự triển khai câu trả lời. Các khác biệt ở bảng trên chưa được phân biệt thành lỗi STT, đọc khác kịch bản hay lỗi thật của người nói; timestamps cũng chưa được kiểm chứng với audio.

Ưu tiên tiếp theo:

1. Nghe audio đã lưu tại các đoạn 23–25 s, 28–32 s, 41–47 s, 80–84 s và đầu bản thu. Ghi transcript đối chiếu theo lời nói thực tế, giữ nguyên lỗi và tự sửa. Các clip ngắn đã được cắt ở thư mục nêu bên dưới.
2. Thử một lượt có đủ 60 giây chuẩn bị và để hệ thống tự dừng ở 120 giây để kiểm tra luồng thời gian thực. Có thể dùng mẫu dài hơn hoặc tự mở rộng câu trả lời; không cần nói hết 2 phút chỉ để kiểm tra transcript trong lượt hiện tại.
3. Khi cải thiện metrics, bổ sung dấu hiệu tự sửa/lặp cụm từ và cảnh báo từ có thời lượng bất thường; tránh suy luận rằng `filler_count=0` hoặc không có từ lặp liền nhau nghĩa là nói hoàn toàn trôi chảy.

## Đối chiếu sau khi có audio

### Độ dài và kết nối dữ liệu

`part2-skill-test-01.webm` có 1.381.321 byte. Giải mã sang mono 16 kHz được đúng **85,5 giây**, khớp `audio_seconds` trong JSON. File có tín hiệu âm thanh, không phải bản thu toàn bộ im lặng. Độ dài phù hợp với lượt xuất; phép đo này không phải kiểm tra định danh tuyệt đối của bản ghi.

### Khoảng không nói trên audio

Đã dùng **Silero VAD** đi kèm faster-whisper, threshold 0,5, min_silence_duration_ms 500, speech_pad_ms 0. VAD là bộ phát hiện giọng nói, không phải bộ chấm phát âm hoặc mốc chuẩn tuyệt đối. Không thay thế metrics trong JSON gốc.

| Phép đo | Timestamps Groq | Silero VAD trên audio |
| --- | --- | --- |
| Mốc bắt đầu | Từ đầu bắt đầu 0,02 s | Vùng giọng nói đầu bắt đầu 2,816 s |
| Mốc kết thúc | Từ cuối kết thúc 84,14 s | Vùng giọng nói cuối kết thúc 84,128 s |
| Khoảng dừng/không nói nội bộ ≥ 0,5 s | 7 | 13 |
| Tổng độ dài các khoảng trên | 5,88 s | 11,168 s |

Hai phương pháp đo khác nhau: Groq đo khoảng trống giữa timestamps các từ; VAD đo khoảng audio không được mô hình phân loại là giọng nói. VAD có thể nhầm một số âm yếu, tiếng thở hoặc phần kéo dài của từ. Tuy vậy, kết quả hỗ trợ nghi ngờ rằng Groq đã gán khoảng lặng đầu bản thu vào từ `I` dài 2,84 giây và chưa thể hiện đủ một số khoảng dừng giữa các từ/câu.

Ví dụ, VAD đánh dấu khoảng không nói **8,480–9,024 s** giữa hai câu đầu và **43,872–44,608 s** trước `I was responsible ...`; timestamps Groq ở các vị trí này liền nhau, nên bộ đếm pause không phát hiện được khoảng trống.

Nếu chỉ dùng khoảng từ vùng giọng nói đầu đến cuối của VAD (81,312 giây), 188 từ tương ứng khoảng **138,7 từ/phút**, thay vì 134,1. Đây là phép tính minh họa ảnh hưởng của mốc bắt đầu, không phải tốc độ chuẩn đã được xác minh. Không lấy tổng thời gian giọng nói thuần của VAD làm mẫu số để thay tốc độ đang có, vì đó là một định nghĩa khác và bỏ thời gian ngập ngừng.

### So sánh với nhận dạng local

Chạy faster-whisper Large v3 Turbo trên cùng audio, CPU int8, 4 luồng, bật prompt giữ filler, tắt VAD. Lượt xử lý mất **27,12 giây**, không tính nạp model. Đây là cùng họ model với Groq, nên sự đồng ý giữa hai kết quả không phải bằng chứng độc lập về lời nói thực tế.

| Điểm kiểm tra | Groq | Local | Kết luận được phép rút ra |
| --- | --- | --- | --- |
| `I like`, `felt`, `write programming`, `practice`, `some dysfunctions` | Có | Có | Hai bản ASR cùng nhận như vậy; vẫn cần nghe trước khi quy lỗi cho người nói. |
| `watch` / `watched` | `watch` | `watched` | Có bất đồng về đuôi quá khứ; chưa nên chấm lỗi thì ở đây. |
| Đoạn xây website | `used to build a simple website` | `used to see my website` | Đây là đoạn nhận dạng chưa chắc chắn, cần nghe lại. |
| Đoạn cuối đổi ý | `than I would, than when` | `than when` | Không đủ căn cứ xác nhận tự sửa câu chỉ từ một kết quả. |
| Sau câu cuối | Kết thúc ở `started.` | Thêm `I have a lot to learn. Thank you. Thank you. Thank you.` | Bản local có nội dung bổ sung đáng nghi so với mẫu và mốc VAD; không dùng làm transcript chuẩn. |

Bản local còn gán nhiều từ bổ sung ở cuối thời lượng bằng 0, nhưng vẫn qua validator hiện tại. Điều này cho thấy validator mới kiểm tra các bất thường cơ bản, chưa phát hiện đầy đủ nội dung có khả năng nhận sai ở cuối audio, câu ngắn lặp hoặc căn chỉnh từ bất thường. Không chuyển sang local chỉ vì nó nhận `watched` giống kịch bản.

### File đối chiếu và clip nghe lại

- `part2-skill-test-01-local.json`: transcript và timestamps nhận dạng local.
- `part2-skill-test-01-vad.json`: vùng giọng nói và khoảng không nói ước lượng bằng VAD.
- [Đầu bản thu, 0–5 s](part2-skill-test-01-clips/01-opening.wav).
- [Found/felt, 17–20 s](part2-skill-test-01-clips/02-found-felt.wav).
- [Write a program, 23–26 s](part2-skill-test-01-clips/03-write-a-program.wav).
- [Watched/practiced, 28–33 s](part2-skill-test-01-clips/04-past-tense.wav).
- [Website/functions, 40–48 s](part2-skill-test-01-clips/05-website-functions.wav).
- [Đoạn cuối, 80–85,5 s](part2-skill-test-01-clips/06-self-correction.wav).

Clip được cắt từ audio gốc và xuất WAV mono 16 kHz để tiện nghe; không thay đổi tốc độ hoặc sửa lời nói. Thời gian trong tên/ghi chú tính theo audio gốc, còn timestamp bên trong từng clip bắt đầu lại từ 0.

**Hướng tiếp theo cho Speaking Agent:** Tiếp tục dùng Groq để lấy transcript, nhưng đo khoảng không nói từ audio bằng VAD để đối chiếu, không coi pause từ timestamps là đầy đủ. Bổ sung cảnh báo từ kéo dài bất thường, từ có độ dài bằng 0 và các kiểu lặp ngắn/tự sửa. Chưa dùng đoạn ASR bất đồng làm bằng chứng chấm Grammar hoặc Lexical Resource nếu chưa xác minh audio.

## Metrics 1.2 đã được triển khai

Đã tích hợp VAD và giữ riêng metrics STT trên API/UI. Chạy lại với audio và transcript đã lưu, không gọi Groq mới; kết quả tại `part2-skill-test-01-metrics-v1.2.json`, không ghi đè JSON gốc. VAD vẫn có 13 khoảng không nói/11,168 giây và WPM theo cửa sổ VAD là 138,7; metrics STT vẫn có 7 pause/5,9 giây để đối chiếu.

Validator mới trả `needs_review` do `long_word_duration` và `word_overlaps_non_speech`; đây là warning nên số liệu STT vẫn xem được với cảnh báo. Dấu hiệu dùng lại từ nối `than` được đưa vào repair_candidates, không kết luận đây là lỗi tự sửa đã xác minh. Quy tắc mới cũng phát hiện từ zero-duration và câu ngắn lặp trong bản local có vấn đề đã nêu ở trên.
