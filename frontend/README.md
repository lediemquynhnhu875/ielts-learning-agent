# Frontend

Ứng dụng giao diện của IELTS Learning Agent, dùng Next.js (App Router), TypeScript và Tailwind CSS, triển khai trên Vercel. Backend UC-04 có thể dùng qua Swagger theo [hướng dẫn chạy](../docs/uc04.md).

## Chạy

```bash
cd frontend
npm install
cp .env.example .env.local   # địa chỉ backend, token (nếu có)
npm run dev     # http://localhost:3000
npm test        # test đơn vị (Vitest)
npm run build   # kiểm tra build
npm run lint
```

Quy tắc giao diện của nhóm: [docs/ui-rules.md](../docs/ui-rules.md).

## Nối backend

Muốn tạo bài và xem chi tiết bài thật, chạy backend UC-04 theo [docs/uc04.md](../docs/uc04.md) (PostgreSQL bằng Docker, provider và API key, uvicorn ở `127.0.0.1:8000`). Cấu hình trong `.env.local`:

| Biến | Ý nghĩa |
|---|---|
| `BACKEND_URL` | Địa chỉ backend, mặc định `http://127.0.0.1:8000`. |
| `API_TOKEN` | Trùng với `API_TOKEN` của backend; để trống nếu backend không bật. Chỉ gửi tới backend UC-04. |
| `SPEAKING_BACKEND_URL` | Địa chỉ agent Speaking, mặc định `http://127.0.0.1:8010`. |
| `WRITING_BACKEND_URL` | Địa chỉ prototype Writing, mặc định `http://127.0.0.1:8765`. |
| `WRITING_MODE` | `live` (mặc định, chấm thật) hoặc `demo` (điểm mô phỏng, chỉ để dev). Server tự đặt `mode` của mỗi lần chấm, trình duyệt không chọn được. |

Các biến này chỉ đọc phía server (không có tiền tố `NEXT_PUBLIC_`), nên token không xuất hiện trên trình duyệt.

Backend không bật CORS, nên trình duyệt gọi qua route trung gian `/api/backend/...` (`src/app/api/backend/[...path]/route.ts`). Route này chỉ chuyển tiếp các endpoint trong bảng cho phép theo tiền tố (`src/lib/backend/proxy-rules.ts`), kiểm tra id là UUID, chờ tối đa 300 giây (5 phút), trả 502 khi không kết nối được backend và 504 khi quá giờ. Thông điệp lỗi của backend được giữ nguyên. Trang chi tiết (server component) gọi thẳng backend bằng cùng danh sách cho phép (`src/lib/backend/server-fetch.ts`).

| Tiền tố | Backend | Endpoint cho phép |
|---|---|---|
| `exercises`, `attempts`, `traces` | UC-04 (`BACKEND_URL`) | `POST exercises`, `GET exercises/{id}`, `GET exercises/{id}/answers`, `GET traces/{id}`; lượt làm Reading/Listening ([docs/reading-listening-practice.md](../docs/reading-listening-practice.md)): `POST exercises/{id}/attempts`, `GET attempts/{id}`, `PATCH attempts/{id}/answers`, `POST attempts/{id}/submit`; Listening ([lượt người nói](../docs/listening-speaker-turns.md), [audio](../docs/listening-azure-speech.md)): `GET exercises/{id}/listening-turns`, `GET exercises/{id}/audio` (WAV), `GET exercises/{id}/audio/timings` |
| `speaking` | Agent Speaking (`SPEAKING_BACKEND_URL`) | `GET cue-cards`, `GET capabilities`, `POST sessions`, `GET sessions/{id}`, `POST sessions/{id}/actions`, `text`, `voice` (multipart, tối đa 24 MB), `assessment`, `GET sessions/{id}/audio/{answerId}` (nhị phân), `GET sessions/{id}/export` |
| `writing` | Prototype Writing (`WRITING_BACKEND_URL`) | `GET status`, `POST assess` |

