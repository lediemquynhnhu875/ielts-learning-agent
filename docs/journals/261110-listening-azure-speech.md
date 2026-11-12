---
date: 2026-11-10
topic: listening-azure-speech
---

# Tổng hợp audio Listening bằng Azure Speech

Nối kết quả tách lượt người nói với Azure Speech REST. Một request SSML chứa
các phần tử `voice` theo đúng thứ tự script; trả WAV PCM mono 24 kHz, 16 bit.
Giọng gán luân phiên ổn định theo người nói, có override bằng `speaker_id`.

Dùng lại key/region của Azure hiện có, thêm `LISTENING_VOICES`. REST tránh yêu
cầu native SDK cho luồng Listening. API nhận script trực tiếp hoặc đọc bài
Listening đã lưu; dùng bearer hiện có, không đổi schema hay dữ liệu chấm bài.

Nội dung được escape và kiểm tra ký tự XML. Giới hạn script/lượt/SSML/audio,
kiểm tra WAV đầy đủ và bỏ body lỗi Azure giúp tránh trả audio hỏng hoặc lộ khóa.
Timeout là giới hạn chờ I/O kèm kiểm tra elapsed giữa chunk, không phải deadline
cứng. Không cache, không tự retry để tránh lặp yêu cầu có thể tính phí.

## Kiểm chứng

Chạy `.venv/Scripts/python.exe -m pytest backend/tests --ignore=backend/tests/speaking -q -rs`:
482 passed, 29 skipped trong 11,09 giây, gồm 43 test Azure mới. Tất cả test bỏ
qua cần `TEST_DATABASE_URL`; bộ Speaking không nằm trong lần chạy này.

Rà soát đã chấp thuận sau khi xử lý thêm `RuntimeError` từ RIFF sai cấu trúc.
Kiểm tra biên dịch và `git diff --check` đạt. Bộ kiểm thử này dùng HTTP transport
giả lập.

Sau khi người dùng điền cấu hình và yêu cầu chạy thử ngày 2026-11-10, một POST
Azure thật qua API TestClient đã thành công sau khi cấp quyền mạng sandbox.
Azure/API trả 200; 3 lượt nói, 2 người, giọng Ryan/Sonia, hoàn tất trong 3,69
giây. WAV dài 12,55 giây, 602.444 byte, PCM mono 24 kHz, 16 bit, có `no-store`.
Audio và JSON metadata nằm trong `data/listening/` được Git bỏ qua; không ghi
khóa vào báo cáo. Lần thử ngắn dùng storage/agent giả lập tránh truy cập PostgreSQL.

Tiếp đó, lấy bài thật `Welcome to Lotus Residence, Can Tho` từ PostgreSQL
(`0452ee07-8baf-4430-a63f-521b64e22b28`, band 6.0, 592 từ, 10 câu hỏi).
GET bài/GET lượt nói và POST `/api/exercises/{item_id}/audio` dùng `Bank` thật;
Azure/API đều trả 200. Script có 15 lượt của Warden/Student; WAV dài 208,137
giây (3 phút 28 giây), 9.990.644 byte, PCM mono 24 kHz/16 bit có tín hiệu,
`no-store`. Tổng thời gian đo gồm các API đọc là 118,48 giây.
So sánh bài trước/sau xác nhận dữ liệu không đổi. DB đang dừng được khởi động
bằng Compose với volume cũ; test tắt auto-migrate. WAV/JSON nằm trong
`data/listening/azure-db-0452ee07-8baf-4430-a63f-521b64e22b28.*`, được Git bỏ qua.
Đã kiểm chứng luồng bài lưu với PostgreSQL thật; chưa đánh giá bằng nghe trực tiếp.

Hợp đồng API và ví dụ: [Listening Azure Speech](../listening-azure-speech.md).
