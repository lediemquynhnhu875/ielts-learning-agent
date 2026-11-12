# Kiểm chứng và phát hành audio Listening

Audio của bài Listening đã lưu chỉ được cấp cho người học sau khi kiểm tra
đáp án và thời gian. Backend tạo từng lượt nói bằng Azure TTS, ghép WAV, chạy
Azure STT toàn bộ file, rồi đối chiếu bằng chứng của từng câu với các từ nhận
dạng trong cửa sổ thời gian kỳ vọng. Script và đáp án không được gửi làm gợi ý
cho STT.

Các API script trực tiếp và CLI vẫn dùng để chẩn đoán lời thoại. Báo cáo WER
toàn văn là thông tin rà soát, không phải điều kiện đủ để phát hành bài.

## Cấu hình và migration

Từ thư mục gốc dự án:

```powershell
python -m pip install -e '.[listening-stt]'
```

Dùng lại `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` và `LISTENING_VOICES` của
[luồng TTS](listening-azure-speech.md). STT nạp SDK khi cần, dùng `en-GB`, chế độ
detailed và word timestamps. SDK chạy trong process riêng với giới hạn chờ
`min(720, thời_lượng_audio + 90)` giây; quá hạn thì dừng worker và dọn WAV tạm.
Kết thúc file được đọc từ `cancellation_details`; lỗi/hủy phiên không được xem
là transcript hoàn chỉnh.

Migration `003_listening_audio.sql` bổ sung bảng `listening_audio`. Startup
chạy migration còn thiếu khi `DATABASE_AUTO_MIGRATE=true`; nếu tắt, chạy CLI
migration theo [hướng dẫn CSDL](database-migrations.md).

Các POST tạo/kiểm chứng audio là API biên soạn riêng: phải cấu hình `API_TOKEN`
và gửi bearer token hiện có. Khi token chưa được cấu hình, POST trả `503`.
Token này là secret của server; không cấp cho người học hoặc nhúng vào browser.
Frontend proxy hiện không mở các route biên soạn này. GET audio đã xác minh
vẫn theo xác thực chung của backend; khi `API_TOKEN` trống, GET không yêu cầu
bearer nhưng vẫn kiểm tra điều kiện phát hành.

## Luồng bài đã lưu

1. Đọc bài khả dụng và đáp án/bằng chứng riêng trong một snapshot nhất quán.
2. Gọi TTS riêng cho từng lượt, kiểm tra WAV và ghép PCM theo thứ tự. Đếm frame
   để đo `start/end` độc lập với STT; không ước lượng thời gian từ độ dài text.
3. Chạy STT một lần cho toàn WAV. Text hiển thị và các từ lexical có timestamp
   được giữ riêng; thiếu timing của một phần thì không coi timeline là đầy đủ.
4. Neo bằng chứng vào đúng vị trí duy nhất trong script, rồi so toàn bộ ngữ
   cảnh của lượt nói chứa bằng chứng và thời gian của từng từ đã khớp.
5. Lưu WAV, manifest và báo cáo riêng với trạng thái `verified` hoặc `blocked`.
   Chỉ bản hiện hành đạt tất cả kiểm tra mới được tải qua GET.

Cửa sổ kỳ vọng là lượt nói được đo bằng frame TTS, không phải timestamp đáp án
do STT tự tạo. Các từ khớp phải nằm trong cửa sổ của chính lượt đó, với dung sai
150 ms ở biên. So cả ngữ cảnh giúp chặn các trường hợp chỉ có từ khóa đúng nhưng
nội dung sai như `not fifteen`, `fifteen point five` hoặc đánh vần tên sai.

Đối chiếu đáp án có quy tắc số hạn chế: `15`/`fifteen`, `4th`/`fourth` có thể
khớp; `15`/`fifty` không khớp, số có zero đầu được giữ nguyên. Không dò gần đúng
tên riêng. Bằng chứng thiếu/lặp mơ hồ, đáp án không neo được, `NOT GIVEN`, loại
câu không hỗ trợ hoặc thiếu timeline đều thành `unverifiable` và chặn cấp audio.
Tất cả câu của bài phải có trạng thái `passed`.

Cơ chế này chủ động chặn khi chưa chắc chắn. STT vẫn có thể nhận sai và làm bài
bị chặn nhầm; cần nghe/rà soát trước khi biên soạn lại. Không tự sửa đáp án,
script hay audio, và không tự retry các lần gọi tính phí.

## API biên soạn và API cấp audio

