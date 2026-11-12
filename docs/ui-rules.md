# Quy tắc giao diện (frontend)

Áp dụng cho mọi màn trong `frontend/`. Cập nhật 11/11/2026.

Nguồn: Đề tài 06 (mục 1.5, 5), Google Doc "SE373 - idea" (Tab 7, Thiết kế web, Agent Reading, Agent Listening, Agent Writing, flow UI) và các quyết định của nhóm ghi ở mục 1.

## 1. Quyết định đã chốt

| # | Quyết định | Căn cứ |
|---|---|---|
| 1 | Giao diện mâu thuẫn với tài liệu thì sửa giao diện theo tài liệu. Không thêm chức năng tài liệu không có. | Mọi màn, nhãn, luồng phải truy được về tài liệu. |
| 2 | Tài liệu mâu thuẫn nhau thì ưu tiên: Đề tài 06 → Tab 7 → tab chuyên đề (Thiết kế web, Agent …) → mock. | |
| 3 | Không có trang "AI Agent" trên thanh bên. | Không tài liệu nào mô tả. |
| 4 | Không có nút "Đổi trạng thái" ở trang chi tiết bài. | Bài Reading/Listening người học tạo đã qua kiểm chứng tự động và được giao luôn (Tab 7, UC05 bước 7). |
| 5 | Speaking: thi thử chỉ ghi âm. Gõ chữ chỉ ở phiên luyện tập (không gọi là bài thi thử) và phần Speaking của bài test đầu vào khi không có micro; band ghi "tạm tính", Pronunciation không chấm. | Tab 7 (UC01 5a, UC04 4a), tab Thiết kế web. |
| 6 | Giáo viên có 5 màn: Kho đề quản trị, Chi tiết bài, Câu bị báo sai, Hàng đợi duyệt điểm, Màn duyệt điểm (Duyệt / Sửa điểm / Từ chối). | Tab 7, UC03. |
| 7 | Thông báo lỗi hiện nguyên văn thông điệp tiếng Việt của backend, kể cả lỗi của nhà cung cấp model. | Tab Thiết kế web. |
| 8 | Tên thẻ Writing: `Writing Task N: <chủ đề ngắn>` (từ trường `topic`). Thẻ và tiêu đề trang dùng cùng tên. | Đề tài 06, mục 2.1. |
| 9 | Tên thẻ Speaking: `Speaking: <title của cue card>`; trang làm bài dùng cùng tên. | |
| 10 | Speaking một lần làm đủ 3 phần (một thẻ = một bộ Part 1, 2, 3). Cue card do thẻ ở Kho đề quyết định, không chọn lại trong trang làm bài. | Đề tài 06 mục 2.1, Tab 7 UC04. |
| 11 | Writing: bấm "Làm bài" ở Kho đề vào thẳng màn viết, không có trang chọn đề. | |
| 12 | Writing Task 1 có giao diện (biểu đồ, bảng số liệu, 20 phút, tối thiểu 150 từ, tiêu chí TA) và chạy bằng dữ liệu mẫu cho tới khi backend chấm được Task 1. | |
| 13 | Writing không có ô ghi chú (tài liệu chỉ mô tả ghi chú ở Speaking Part 2). | |
| 14 | Reading/Listening có hai chế độ cùng một màn làm bài: Luyện (`/exercises/[id]`, bấm "Làm bài" ở Kho đề) và Thi (`/mock/[id]`, từ trang Thi thử). Thi thử chỉ dành cho người học; giáo viên và người chưa đăng nhập thấy "Trang này dành cho người học". | Tab 7, `docs/reading-listening-practice.md`. |
| 15 | Mở màn làm bài là vào làm luôn, không có màn bắt đầu: có lượt chưa nộp thì mở lại, không có thì tạo lượt mới. Nộp bài có hộp thoại xác nhận, nói rõ số câu chưa trả lời và nộp rồi không sửa được. | |
| 16 | Bài mẫu (id `rl-…`, không có ở backend) chưa làm được; người học thấy "Bài mẫu, chưa làm được". | Backend chỉ có lượt làm cho bài thật. |

