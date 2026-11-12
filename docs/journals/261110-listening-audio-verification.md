---
date: 2026-11-10
topic: listening-audio-verification
---

# Kiểm chứng đáp án và thời gian trước khi cấp audio Listening

Phạm vi đã mở rộng từ báo cáo STT toàn văn sang luồng biên soạn, kiểm chứng và
lưu artifact của bài DB. TTS tạo riêng từng lượt rồi ghép PCM để đo timeline
bằng frame, độc lập với word timestamps của Azure STT. STT không nhận script,
đáp án hoặc gợi ý từ vựng. Text hiển thị và từ lexical có thời gian được giữ
riêng; EOF được xử lý theo `cancellation_details` của SDK.

Kiểm tra neo bằng chứng riêng vào vị trí duy nhất trong script, so cả ngữ
cảnh lượt nói và yêu cầu từng từ khớp nằm trong cửa sổ TTS của chính lượt đó.
Quy tắc số hạn chế cho phép `15`/`fifteen` nhưng chặn `15`/`fifty`, giữ zero
đầu. Ngữ cảnh đầy đủ giúp chặn `not fifteen`, `fifteen point five` và đánh vần
tên sai. `NOT GIVEN`, bằng chứng thiếu/mơ hồ hoặc timing không đầy đủ đều
không xác minh được và chặn cấp audio. Cơ chế bảo thủ có thể cần người nghe
rà soát các báo động nhầm từ STT.

Migration `003_listening_audio.sql` lưu WAV, manifest và báo cáo riêng với
`blocked`/`verified`. Nguồn/đáp án, pipeline/giọng, audio và manifest được gắn
hash; GET kiểm tra lại bản hiện hành trước khi cấp. POST audio của bài DB nay
tạo, kiểm chứng và lưu; chỉ đạt mới trả WAV. POST verify trả báo cáo riêng,
bản chặn không kèm audio. GET WAV và GET timing chỉ cấp artifact hợp lệ;
timeline công khai chỉ có 8 trường lượt nói và không lộ đáp án/bằng chứng.

Các POST biên soạn cần `API_TOKEN` đã cấu hình và bearer server. Secret không
được cấp cho learner; frontend proxy không mở các route này. Preview script
trực tiếp và CLI vẫn là chẩn đoán không có đáp án DB. API WAV thành công giữ
định dạng cũ, nhưng cổng kiểm chứng của bài DB là thay đổi hành vi chủ ý.
Không tự retry hoặc tự sửa/sinh lại nội dung.

Kiểm thử đầy đủ với PostgreSQL trong các schema tạm riêng đạt **698 passed,
0 skipped** trong 29,62 giây. Các kiểm thử không xóa hay sửa dữ liệu public.
Rà soát mã, kiểm tra biên dịch và `git diff --check` đều đạt.

Luồng Azure thật đã chạy với bài `Welcome to Lotus Residence, Can Tho`
(`0452ee07-8baf-4430-a63f-521b64e22b28`): 15 request TTS đều trả 200, sau đó
STT detailed nhận dạng toàn WAV. Đã lưu 9.990.644 byte audio, 15 mốc lượt nói
và báo cáo riêng vào PostgreSQL. Kết quả có 3 kiểm tra đạt, 6 chưa đạt và 1
không xác minh được; artifact mang trạng thái `blocked`. GET audio và GET
timeline đều trả 409; báo cáo bị chặn không có audio base64. Nguồn đề/đáp án
trước và sau giống nhau. Thời gian đo toàn lượt là 266,04 giây.

Các khác biệt có thể đến từ STT; 6 kiểm tra chưa đạt không chứng minh có 6
lỗi TTS. Cần nghe/rà soát thay vì tự sửa hoặc tự phát hành lại. Báo cáo quản
trị được Git bỏ qua tại
`data/listening/azure-publication-0452ee07-8baf-4430-a63f-521b64e22b28.json`.
Lượt thử dùng token quản trị ngẫu nhiên trong process, không sửa `.env`.
Muốn dùng POST biên soạn trên server, cần tự cấu hình `API_TOKEN`.

Lượt CLI trước đó trên WAV DB cũ dài 208,137 giây cho 586 token tham chiếu,
588 token nhận dạng, 18 thay thế/1 thiếu/3 thêm, WER 0,037543. Đây là chẩn đoán
lời thoại, không phải quyết định đáp án/timestamp của pipeline mới; WAV cũ giữ
nguyên và không tạo TTS lại trong lượt đó. Báo cáo cục bộ được Git bỏ qua tại
`data/listening/azure-db-0452ee07-8baf-4430-a63f-521b64e22b28-verification.json`.

Xem [hướng dẫn kiểm chứng và phát hành](../listening-audio-verification.md).
