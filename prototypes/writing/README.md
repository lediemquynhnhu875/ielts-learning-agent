# Writing Task 2 — bản MVP độc lập

## Chạy ngay

Yêu cầu Python >=3.10. Ứng dụng demo không cần cài thêm thư viện.

```powershell
cd <thu-muc-ielts-writing>
python app.py
```

Mở http://127.0.0.1:8765, nhập bài và chọn Demo. Demo dùng điểm cố định để kiểm
hai giám khảo, validator, moderator và log. **Không đánh giá band của người học.**

## Chấm thật

1. Tải Writing Band Descriptors từ nguồn chính thức:
   https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf
2. Kiểm tra trang bảng Task 2 (bản May 2023: trang PDF 7–9).
3. Nhập PDF trên máy:

```powershell
python -m pip install pypdf
python import_rubric.py "C:\duong-dan\ielts-writing-band-descriptors.pdf"
```

Importer giữ nguyên các bảng Task 2 đầy đủ, không tự dựng descriptor theo band.
Mỗi tiêu chí nhận cùng bảng đầy đủ và yêu cầu dùng đúng cột. Cần kiểm tra rubric.json
thủ công vì PDF có thể trích xuất sai thứ tự cột. Không công bố raw PDF/rubric lên
repo khi chưa kiểm tra điều kiện sử dụng. Không có rubric thật thì live từ chối chấm.

4. Với OpenRouter, làm theo OPENROUTER.md: chạy setup_openrouter.py để tạo .env.
   App tự đọc .env. Một OPENROUTER_API_KEY dùng chung cho ba model.
   Hoặc cấu hình biến môi trường riêng từng provider như ví dụ dưới.
   Ví dụ (không ghi key thật vào source hoặc commit):

```powershell
$env:WRITING_A_BASE_URL = 'https://your-provider.example/v1'
$env:WRITING_A_MODEL = 'your-model-id'
$env:WRITING_A_API_KEY = '<your-key>'
```

Làm tương tự cho B và MODERATOR, khởi động lại app, chọn Live. Adapter dùng giao thức
Chat Completions tương thích với JSON response_format. Provider không hỗ trợ giao
thức này cần adapter riêng. Feedback dùng model A. Chưa chạy kiểm chứng provider thật.

## Chức năng đã triển khai

- Giao diện nhập đề/bài, đếm từ, xem điểm tiêu chí và evidence, tải JSON/trace.
- Hai giám khảo độc lập; tối đa 1 lượt đầu + 2 lần sửa đầu ra không hợp lệ.
- Kiểm đủ tiêu chí, band, quote, vị trí và mã rubric đúng tiêu chí.
- Đối chiếu khi một tiêu chí lệch >=1.0; lệch >=1.5 có điểm tạm cần người xem.
- Feedback tối đa hai câu, kiểm quote trước khi lưu lỗi vào SQLite local.
- Hai tool get_writing_rubric, save_writing_errors; tài liệu quy trình skill riêng.
- Lưu runs và lỗi không trùng theo attempt_id + error_code + quote.

## Chính sách và tích hợp

- Offset là Unicode code points, đầu bao gồm/cuối không bao gồm. Frontend JS cần
  dùng Array.from(text) khi tô sáng thay vì String.slice trên code units.
- Giữ điểm trung bình tiêu chí dạng thô (có thể .25/.75). Điểm Task 2 hiển thị
  làm tròn half-up 0.5 đúng một lần, là chính sách sản phẩm chưa hiệu chỉnh.
- overall_band ở đây chỉ là ước lượng bài Task 2, không phải điểm toàn Writing.
- Schema outbound hiện là DTO prototype, chưa khớp hoàn toàn database của nhóm.
  Adapter cần ánh xạ ASSESSMENT, GRADING, GRADING_CRITERION, EVIDENCE_SPAN,
  CRITERION_REF, RECONCILIATION, FINAL_SCORE; Planning tiếp nhận lỗi để tạo memory.
- errors hiện lưu local; không gọi Planning API. Mã lỗi do model tạo phải được
  ánh xạ taxonomy chung trước khi tích hợp. Regrade/retraction chưa xử lý.
- final nghĩa là pipeline hoàn tất, không có nghĩa đã được giáo viên duyệt.
- Evidence tồn tại không chứng minh nhận xét đúng; cần đánh giá có người chấm.

## Kiểm thử

```powershell
python -m unittest -v test_app
```

16 ca chức năng, không phải benchmark độ chính xác band. Không cần dataset lớn
để chạy. Các ca có provider dùng mock và không chứng minh chất lượng model thật.

## Chưa hoàn thiện

Chưa có Task 1, sinh đề, đếm giờ, giáo viên duyệt, đồng bộ Planning, telemetry chi phí,
dataset có nhãn, hiệu chỉnh điểm, CI trong repo nhóm. Quy trình skill chưa được đăng
ký theo framework của nhóm. Đây là bản local cho phát triển, không triển khai public.
Không nhập dữ liệu nhạy cảm khi gửi bài qua provider bên ngoài.

## Thứ tự tiếp tục

1. Chạy demo, kiểm JSON cùng bạn Speaking và Planning.
2. Nhập rubric, cấu hình provider nhóm, chạy 3–5 bài thật.
3. Ánh xạ schema/taxonomy và thay persistence bằng repository/API chung.
4. Đánh giá trên dev/test có điểm người chấm, sau đó mới báo MAE/QWK.