Cố ý không mở: các `POST` tạo và kiểm chứng audio Listening (API biên soạn, dùng secret của server), `teacher-review` của Speaking (backend chưa kiểm quyền, mở khi có đăng nhập) và các endpoint tài liệu không có màn nhận (tra rubric, transcribe, samples, weakness-profile, attempt-audio, database-schema).

| Phần | Nguồn dữ liệu |
|---|---|
| Form "Tạo bài" của người học | API thật: `POST /api/exercises`. Tạo xong thì lấy lại danh sách từ backend, bài mới nằm đầu. |
| Chi tiết bài có id UUID | API thật: bài, đáp án, trace (5 chặng kiểm chứng, độ giống, model). Người học chỉ gọi bài, không gọi đáp án và trace. |
| Danh sách bài Reading/Listening ở Kho đề (người học) và Thi thử | API thật: `GET /api/exercises` ([docs/uc04.md](../docs/uc04.md)), chỉ bài đã kiểm chứng, mới nhất trước. Lọc theo kỹ năng (`skill`) và ô tìm (`q`, tìm trong tiêu đề và chủ đề), mỗi lần 20 bài (`limit`, `offset`), nút "Xem thêm" theo `total`. Thẻ hiện số câu (`question_count`) và các dạng câu (`question_types`). Có trạng thái đang tải, rỗng và lỗi kèm Thử lại. |
| Kho đề quản trị, bài Writing/Speaking, Câu bị báo sai, đăng nhập | Mock: backend chưa có endpoint (danh sách của backend chỉ có bài đã kiểm chứng, không đủ cho Kho đề quản trị). |
| Màn viết Writing Task 2 (`/writing/[id]`) | API thật: `GET writing/status`, `POST writing/assess` (prototype Writing). Đề lấy từ mock. |
| Màn viết Writing Task 1 | Mock: backend chưa chấm Task 1; nộp bài hiện kết quả mẫu (`sampleTask1Result`), có băng "Chế độ mô phỏng" như chế độ demo của Task 2. |
| Làm bài Reading/Listening (Luyện `/exercises/[id]`, Thi `/mock/[id]`) | API thật, chỉ với bài UUID đã `verified`: tạo lượt, tự lưu đáp án (gom sau 1 giây ngưng thao tác, tối đa 40 câu mỗi request), nộp và chấm. Bài mẫu (`rl-…`) chưa làm được. |
| Lượt làm Reading/Listening | Lưu trong trình duyệt (`localStorage`, khoá `rl-attempts:{luyện/thi}:{id}`, 5 lượt gần nhất mỗi bài): mã lượt, token (backend chỉ trả một lần), số lần nghe, đã nghe hết, đã nộp, số câu đúng (cho hàng chọn lượt). Gắn với trình duyệt, không gắn tài khoản, vì chưa có đăng nhập. Mất token thì không mở lại được lượt đó. |
| Xem lại kết quả Writing, Làm lại | Lưu trong trình duyệt (`localStorage`, 5 lượt gần nhất mỗi đề), vì chưa có đăng nhập và backend Writing chưa có API lấy lại kết quả. Thẻ Writing đã chấm ở Kho đề của người học có nút "Xem kết quả" và "Làm lại". |

Thông điệp lỗi tiếng Việt của backend hiện nguyên văn, kể cả lỗi của provider LLM (`src/lib/api/errors.ts`); lỗi chỉ có câu tiếng Anh kỹ thuật (ví dụ 404, 401 của UC-04) được đổi sang câu tiếng Việt. Lỗi sinh bài kèm mã tra cứu (8 ký tự đầu `trace_id`).

### Trước khi deploy

- Route trung gian đang mở cho mọi người: cần đăng nhập và giới hạn số lần gọi `POST /api/exercises`, vì mỗi lần sinh bài tốn lượt gọi API key.
- `/answers` và `/traces` chỉ dành cho quản trị: cần kiểm tra vai trò ở route trung gian khi có đăng nhập.
- Vercel: `maxDuration = 300` của route (5 phút) cần gói Vercel cho phép thời gian chạy dài như vậy; nếu không, giảm cả hai con số trong `route.ts` và `server-fetch.ts`; đặt `BACKEND_URL` và `API_TOKEN` trong Environment Variables của dự án.

## Cấu trúc

