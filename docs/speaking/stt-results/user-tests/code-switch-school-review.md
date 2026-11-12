# Kiểm tra STT trên câu có tên trường tiếng Việt — 16/10/2026

Nguồn là audio 8,28 giây đã được người học chọn lưu trong demo, answer_id `dc0afd97-330d-46a5-94ce-ab715ac37606`. Người học mô tả câu mong đợi: `I'm studying at Ngô Gia Tự High School`. Đây là lời người học báo lại, chưa có transcript chuẩn được người nghe độc lập xác nhận.

Người học đã đồng ý gửi lại bản thu này tới Groq cho tối đa 4 cấu hình. Đã chạy đúng 4 lời gọi thành công; không gửi bản thu khác. Dữ liệu provider và timestamps giữ trong [code-switch-school-comparison.json](code-switch-school-comparison.json). Báo cáo không ghi API key và không nhúng bytes audio.

## Groq thực tế

Mọi lượt dùng endpoint transcriptions, tự nhận diện ngôn ngữ (không truyền language), temperature=0 và word/segment timestamps. Khoảng trắng đầu/cuối được bỏ khi trình bày bảng; không chỉnh từ trong kết quả.

| Cấu hình | Prompt | Transcript provider | Thời gian API |
| --- | --- | --- | --- |
| V3 Turbo | Không | Tôi đang học hiện tại Ngôi Dê Tự HIGH SCHOOL | 0,935 s |
| V3 | Không | I'm currently a student in Ngoi Gia Tuk High School. | 1,805 s |
| V3 | Ngô Gia Tự | I'm currently a student in Gô Gia Tự High School. | 0,718 s |
| V3 | Chỉ dẫn verbatim/no translation và tên trường | I'm currently a student in Ngo Gia Tự High School. | 0,488 s |

Turbo tái hiện chính xác lỗi output tiếng Việt người học báo. Ba lượt V3 giữ phần câu tiếng Anh nhưng vẫn sai cách viết tên riêng. Không lượt nào khớp nguyên văn câu người học ghi lại; không đánh dấu bài kiểm tra này là đã giải quyết hoàn toàn. Thời gian chỉ của từng lượt, không đại diện latency chung của model.

## Local thực tế, không gửi audio ra ngoài

Chạy model V3 Turbo CPU int8 đã có sẵn trong cache, task=transcribe, language=None, multilingual=True, không cắt pause:

- Không prompt: `I'm currently a student in Ngô Gia Tự High School.` — 9,891 s.
- Chỉ dẫn verbatim/no translation: `I'm currently a student in Ngô Yê Tự High School.` — 11,348 s.
- Chỉ gợi ý `Ngô Gia Tự`: `I'm currently a student in Ngô Gia Tự High School.` — 10,576 s.

Xem [local](code-switch-school-local.json) và [local prompt trials](code-switch-school-local-prompts.json). Local giữ tên tốt hơn trong clip này, nhưng vẫn chưa khớp từng từ với câu người học ghi. Chỉ dẫn “không dịch” không tạo bảo đảm và có thể làm kết quả khác đi. Không tự cài hoặc tải model mới trong phép thử local.

## Thay đổi được triển khai

1. Groq mặc định V3 thay Turbo; `SPEAKING_STT_MODEL` cho phép cấu hình lại. Không cố định en hoặc vi.
2. Prompt filler đổi sang danh sách tiếng đệm, bỏ các câu ví dụ Việt/Anh có thể ảnh hưởng nội dung giải mã.
3. Thêm field `vocabulary` cho cả hai API và ô tên riêng trên cả hai demo. Chỉ dùng làm spelling hint trước nhận dạng; không hardcode tên trường vào thuật toán hoặc sửa transcript bằng dịch ngược.
4. Khi tên gợi ý chưa xuất hiện nguyên văn, trả warning cần nghe lại; không tự chèn tên, sửa từ hay tạo timestamps giả.
5. Response/health ghi model thực và policy `original_language_context_v2`. Benchmark mới cũng ghi model/policy từng lượt.

50 unit/API tests đã qua, gồm 9 test cấu hình/pipeline ngôn ngữ. Test giả lập chứng minh việc truyền tham số và giữ output provider, không chứng minh model luôn chép nguyên văn. Một clip chưa đủ để chọn model cho mọi người học. Bước đánh giá còn lại là nghe và xác nhận transcript thực, bổ sung nhiều câu Việt/Anh/xen tên riêng, đo cả việc đổi ngôn ngữ và lỗi nhận dạng tên; không chỉ kiểm tra output trông đúng ngữ pháp.
