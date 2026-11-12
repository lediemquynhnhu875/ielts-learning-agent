---
date: 2026-11-03
topic: startup-migrations
---

# Tự chạy migration khi khởi động

Backend trước đây yêu cầu chạy `init` riêng, khiến các bảng làm bài mới chưa xuất
hiện khi chỉ mở ứng dụng. Lifespan nay chạy migration trước khi nhận request;
`DATABASE_AUTO_MIGRATE=false` giữ lựa chọn dùng CLI.

Ledger và advisory lock cho phép chạy mỗi file một lần, rollback cả batch lỗi
và kiểm tra file lịch sử. Hash nội dung chuẩn hóa xuống dòng dùng được trên
Windows/Linux. Bỏ mount SQL ở Docker entrypoint để tránh chạy trùng với API.

Kiểm thử bao gồm database trống, nâng cấp CSDL cũ giữ nội dung, chạy đồng thời,
rollback, checksum, tùy chọn môi trường và dọn tài nguyên khi startup lỗi.

Xác minh PostgreSQL thật: 490 test passed, 19 skipped, 15 subtests; compile,
kiểm tra diff và cấu hình Docker Compose đều đạt. Container test không gắn volume
đã được dọn sau khi chạy. Database thật của người dùng không bị thay đổi.