```
src/
  app/            routes và layout (App Router); api/backend là route trung gian tới backend
  components/     thành phần giao diện dùng chung (khung trang, thanh bên, icon, trang báo cho người học)
  features/       luồng nghiệp vụ: exercise-bank (Kho đề, Thi thử), exercise-detail (chi tiết bài cho quản trị),
                  reading-listening (làm bài, lượt làm, tự lưu nháp, trình phát audio), writing (màn viết)
  lib/            api (client, lỗi, kiểu DTO), backend (chuyển tiếp phía server), định dạng ngày giờ
  mock-data/      dữ liệu giả lập cho phần backend chưa có endpoint
```

## Màn hình

| Route | Nội dung |
|---|---|
| `/exercises` | Kho đề. Quản trị: card có trạng thái, thẻ Câu bị báo sai và Trạng thái kho. Người học: bài Reading/Listening đã kiểm chứng từ `GET /api/exercises` (phân trang "Xem thêm"), bài Writing/Speaking mẫu, form Tạo bài mới (Reading/Listening). |
| `/exercises/[id]` | Chi tiết bài cho quản trị: Reading/Listening (bài đọc, câu hỏi, đáp án, bằng chứng, 5 chặng kiểm chứng UC-04, độ giống), Writing (đề, thời gian, số từ, tiêu chí chấm), Speaking (Part 1–3). Người học: bài Reading/Listening UUID vào màn làm bài chế độ Luyện; bài mẫu hiện "Bài mẫu, chưa làm được"; Writing chuyển sang `/writing/[id]`; Speaking còn trang tạm "Làm bài". |
| `/mock` | Thi thử, chỉ người học (mục "Thi thử" ở thanh bên): danh sách bài Reading/Listening từ `GET /api/exercises`, cùng nguồn với Kho đề. Giáo viên và người chưa đăng nhập thấy "Trang này dành cho người học". |
| `/mock/[id]` | Màn làm bài chế độ Thi, chỉ người học. Cùng màn với chế độ Luyện, khác ở Listening: audio phát một lần, không tua, hết bài thì khoá, tải lại lúc đang nghe dở thì tính là đã nghe; lúc làm bài không có script. Luyện cho tua, nghe lại, đếm số lần và có nút "Xem script". Bài chưa có audio thì cả hai chế độ có nút "Xem script" kèm băng báo. |
| `/writing/[id]` | Màn viết Writing (Task 2 chấm qua backend, Task 1 kết quả mẫu): đồng hồ, đếm từ, tự lưu nháp, đang chấm, kết quả có dẫn chứng tô sáng, chấm lỗi. Thẻ Writing của người học mở thẳng trang này. |

Màn làm bài Reading/Listening: mở màn là vào làm (mở lại lượt chưa nộp đã lưu, không có thì tạo lượt mới). Hộp thoại xác nhận trước khi nộp, báo số câu chưa trả lời. Màn kết quả (mở lại bằng `?view=result`; `?redo=1` tạo lượt mới): hàng tóm tắt (các lượt đã nộp, đọc lại bằng `GET attempts/{id}`; số câu đúng; band nếu backend trả), từng câu Đúng/Sai/Bỏ trống kèm câu trả lời, đáp án và giải thích của backend, lọc theo trạng thái, "Xem bằng chứng" tô chỗ tương ứng trong bài đọc/script. Listening có trình phát nghe lại, script thu gọn mặc định và hiện theo lượt người nói (lấy từ `GET exercises/{id}/listening-turns`; mốc ký tự của backend tính theo code point nên được quy đổi trước khi cắt chuỗi; lượt không khớp script thì chia theo đoạn). Hai cột có nút kéo đổi bề rộng từ 1150px (tỉ lệ lưu ở `localStorage`, khoá `rl-split`). Thẻ bài đã nộp ở Kho đề và Thi thử có "Xem kết quả" và "Làm lại". Hiện chưa có: đồng hồ đếm ngược; Audio Listening: màn làm bài tự gọi `GET exercises/{id}/audio/timings` rồi phát `GET exercises/{id}/audio` qua route trung gian, vì `GET attempts/{id}` chưa trả audio. Chỉ bài có audio đã qua kiểm chứng mới có; gặp `409 audio_not_verified`, `404` hoặc lỗi mạng thì màn làm bài dùng trạng thái chưa có audio (băng báo và nút "Xem script"), không báo lỗi. "Nghe lại đoạn này" ở màn kết quả phát đoạn của các lượt nói chứa bằng chứng, chọn theo khoảng ký tự `source_start_char`–`source_end_char` của timings.

