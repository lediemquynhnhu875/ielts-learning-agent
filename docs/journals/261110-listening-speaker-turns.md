---
date: 2026-11-10
topic: listening-speaker-turns
---

# Chuẩn bị lượt người nói cho Listening

## Bối cảnh

Script Listening đang nằm trong `CONTENT_ITEM.text`; cần chia lượt để gán giọng
Azure Speech sau này mà không thay đổi dữ liệu dùng kiểm chứng và chấm bài.

## Thay đổi và quyết định

Thêm bộ tách xác định với danh sách người nói, lượt theo thứ tự và vị trí ký tự
trong script gốc. Nhãn vai trò nhận diện cùng dòng; tên riêng được khai báo ở đầu
dòng. Văn bản không nhãn dùng Narrator. Giữ nguyên lời thoại và từ chối lượt rỗng.

Hai API bổ sung nhận script trực tiếp hoặc đọc bài Listening đã lưu, dùng cơ chế
bearer hiện có. Không thêm dependency, migration, audio hoặc gọi dịch vụ ngoài.

## Nhận xét

Quy tắc nhãn cho kết quả lặp lại và giữ được bằng chứng từ script gốc. Đây không
phải suy luận người nói: tiêu đề giống tên và nhãn trong lời trích dẫn còn mơ hồ;
hợp đồng API ghi rõ giới hạn và khuyến nghị nhãn vai trò rõ ràng.

## Kiểm chứng

Rà soát đã chấp thuận sau khi sửa nhãn chồng lấn ở vai trò ghép. Chạy
`.venv/Scripts/python.exe -m pytest backend/tests --ignore=backend/tests/speaking -q`:
430 passed, 29 skipped trong 10,25 giây, gồm 28 test mới. Bộ Speaking không nằm
trong lần chạy này.

Lần rà soát thứ hai phát hiện tên nhiều từ với khoảng trắng/tab khác nhau bị
gộp lượt, tên `O'Connor:` và dòng chỉ xuống bằng `\r` chưa được nhận diện đúng.
Đã sửa quy tắc khớp tên, giữ nguyên offsets. API cũng xử lý lỗi xác thực cục bộ
để JSON chứa Unicode surrogate trả `422` thay vì lỗi mã hóa phản hồi `500`.

Kiểm thử sau sửa: 439 passed, 29 skipped trong 9,64 giây, gồm 37 test Listening
(thêm 9 trường hợp hồi quy). Tất cả test bỏ qua cần `TEST_DATABASE_URL`.
Rà soát đối kháng không có phát hiện mới; thử script tối đa 100.000 ký tự không
ghi nhận regex chạy quá lâu do backtracking.

## Tiếp theo

Gán giọng Azure theo `speaker_id`, tổng hợp từng lượt và ghép audio theo `position`.