| Endpoint | Kết quả |
|---|---|
| `POST /api/exercises/{item_id}/audio` | Tạo, kiểm chứng và lưu. `200 audio/wav` chỉ khi đạt; bản bị chặn trả `409 audio_verification_failed` |
| `POST /api/exercises/{item_id}/audio/verify` | Báo cáo riêng cho người biên soạn, gồm `status`, `verification`, `manifest` và hash. Chỉ `verified` mới kèm `audio_base64`/`audio_media_type` |
| `GET /api/exercises/{item_id}/audio` | Tải WAV đã lưu và còn hợp lệ; không tạo TTS/STT mới |
| `GET /api/exercises/{item_id}/audio/timings` | Timeline công khai của cùng WAV đã xác minh; không chứa đáp án/báo cáo riêng |

Hai POST nhận body `{"voices":{"speaker_1":"en-GB-RyanNeural"}}` hoặc không
body. POST `/audio` giữ định dạng WAV thành công trước đây nhưng nay có cổng
kiểm chứng trước khi trả file. POST `/audio/verify` có thể trả JSON với
`status="blocked"`; trường hợp này không có audio base64 hoặc URL tải audio.
Lỗi TTS trước khi tạo được artifact vẫn trả lỗi dịch vụ; nếu STT/kiểm tra thất
bại sau khi có WAV, artifact được lưu ở trạng thái chặn để rà soát.

Ví dụ tạo và xem quyết định trước khi tải:

```powershell
$base = 'http://127.0.0.1:8000'
$headers = @{ Authorization = "Bearer $env:API_TOKEN" }
$itemId = '<UUID bài Listening>'
$report = Invoke-RestMethod -Method Post `
    -Uri "$base/api/exercises/$itemId/audio/verify" -Headers $headers