Các mục khác ở thanh bên hiện là trang tạm. Ngày giờ hiển thị theo dạng `HH:mm dd/MM/yyyy`, múi giờ Việt Nam.

Khi thêm tính năng, tổ chức theo trách nhiệm:

- Routes trong `src/app`: màn hình và điều hướng.
- Features: luồng nghiệp vụ như Kho đề, làm bài Reading/Listening, xem kết quả.
- Shared UI trong `src/components`: thành phần tái sử dụng giữa các feature.
- API clients trong `src/lib/api`: gọi backend, kiểu DTO và xử lý lỗi HTTP; ánh xạ DTO sang dữ liệu giao diện làm ở feature.

Backend trả câu hỏi theo nhóm `question_groups`; frontend dùng `number` để hiển thị số câu và giữ nguyên các hướng dẫn/lựa chọn chung của group.

## Hệ thiết kế

Token nằm trong `src/app/globals.css` (khối `@theme`) và dùng được như class Tailwind, ví dụ `bg-navy`, `text-muted`, `bg-skill-writing`.

- Màu nền và nhấn: `cream`, `sand`, `orange`, `navy`, `navy-deep`, `muted`.
- Màu kỹ năng: `skill-reading`, `skill-listening`, `skill-writing`, `skill-speaking`.
- Trạng thái: `status-verified`, `status-spare`, `status-rejected`, `status-correct` (kèm `-text` cho chữ). Trạng thái luôn hiển thị bằng màu, hình và chữ, không dùng màu đơn thuần.
- Kính: `glass` (khối nội dung), `glass-card` (card danh sách), `glass-navy` (thanh bên).
- Chữ: Be Vietnam Pro (tự host qua `@fontsource/be-vietnam-pro`), số dạng tabular.
- Trên nền cam dùng chữ navy, không dùng chữ trắng.

## Dữ liệu giả lập

`src/mock-data` chứa dữ liệu dùng tạm khi backend chưa có endpoint tương ứng (Kho đề quản trị, bài Writing/Speaking, đổi trạng thái, báo sai, đăng nhập). Mỗi file ghi rõ là giả lập và phần nào lấy từ tài liệu/repo; khi có API thì thay bằng API client.

| File | Nội dung |
|---|---|
| `session.ts` | Người dùng đang đăng nhập. Đổi `mockSession` giữa `mockTeacher`, `mockLearner` hoặc `null` để xem giao diện quản trị, người học (form Tạo bài, Thi thử, làm bài) hoặc khi chưa đăng nhập. |
| `reading-listening.ts` | Bài Reading/Listening mẫu theo hình dạng `GET /api/exercises/{id}` và trace UC-04 (id `rl-…`, không phải UUID). |
| `writing.ts` | Đề Writing; thời gian, số từ, tiêu chí theo UC-02. Đề Task 2 lấy từ đề tài; đề Task 1, số liệu biểu đồ và kết quả mẫu Task 1 viết tạm cho giao diện. |
| `speaking.ts` | Bộ đề Speaking lấy từ `docs/speaking/examples/database-export-text.json`. |
| `reports.ts` | Câu bị báo sai (bảng `QUESTION_REPORT`). |
| `exercises.ts` | Gộp 4 kỹ năng thành danh sách card; đếm theo trạng thái. |

## Bảo mật

API key OpenAI/DeepSeek chỉ ở backend; `API_TOKEN` chỉ ở server của Next.js. Endpoint đáp án và trace hiện phục vụ việc quản trị/đánh giá; khi xây dựng luồng người học, cần thiết kế phân quyền và thời điểm hiển thị đáp án trong phạm vi tính năng đó.
