# Tách script Listening thành lượt người nói

Backend tách script bằng quy tắc xác định, không gọi LLM. Kết quả được dùng để
gán giọng cho [API tạo audio Azure Speech](listening-azure-speech.md). Các API
tách lượt dưới đây chỉ trả văn bản, không gọi Azure hoặc lưu lượt nói vào CSDL.
Script gốc, API sinh bài và chấm điểm giữ nguyên.

## API

Nếu cấu hình `API_TOKEN`, cả hai endpoint yêu cầu
`Authorization: Bearer <API_TOKEN>` giống API UC-04.

| Endpoint | Đầu vào | Kết quả |
|---|---|---|
| `POST /api/listening/turns` | JSON `{"script":"Man: Hello. Woman: Hi."}` | `200`, danh sách người nói và lượt nói |
| `GET /api/exercises/{item_id}/listening-turns` | UUID bài Listening đã lưu | `200`, tách trường `text` của bài |

Ví dụ phản hồi cho script trên:

```json
{
  "speakers": [
    {"id": "speaker_1", "label": "Man"},
    {"id": "speaker_2", "label": "Woman"}
  ],
  "turns": [
    {"position": 1, "speaker_id": "speaker_1", "text": "Hello.", "start_char": 5, "end_char": 11},
    {"position": 2, "speaker_id": "speaker_2", "text": "Hi.", "start_char": 19, "end_char": 22}
  ]
}
```

`position` bắt đầu từ 1. ID người nói được gán theo lần xuất hiện đầu tiên có
lời thoại, ổn định khi tách lại cùng script; ID không dùng chung giữa các bài.
Nhãn khác chữ hoa/thường hoặc khoảng trắng được xem là cùng người, giữ nhãn
hiển thị đầu tiên. Hai lượt liên tiếp cùng người vẫn là hai lượt riêng.

`start_char` và `end_char` là chỉ số ký tự Unicode theo Python trong **script
gốc**, đầu bao gồm và cuối không bao gồm:
`script[start_char:end_char] == turn.text`. Khoảng trắng ngoài lời thoại và nhãn
người nói không thuộc `text`; nội dung, dấu câu và xuống dòng bên trong giữ nguyên.
Client JavaScript cần lưu ý chỉ số UTF-16 khác Python khi có ký tự ngoài BMP.

## Nhãn và giới hạn

- Nhãn vai trò có dấu `:` dùng được ở đầu dòng hoặc cùng dòng: `Narrator`,
  `Receptionist`, `Caller`, `Man`, `Woman`, `Interviewer`, `Interviewee`, `Tutor`,
  `Lecturer`, `Professor`, `Student`, `Guide`, `Customer`, `Agent`, `Assistant`,
  `Librarian`, `Advisor`, `Adviser`, `Speaker`, `Clerk`, `Presenter`, `Host`, `Guest`.
  Có thể thêm số hoặc một chữ cái, ví dụ `Speaker 1:` và `Student A:`.
- Tên riêng phải có nhãn ở đầu một dòng, ví dụ `Alice:` hoặc `John Smith:`;
  các lần xuất hiện cùng tên cũng nhận diện được trong hội thoại cùng dòng. Quy tắc tên
  hiện hỗ trợ 1–3 từ chữ Latin viết hoa chữ đầu, với dấu nối/nháy ở từ đầu,
  ví dụ `O'Connor:`. Khi lặp lại tên đã nhận diện, chữ hoa/thường, nhiều dấu cách
  hoặc tab giữa các từ không làm thay đổi người nói.
  Nhãn ghép `Travel Agent:` và `Tour Guide:` dùng cùng quy tắc này: cần được
  khai báo ở đầu dòng trước khi nhận diện các lần xuất hiện cùng dòng.
- Văn bản trước nhãn đầu tiên, hoặc toàn bộ script không có nhãn, thuộc
  `Narrator`. Dòng không có nhãn sau một lượt tiếp tục thuộc người đang nói.
- Các tiêu đề `Note:`, `Notes:`, `Section:`, `Part:`, `Introduction:`, `Script:`,
  `Transcript:`, `Title:`, `Example:`, `Time:`, `Warning:`, `Summary:` và
  `Instructions:` được giữ như nội dung, không tạo người nói. Nhãn không phải
  suy luận danh tính thật: tiêu đề khác giống tên, chẳng hạn `Opening Hours:`
  ở đầu dòng, có thể bị xem là người nói. Vai trò trong nội dung cũng có thể mơ hồ.
  Nên dùng script có nhãn vai trò rõ ràng; không dùng các nhãn dành riêng này
  để viết nội dung trích dẫn có dấu `:`.
- Body POST chỉ nhận `script`, chuỗi không rỗng, tối đa 100.000 ký tự, không có
  NUL hoặc Unicode surrogate. Nhãn không có lời thoại bị từ chối thay vì bỏ qua.

| HTTP | Tình huống |
|---|---|
| `400` | Body JSON có byte không phải UTF-8 hợp lệ |
| `401` | Thiếu/sai bearer khi bật `API_TOKEN` |
| `404` | Không tìm thấy bài khả dụng |
| `422` | Body/script không hợp lệ, lượt rỗng, UUID sai hoặc bài không phải Listening |
| `503` | PostgreSQL/schema chưa sẵn sàng khi đọc bài đã lưu |

Lỗi xác thực đầu vào `422` trả `detail` gồm `type`, `loc`, `msg`, không phản
chiếu script trong `input`. Unicode surrogate trong chuỗi JSON bị từ chối bằng
`422`, không gây lỗi server khi mã hóa phản hồi.

## Tham khảo

- [Làm bài và chấm Reading/Listening](reading-listening-practice.md)
- [Sinh bài UC-04](uc04.md)
