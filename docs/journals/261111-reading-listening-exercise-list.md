---
date: 2026-11-11
topic: reading-listening-exercise-list
---

# Liệt kê bài Reading/Listening trong kho đề

## Bối cảnh

Backend đã có API sinh bài và lấy chi tiết theo UUID nhưng chưa có API liệt kê.
Kho đề frontend dùng dữ liệu mẫu; proxy chưa mở GET collection và không chuyển
query string. Người dùng yêu cầu thêm endpoint trên nhánh riêng và commit.

## Thay đổi và quyết định

Thêm `GET /api/exercises` trả `{items, total, limit, offset}` với bộ lọc kỹ năng,
band và tìm chuỗi con trong tiêu đề/chủ đề. Tìm kiếm coi `%`, `_` là ký tự thường.
Sắp mới nhất trước, dùng UUID giảm dần để ổn định thứ tự khi trùng thời điểm.

Truy vấn PostgreSQL lấy tổng và trang trong cùng snapshot, giữ tổng đúng cả khi
offset vượt kết quả cuối. Chỉ liệt kê bài `verified`, không có câu bị loại và đủ
ba lớp kiểm định đều đạt. Tóm tắt dùng danh sách trường cho phép, không lấy nội
dung bài, đáp án hoặc metadata model/trace.

Mở `GET /api/backend/exercises` và giữ query string riêng cho route danh sách.
Giữ bearer phía server và hành vi các route hiện có. Không thêm dependency hoặc
migration; chuyển UI kho đề từ mock sang API và ghép đề thi đủ bài nằm ngoài lần
thay đổi này.

## Kiểm chứng

Rà soát thay đổi không có phát hiện chặn triển khai. Bộ backend đạt **733
passed**, không có failure, skip hoặc warning, gồm kiểm thử tích hợp PostgreSQL
trên `ielts_test` với schema riêng cho từng fixture. Frontend đạt **138/138 test**
trong 16 file; `npm run lint` và `tsc --noEmit --incremental false` đều qua.

Các kiểm thử mới bao phủ xác thực, query không hợp lệ, lỗi CSDL đã làm sạch,
bộ lọc, tìm kiếm ký tự đặc biệt, thứ tự/phân trang, tổng vượt trang cuối và điều
kiện xuất bản. Không gọi dịch vụ AI hoặc sửa dữ liệu bài thật.

## Nhận xét và tiếp theo

API danh sách cung cấp dữ liệu để frontend tải lại kho đề từ PostgreSQL. Bước
tích hợp UI tiếp theo cần thay mock bằng API và đồng bộ lọc/phân trang với server.