## 2. Điểm và nhãn

- Mọi màn có band kèm nhãn: "Điểm ước lượng do AI chấm, chỉ dùng để luyện tập, không thay thế điểm thi chính thức". Không dùng logo hay thương hiệu IELTS.
- Band chưa có (`null`) không vẽ thành số; hiện "—" và nói lý do. Không tự tính band ở client.
- Writing/Speaking: hiện điểm từng giám khảo (A, B). Tiêu chí qua bước đối chiếu ghi "Đã qua đối chiếu"; điểm chờ giáo viên ghi "Tạm tính".
- Dẫn chứng gắn vị trí trong bài làm hoặc transcript; bấm vào thì nhảy tới và tô sáng. Vị trí do backend tính theo code point, nên cắt chuỗi bằng `Array.from`.
- Không có nút để người học yêu cầu chấm lại; ca chuyển giáo viên là tự động.

## 3. Đáp án và dữ liệu

- Đáp án, bằng chứng, transcript, script chỉ trả về sau khi đã nộp bài.
- Người học không thấy trace. Chỉ bài `verified` đến tay người học.

## 4. Trạng thái và lỗi

- Trạng thái khoá phải nói thành lời (một dòng ngắn và đường thoát), không chỉ làm xám nút.
- Speaking tạm dừng bắt buộc có báo và nút Tiếp tục. Nút "Bắt đầu phiên mới" luôn hiện.
- Thao tác chờ lâu nói rõ thời gian dự kiến; khoá nút vừa bấm, không cho gửi lại.
- Không dùng `alert()` hay `confirm()`; xác nhận dùng hộp thoại trong trang.

## 5. Màn làm bài

- Mỗi màn làm bài có nút quay về Kho đề và điều hướng bước.
- Reading: bài đọc trái, câu hỏi phải, cuộn độc lập; điện thoại chuyển hai tab. Đồng hồ đếm ngược, cảnh báo còn 5 phút, hết giờ tự nộp. Tự lưu câu trả lời.
- Reading/Listening tự lưu đáp án sau 1 giây ngưng thao tác; lỗi lưu thì giữ lại thay đổi và có nút Thử lại. Rời trang thì gửi nốt phần đang chờ.
- Listening: tải trọn audio trước. Chế độ thi phát một lần, không tua, hết bài thì khoá; tải lại lúc đang nghe dở thì lượt nghe coi như đã dùng. Chế độ luyện cho tua, nghe lại và đếm số lần.
- Script Listening luôn thu gọn sau nút "Xem script"/"Ẩn script". Chế độ luyện có nút ngay lúc làm bài; chế độ thi lúc làm bài không có script, sau khi nộp mới có nút. Bài chưa có audio thì cả hai chế độ đều có nút, kèm băng "Chưa có audio, tạm làm bằng script".
- Lượt làm Reading/Listening (mã lượt, token, số lần nghe) tạm lưu trong trình duyệt, 5 lượt gần nhất mỗi bài và mỗi chế độ, cho tới khi có đăng nhập và API lịch sử bài làm.
- Kết quả Reading/Listening: header giống màn làm bài (tiêu đề không dịch chỗ), dưới là một hàng tóm tắt: hàng chọn lượt đã nộp, "x/y câu đúng" (có band thì thêm "Band x.x"), nút "Làm lại". Từng câu có ba trạng thái Đúng/Sai/Bỏ trống (biểu tượng trong vòng tròn, có chữ cho trình đọc màn hình, ô số câu cùng màu), câu trả lời cạnh đáp án, giải thích; lọc theo trạng thái kèm số câu, mặc định mở các câu sai. "Xem bằng chứng" tô và cuộn tới chỗ trong bài đọc/script. Thẻ ở Kho đề và Thi thử của bài đã nộp có "Xem kết quả" và "Làm lại".
- Kết quả Listening: có trình phát nghe lại (tua được), chưa có audio thì báo "Bài này chưa có audio"; script thu gọn mặc định, "Xem bằng chứng" tự mở script. "Nghe lại đoạn này" chỉ hiện khi bài có audio kèm mốc thời gian.
- Script Listening hiện theo lượt người nói do backend tách (tên in đậm; phần chữ trước nhãn đầu tiên là "Narrator"); không lấy được hoặc không khớp script thì chia theo đoạn.
- Màn làm bài và màn kết quả Reading/Listening từ 1150px có nút tròn kéo được giữa hai cột (chuột, cảm ứng, phím ←/→, Home/End, nhấp đúp về mặc định), mỗi cột tối thiểu 360px, tỉ lệ lưu trong trình duyệt.
- Chưa làm: đồng hồ đếm ngược Reading/Listening (cảnh báo còn 5 phút, hết giờ tự nộp).
- Writing: đếm từ theo thời gian thực (cùng regex với backend), đồng hồ đếm ngược, tự lưu nháp. Hết giờ thì khoá bài và báo rõ.
- Writing đã chấm: thẻ ở Kho đề của người học có nút "Xem kết quả" và "Làm lại". Kết quả gần nhất tạm lưu trong trình duyệt cho tới khi có đăng nhập và API lịch sử bài làm.
- Speaking: câu hỏi và nút ghi âm luôn thấy không cần cuộn, kể cả trên điện thoại. "Chọn file audio" nhận wav, m4a, mp4, webm, mp3, ogg, flac, tối đa 24 MB.