$report.status
$report.verification | ConvertTo-Json -Depth 12
if ($report.status -eq 'verified') {
    Invoke-WebRequest -Uri "$base/api/exercises/$itemId/audio" `
        -Headers $headers -OutFile 'verified-listening.wav'
    $timings = Invoke-RestMethod -Uri "$base/api/exercises/$itemId/audio/timings" -Headers $headers
    $timings.turns | Format-Table
}
```

Timeline trả `item_id`, `audio_sha256`, `sample_rate` và `turns`. Mỗi lượt chỉ có
8 trường: `position`, `speaker_id`, `start_frame`, `end_frame`, `start_seconds`,
`end_seconds`, `source_start_char`, `source_end_char`. Player có thể dùng
`start_seconds`/`end_seconds` để chuyển lượt; UI player chưa được thêm trong
thay đổi này. Các chỉ số nguồn là ký tự Python trong script, cuối không bao gồm.

## Lưu trữ và ràng buộc artifact

`listening_audio` giữ bản hiện hành theo `item_id`: WAV `bytea`, manifest đo
thời gian, báo cáo kiểm chứng riêng, trạng thái và các SHA-256. Nguồn được gắn
với cả bài công khai lẫn đáp án/bằng chứng riêng; cấu hình gắn với phiên bản
pipeline, locale, danh sách giọng và override. Hash audio và hash manifest phải
khớp. GET kiểm tra lại nguồn, cấu hình pipeline hiện tại, đủ kết quả từng câu,
frame/timeline và trạng thái trước khi trả dữ liệu.

Nếu nguồn/đáp án/giọng/cấu hình đổi, artifact bị sửa, chưa có bản lưu hoặc bản
hiện hành bị chặn, GET trả `409 audio_not_verified`. WAV và báo cáo chặn vẫn ở
DB để xử lý riêng, không được cấp cho người học. Báo cáo biên soạn có thể chứa
đoạn bằng chứng; không dùng nó làm response cho learner.

## Preview script trực tiếp và CLI

`POST /api/listening/audio` tạo WAV preview bằng một request SSML nhiều giọng.
`POST /api/listening/audio/verify` tạo preview rồi STT một lần, trả JSON
`audio_base64`, `audio_media_type`, `verification`. Cả hai cần quyền biên soạn.
Preview không có đáp án/bằng chứng DB nên không đưa ra quyết định phát hành bài.

```powershell
$body = @{ script = 'Man: Hello. Woman: Good morning.' } | ConvertTo-Json
$preview = Invoke-RestMethod -Method Post -Uri "$base/api/listening/audio/verify" `
    -Headers $headers -ContentType 'application/json; charset=utf-8' `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
[System.IO.File]::WriteAllBytes(
    (Join-Path (Get-Location).Path 'preview.wav'),
    [System.Convert]::FromBase64String($preview.audio_base64))
$preview.verification.comparison | ConvertTo-Json -Depth 8
```

Để đối chiếu WAV cũ mà không tạo TTS lại:

```powershell
python -m ielts_agent.listening.cli `
    --audio data/listening/existing.wav `
    --script data/listening/reference.txt `
    --output data/listening/verification.json
```

Script là UTF-8, có thể chứa nhãn người nói. CLI loại nhãn khi tạo tham chiếu,
chỉ chạy STT và báo cáo toàn văn; không ghi DB hay phát hành artifact. Bỏ
`--output` để in JSON; output không được trùng audio hoặc script đầu vào.

## Báo cáo toàn văn, giới hạn và lỗi

Báo cáo chẩn đoán gồm `expected_text`, `transcript` và `comparison`. So sánh
chuẩn hóa NFKC, hoa/thường, dấu nháy cong và dấu câu; không sửa số/tên theo ngữ
nghĩa ở bước WER này. Alignment Levenshtein trả `substitutions`, `deletions`,
`insertions`, `word_error_rate=(S+D+I)/số_từ_tham_chiếu` và `normalized_match`.
WER có thể lớn hơn 1. `differences` dùng khoảng token đã chuẩn hóa từ 0, cuối
không bao gồm, không phải timestamp. Kết quả này tách biệt với kiểm tra đáp án
theo thời gian dùng từ lexical và quy tắc số nêu trên.

- Script tối đa 12.000 ký tự, 50 lượt; mỗi phía alignment tối đa 2.500 từ và
  40.000 ký tự. Transcript rỗng hoặc không có từ là lỗi nhận dạng.
- WAV đầy đủ, PCM mono 24 kHz/16 bit, tối đa 29.000.000 byte, ngắn hơn 599 giây.
  Timed TTS dùng ngân sách 300 giây cho chuỗi request; preview dùng 120 giây.
  HTTP timeout vẫn có giới hạn I/O và kiểm tra elapsed giữa chunk, không phải
  deadline cứng cho toàn bộ phiên biên soạn.
- API biên soạn có thể tính phí TTS cho từng lượt và STT toàn file. JSON base64
  lớn hơn nhị phân khoảng 4/3 lần. Không tự retry hoặc tự tạo lại bản bị chặn.
- Response audio, báo cáo và timing có `no-store`; không phản chiếu key hoặc
  lỗi nội bộ SDK. Lỗi chính: `422` đầu vào, `503` thiếu cấu hình/SDK hoặc tắt
  biên soạn, `502` lỗi nhà cung cấp/transcript, `504` timeout, `409` chưa đạt
  điều kiện cấp audio. Lỗi UUID, xác thực và DB hiện có vẫn áp dụng.

## Kiểm chứng

Kiểm thử đầy đủ có PostgreSQL đạt **698 passed, 0 skipped** trong 29,62 giây,
dùng schema tạm riêng cho từng test. Rà soát mã, biên dịch và kiểm tra diff đạt.

Đã thử toàn luồng trên bài `Welcome to Lotus Residence, Can Tho`
(`0452ee07-8baf-4430-a63f-521b64e22b28`): 15 request Azure TTS đều trả 200,
STT detailed chạy toàn file, rồi lưu WAV 9.990.644 byte cùng 15 mốc lượt nói
và báo cáo vào PostgreSQL. Có 3 kiểm tra đạt, 6 chưa đạt và 1 không xác minh
được, nên bản lưu là `blocked`. GET audio và GET timeline trả 409; JSON báo
cáo bị chặn không chứa audio base64. Nguồn đề/đáp án không thay đổi. Thời gian
đo là 266,04 giây. Các kiểm tra chưa đạt vẫn cần rà soát vì STT có thể nhận sai.
Báo cáo quản trị cục bộ:
`data/listening/azure-publication-0452ee07-8baf-4430-a63f-521b64e22b28.json`.
Lượt thử dùng token tạm trong process; không thay đổi `.env`. Các POST biên
soạn trên server vẫn cần `API_TOKEN` do người vận hành cấu hình.

Ở bước chẩn đoán trước đó, CLI nhận dạng WAV cũ của bài
`Welcome to Lotus Residence, Can Tho`: 586 token tham chiếu, 588 token STT,
18 thay thế/1 thiếu/3 thêm, WER **0,037543**. Các cặp `nine`/`9`, `fourth`/`4th`,
`Can Tho`/`Cantho` cho thấy khác cách viết chưa chứng minh TTS đọc sai. Kết quả
3,75% này không phải quyết định phát hành của pipeline đáp án/timestamp mới.
Báo cáo cục bộ ở
`data/listening/azure-db-0452ee07-8baf-4430-a63f-521b64e22b28-verification.json`;
`data/` được Git bỏ qua.

Tham khảo [continuous recognition của Microsoft](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech?pivots=programming-language-python).
