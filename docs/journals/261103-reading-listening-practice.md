---
date: 2026-11-03
topic: reading-listening-practice
---

# Backend làm bài Reading/Listening

## Bối cảnh

UC-04 đã sinh và kiểm chứng đáp án, nhưng chưa có lượt làm của người học.
Thêm luồng bắt đầu, lưu nháp, mở lại, nộp và đọc kết quả cho một content item.

## Thay đổi và quyết định

- Chấm bốn dạng câu bằng code theo key; dùng cùng bộ đếm từ với validator.
- Chụp nội dung và key cùng transaction để việc sửa đề không đổi kết quả lượt cũ.
- Lưu nháp/kết quả trong PostgreSQL; row lock bảo vệ nộp và lưu đồng thời.
- Dùng token riêng từng lượt, chỉ lưu hash vì repo chưa có danh tính người học.
- Bài ngắn chỉ trả điểm thô/tỷ lệ đúng, `band=null`; Listening vẫn là script.
- Bảng phát triển độc lập không suy diễn schema SESSION/EXAM hay answer sets.

## Giới hạn và bước tiếp

Token từng lượt chưa thay thế tài khoản hoặc phân quyền quản trị/học viên: API
đáp án/trace cũ vẫn dùng bearer chung. UI làm bài, audio, đề đủ 40 câu và tổng hợp
theo phiên học cần triển khai riêng.

## Xác minh cuối

Toàn bộ backend chạy với PostgreSQL tạm và schema kiểm thử cô lập: **460 passed,
19 skipped, 15 subtests trong 32,72 giây**. Luồng HTTP thực đã kiểm tra lưu nháp,
khởi tạo lại app, nộp và đọc lại kết quả; kiểm thử lưu trữ có tình huống đồng thời.
Review chấp nhận sau khi bổ sung kiểm tra Unicode/NUL; compile và diff check đạt.
Container kiểm thử đã dọn; thay đổi frontend đồng thời được giữ nguyên.
Xem [báo cáo xác minh](../../plans/261103-reading-listening-attempts/reports/verification.md).