## 6. Trợ năng

- Trạng thái không phân biệt chỉ bằng màu; đồng hồ có số.
- Thao tác được bằng bàn phím, có viền focus thấy được.
- Thay đổi quan trọng (chuyển phần, hết giờ, chấm xong) báo qua `aria-live`.
- Tôn trọng `prefers-reduced-motion`: tắt hiệu ứng chạy, trôi, đếm ngược động.

## 7. Phong cách

- Glassmorphism theo màn Kho đề: nền gradient kem → cát → xanh có đốm màu mờ, khối kính mờ, thanh bên navy với mục đang chọn là viên cam, nút viên thuốc (navy, cam, kính). Vùng viết/đọc chữ dài dùng kính gần đặc (`glass-paper`, trắng ~86%).
- Header trang làm bài/kết quả: nút tròn quay lại, ô kỹ năng, tiêu đề đậm, dòng phụ nhỏ; đồng hồ hoặc ô điểm bên phải. Không bọc header trong khối kính.
- Đồng hồ là viên kính nhỏ chỉ có biểu tượng và số.
- Ô điểm tổng ở trang kết quả chỉ có nhãn "Điểm ước lượng" và số; chưa có điểm thì "—". Trạng thái (tạm tính, chờ giáo viên, lỗi) do nội dung trang nói.
- Trạng thái chờ, lỗi, xác nhận vẽ thành màn đầy đủ dựng từ màn gốc (nút khoá kèm một dòng trạng thái, lớp phủ kính, hộp thoại).
- Màn rộng (từ 1024px) gói vừa một màn, phần dài cuộn trong khối; màn hẹp hơn thì trang cuộn bình thường.
- Không viền hay quầng màu nổi quanh thẻ; trạng thái thể hiện bằng chip nhỏ.

## 8. Chữ trên giao diện

- Ít chữ, nhãn dễ hiểu. Mỗi thông báo một dòng ngắn; không chép đoạn giải thích từ tài liệu vào giao diện.
- Không chip trùng ý với chữ đã có. Cảnh báo nhỏ viết thành một dòng ngay dưới chỗ liên quan.
- Không nhãn viết hoa toàn bộ, không nối chuỗi bằng "·", không thêm "→" vào nút.
- Không dịch tên đề. Ngày giờ dạng `HH:mm dd/MM/yyyy`, giờ Việt Nam.
- Dữ liệu giả lập để trong `frontend/src/mock-data` (không dùng chữ "sample" trong tên thư mục), ghi rõ phần nào lấy từ tài liệu hay repo.
