# Tạo audio Listening bằng Azure Speech

Backend tách script theo [lượt người nói](listening-speaker-turns.md) và gán
giọng cho mỗi `speaker_id`. Có hai luồng: preview script trực tiếp và biên soạn
audio cho bài Listening đã lưu. Luồng bài DB đo timeline, nhận dạng lại bằng
STT, kiểm tra từng đáp án rồi lưu; chỉ artifact đạt mới được cấp cho người học.
Xem [hợp đồng kiểm chứng và phát hành](listening-audio-verification.md).

## Cấu hình

```dotenv
AZURE_SPEECH_KEY=<key của Speech resource>
AZURE_SPEECH_REGION=<region của resource, ví dụ southeastasia>
LISTENING_VOICES=en-GB-SoniaNeural,en-GB-RyanNeural
API_TOKEN=<secret biên soạn của server>
```

Key/region dùng chung với Speaking. TTS dùng REST qua `httpx`; kiểm chứng STT
cần SDK tùy chọn: `python -m pip install -e '.[listening-stt]'`.
`LISTENING_VOICES` là pool phân cách bằng dấu phẩy, mặc định Sonia/Ryan. Giọng
luân phiên theo thứ tự người nói, không suy luận giới tính; nhiều người có thể
dùng chung giọng. Gửi map `voices` để override theo ID có trong kết quả tách.
Tên giọng phải là Neural shortname và khả dụng với resource/region.

Migration `003_listening_audio.sql` tạo nơi lưu WAV, timeline và báo cáo riêng.
Startup áp dụng migration còn thiếu khi bật `DATABASE_AUTO_MIGRATE`; xem
[migration CSDL](database-migrations.md).

## API biên soạn

Các POST audio cần cấu hình `API_TOKEN` và bearer token hiện có; thiếu cấu hình
thì trả `503`. Đây là secret server, không cấp cho browser/người học. Frontend
proxy chưa mở các route biên soạn. Lời thoại được escape thành XML; client không
gửi SSML tùy ý. Không có tự retry, mỗi lần tạo có thể phát sinh phí Azure.

| Endpoint | Hành vi |
|---|---|
| `POST /api/listening/audio` | Preview script trực tiếp, một SSML nhiều giọng, trả WAV |
| `POST /api/listening/audio/verify` | Preview và STT toàn văn, trả WAV base64 và báo cáo chẩn đoán |
| `POST /api/exercises/{item_id}/audio` | Tạo TTS từng lượt, kiểm chứng đáp án/timestamp và lưu; chỉ đạt mới trả WAV, không đạt trả `409` |
| `POST /api/exercises/{item_id}/audio/verify` | Cùng pipeline lưu bài, trả báo cáo riêng `verified`/`blocked`; bản chặn không có audio base64 hoặc URL |

Preview không có đáp án DB nên không xác nhận điều kiện phát hành. Body script
trực tiếp gồm `script` và `voices` tùy chọn. Các POST bài lưu nhận không body
hoặc `{"voices":{...}}`. Ví dụ tạo bài đã lưu:

```powershell
$base = 'http://127.0.0.1:8000'
$headers = @{ Authorization = "Bearer $env:API_TOKEN" }
$itemId = '<UUID bài Listening đã lưu>'
Invoke-WebRequest -Method Post -Uri "$base/api/exercises/$itemId/audio" `
    -Headers $headers -OutFile 'exercise-listening.wav'
```

POST trên nay có cổng kiểm chứng; response WAV thành công giữ định dạng cũ.
Muốn xem lý do chặn, dùng POST `/audio/verify` trong công cụ biên soạn riêng,
không đưa báo cáo đó cho learner.

## Audio và timeline đã lưu

`GET /api/exercises/{item_id}/audio` tải WAV hiện hành đã xác minh, không gọi
Azure lại. `GET /api/exercises/{item_id}/audio/timings` cấp các mốc lượt nói để
player dùng `start_seconds`/`end_seconds`; UI player chưa được thêm.
Cả hai chỉ trả dữ liệu khi trạng thái, nguồn/đáp án, cấu hình pipeline/giọng và
hash audio/manifest còn hợp lệ. Bản chặn, thiếu hoặc cũ trả `409 audio_not_verified`.

WAV là PCM mono 24 kHz, 16 bit. Trong luồng bài DB, mỗi lượt có một request TTS
riêng; backend kiểm tra rồi ghép PCM và đo cửa sổ bằng frame. STT tạo word
timestamps độc lập; so sánh không ước lượng mốc thời gian từ chiều dài script.
WAV, manifest và báo cáo riêng lưu trong `listening_audio`, gồm cả bản chặn để
rà soát. Timeline công khai chỉ có 8 trường lượt nói, không có đáp án/bằng chứng.

GET theo cơ chế bearer chung nếu `API_TOKEN` có giá trị. Nếu không cấu hình
token, GET artifact đã xác minh vẫn được phép công khai; điều kiện phát hành
luôn áp dụng. Secret server không phải thông tin đăng nhập của người học.

## Giới hạn và lỗi

- Script tối đa 12.000 ký tự, 50 lượt; SSML mỗi request tối đa 64.000 byte.
- WAV tối đa 29.000.000 byte, ngắn hơn 599 giây, phải đầy đủ PCM mono 24 kHz/16 bit.
- Preview có ngân sách 120 giây; chuỗi timed TTS có ngân sách 300 giây. HTTP có
  timeout I/O và kiểm tra elapsed giữa chunk, không phải deadline cứng toàn phiên.
- `voices` tối đa 50 phần tử, ID phải thuộc script và tên giọng phải đúng dạng.
  Quy tắc nhãn của bộ tách vẫn áp dụng; không suy luận danh tính thật.
- Response audio, timing và báo cáo dùng `no-store`. Không phản chiếu key/body
  lỗi Azure. `401` sai bearer, `404` bài không khả dụng, `409` không đủ điều kiện
  cấp audio, `422` đầu vào sai, `502` lỗi dịch vụ/audio, `503` thiếu cấu hình hoặc
  bị giới hạn tài nguyên, `504` timeout. Lỗi DB hiện có vẫn áp dụng.

## Kiểm chứng

Trước pipeline kiểm chứng đáp án/timestamp, Azure đã trả preview thật 3 lượt,
2 giọng Ryan/Sonia dài 12,55 giây. Luồng DB trước đó cũng tạo WAV 208,137 giây
cho `Welcome to Lotus Residence, Can Tho` (band 6.0, 592 từ, 10 câu, 15 lượt).
Các lần thử này chứng minh TTS/API hoạt động, không thay cho quyết định phát
hành của pipeline mới. WAV và metadata cục bộ ở `data/listening/`, được Git bỏ qua.

Kiểm thử đầy đủ với PostgreSQL đạt **698 passed, 0 skipped**. Luồng tạo từng
lượt, STT và lưu artifact thật đã chạy trên bài trên: 15 request TTS đều trả
200, WAV và 15 mốc được lưu cùng bài; nguồn đề/đáp án giữ nguyên. Có 3 kiểm
tra đạt, 6 chưa đạt và 1 chưa xác minh được, nên bản lưu bị chặn và GET audio/
timeline trả 409. Đây là quyết định cần rà soát, không phải kết luận mọi khác
biệt đều do TTS đọc sai. Chi tiết nằm trong
[tài liệu STT](listening-audio-verification.md).

## Tài liệu Microsoft

- [Text to speech REST API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)
- [Nhiều giọng trong SSML](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice)
- [Quotas và giới hạn Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits)
