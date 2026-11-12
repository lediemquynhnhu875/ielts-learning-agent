# 10 sample thu âm để kiểm tra STT cho Speaking Agent

## Phạm vi kiểm chứng — cập nhật 15/10/2026

Đây là bộ mẫu đọc sẵn (`response_mode=read_aloud`) để kiểm tra độ trung thực STT, khả năng giữ lỗi/filler/từ lặp và timestamps. Kịch bản chỉ trở thành transcript đối chiếu sau khi người nghe xác nhận lời thực sự có trong audio. Bộ này chưa đánh giá phiên thi nói tự do theo UC04, Part 3 đào sâu, hỏi trùng nghĩa, RAG/evidence hoặc độ lệch band so với giáo viên; không dùng các lỗi cố ý trong kịch bản làm điểm chuẩn Speaking.

Benchmark UC04 cần phiên nói tự do (`response_mode=spontaneous`), dữ liệu voice/text phù hợp, điểm giáo viên và evaluator câu hỏi/state riêng. Kế hoạch và 5 eval case tối thiểu tại [meeting-proposal.md](meeting-proposal.md#kế-hoạch-đánh-giá-uc04--chưa-chạy).

## Hướng dẫn gửi người thu âm

- Thu thành 10 file riêng: `sample-01.wav` đến `sample-10.wav`. Có thể dùng định dạng khác nếu thiết bị không xuất WAV; không cần đổi đuôi file bằng tay.
- Chỉ đọc phần **Nội dung đọc**, không đọc tiêu đề hoặc ghi chú.
- Đọc bằng giọng tiếng Anh tự nhiên của bạn, không cần bắt chước giọng bản xứ. Giữ nguyên câu sai, từ lặp và các tiếng `um`, `uh`, `hmm`.
- Không sửa câu dù thấy sai. Ví dụ `he go` phải đọc là `he go`, không đọc thành `he goes`.
- Các ký hiệu `[pause 1s]`, `[pause 2s]`, `[pause 3s]` nghĩa là im lặng khoảng thời gian đó, không đọc ký hiệu. Không cần chính xác đến mili giây.
- Dấu `...` chỉ chỗ do dự hoặc đổi ý, không phải chỉ dẫn nghỉ một khoảng cố định.
- Với sample 10, đọc theo hướng dẫn riêng. Các sample còn lại không cần cố tình phát âm sai.
- Thu trong cùng một không gian, cùng thiết bị và khoảng cách với mic. Giữ một chút khoảng lặng ở đầu và cuối; không cắt khoảng lặng bên trong đoạn.

**Lưu ý:** Lỗi chính tả thuộc văn bản, không nghe được trực tiếp từ audio. Bộ này kiểm tra lỗi ngữ pháp, dùng từ, cách phát âm, từ dễ nhận nhầm và các dấu hiệu ngập ngừng. Những cách viết như `enviroment` không nên dùng làm lỗi chính tả để đánh giá STT.

## Sample 01 — Đoạn đúng làm mốc

**Nội dung đọc**

I am a university student, and I study information technology. I usually attend classes in the morning and work on group projects in the afternoon. In my free time, I enjoy listening to music and walking around my neighborhood. These activities help me relax after a busy day.

**Ghi chú cho người kiểm tra:** Đoạn không có lỗi cố ý. Dùng để xem STT có nhận đúng lời nói thông thường trước khi đánh giá các đoạn khó hơn.

## Sample 02 — Thiếu đuôi động từ và sai cấu trúc phủ định

**Nội dung đọc**

My brother live near my university. He go to work by bus every morning, and he usually finish at six. He don't like cooking, so we often eat together. Sometimes he ask me about my classes, but he doesn't understands the subjects I study.

**Ghi chú cho người kiểm tra:** Kiểm tra STT có tự sửa `live` thành `lives`, `go` thành `goes`, `finish` thành `finishes`, `don't` thành `doesn't`, `ask` thành `asks`, hoặc `doesn't understands` thành `doesn't understand` hay không.

## Sample 03 — Sai thì quá khứ

**Nội dung đọc**

Last weekend, I go to a small restaurant with my friends. We order noodles and talk about our exams. After dinner, we walk to a bookstore, and I buy a novel. I didn't went home until ten. Yesterday, I readed the first chapter, and it was quite interesting.

**Ghi chú cho người kiểm tra:** Giữ nguyên `go`, `order`, `talk`, `walk`, `buy`, `didn't went` và `readed`. Với `readed`, đọc thành hai âm tiết, gần như "reed-id"; đây là dạng sai cố ý.

## Sample 04 — Sai danh từ số nhiều và lượng từ

**Nội dung đọc**

There are many student in my class. We have a lot of homework, but our teacher also gives us useful advices. I need more informations about the final project. Last week, I bought two new notebook and a few equipment for recording audio. These thing were quite expensive.

**Ghi chú cho người kiểm tra:** Các lỗi cần giữ là `many student`, `advices`, `informations`, `two new notebook`, `a few equipment` và `These thing`. Đọc rõ đuôi `s` trong `advices` và `informations`, dù các từ này bị dùng sai.

## Sample 05 — Sai mạo từ và giới từ

**Nội dung đọc**

I live in small apartment near the campus. It takes about ten minutes to arrive to my classroom. I am interested on learning English because it is useful for my future job. At the evening, I often discuss about my homework with a friend who lives in the same building.

**Ghi chú cho người kiểm tra:** Kiểm tra việc tự sửa `in small apartment`, `arrive to`, `interested on`, `At the evening` và `discuss about`.

## Sample 06 — Filler và khoảng dừng

**Nội dung đọc**

Um, I think my favorite place is, uh, the library. [pause 1s] I go there because, um, it is quiet, and I can focus better. [pause 2s] Hmm, sometimes I just sit near the window and read. Uh, I usually stay there for about an hour before going home.

**Ghi chú cho người kiểm tra:** Có 5 filler được viết rõ: `Um`, `uh`, `um`, `Hmm`, `Uh`. Có 2 khoảng dừng được chỉ định. Khi đối chiếu, dùng audio thực tế để xác định thời lượng; người thu có thể dừng lâu hoặc ngắn hơn hướng dẫn.

## Sample 07 — Lặp từ và tự sửa câu

**Nội dung đọc**

I, I usually study at home, at home after dinner. My favorite subject is history... sorry, I mean computer science. Last month, I went there on Monday... no, on Tuesday. I bought a book, a book about programming, and I, I finished it in two weeks.

**Ghi chú cho người kiểm tra:** Cần giữ các chỗ lặp `I, I`, `at home, at home`, `a book, a book`, và hai lần đổi ý từ `history` sang `computer science`, từ `Monday` sang `Tuesday`. STT có thể gộp hoặc loại bỏ chúng.

## Sample 08 — Dùng từ sai và kết hợp từ không tự nhiên

**Nội dung đọc**

Before an exam, I usually make my homework and learn new vocabularies. When I get a good result, I feel very funny and proud. My teacher gives me many knowledge about English. I want to improve my speaking because it can bring me a better work in the future.

**Ghi chú cho người kiểm tra:** Giữ nguyên `make my homework`, `vocabularies`, `feel very funny`, `many knowledge` và `a better work`. Các lỗi này giúp kiểm tra độ trung thực của transcript và sau này có thể dùng thử module chấm Lexical Resource.

## Sample 09 — Kết hợp lỗi ngữ pháp, filler và ngập ngừng

**Nội dung đọc**

Uh, when I was a child, I don't like speaking English. [pause 2s] My parents was very busy, so I study by myself. I, I watched videos, but I didn't understood much. [pause 3s] Now I am more confidence, and, um, I can explain my opinion more clear than before.

**Ghi chú cho người kiểm tra:** Giữ `don't`, `parents was`, `study`, `didn't understood`, `more confidence` và `more clear`. Đồng thời kiểm tra 2 filler, chỗ lặp `I, I` và 2 khoảng dừng được chỉ định.

## Sample 10 — Từ dễ đọc nhầm và số liệu

**Nội dung đọc**

I am comfortable speaking English with my classmates, although I still make mistakes. I want to develop better study habits and learn how technology affects the environment. Last Thursday, I bought fifteen notebooks for fifty thousand dong. This Thursday, I will buy thirteen pens for thirty thousand dong.

**Hướng dẫn riêng cho người thu:** Cố ý đọc `comfortable` thành "com-for-table" với 4 âm tiết; nhấn âm đầu của `develop` thay vì âm thứ hai; đọc `environment` thành "en-vai-ruh-ment", bỏ âm /n/ ngay trước âm /m/. Những từ còn lại đọc tự nhiên. Đọc phân biệt `fifteen` với `fifty`, `thirteen` với `thirty` theo khả năng của bạn.

**Ghi chú cho người kiểm tra:** Đây là thử nghiệm phát âm biến đổi có chủ đích, không phải mẫu chuẩn để chấm Pronunciation. STT vẫn viết đúng từ dù phát âm sai là điều có thể xảy ra. Muốn đánh giá phát âm phải nghe hoặc phân tích audio; transcript không thể chứng minh người nói đã phát âm đúng. Kiểm tra riêng độ chính xác của bốn số 15, 50, 13 và 30; các số được viết bằng chữ hoặc chữ số đều chấp nhận nếu giữ đúng giá trị.

## Cách sử dụng sau khi thu

1. Nghe lại từng file và ghi transcript đối chiếu theo lời người thu thực sự nói. Nội dung ở trên chỉ là kịch bản; nếu người thu đọc khác, transcript đối chiếu phải theo audio.
2. Không đưa tiêu đề, ghi chú hoặc ký hiệu `[pause ...]` vào transcript đối chiếu. Giữ filler, từ lặp, từ sai và những phần tự sửa đã thực sự được nói.
3. Chạy cùng audio trên Groq và faster-whisper local, mỗi công cụ thử có và không có `--keep-fillers`.
4. Ghi lại thời gian xử lý, từ bị nhận sai hoặc bỏ sót, lỗi ngữ pháp bị tự sửa, filler/từ lặp bị mất và chất lượng timestamps tại các khoảng dừng.
5. Khi so sánh độ chính xác, có thể bỏ qua khác biệt viết hoa và dấu câu. Kiểm tra riêng các lỗi cố ý vì một transcript trông đúng ngữ pháp hơn có thể phản ánh sai lời người nói.

| File | Công cụ | Keep fillers | Thời gian xử lý (s) | Từ sai/bỏ/thêm | Lỗi ngữ pháp bị tự sửa | Filler/từ lặp bị mất | Nhận xét timestamps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sample-01.wav | Groq | Không | | | | | |
| sample-01.wav | Groq | Có | | | | | |
| sample-01.wav | Local | Không | | | | | |
| sample-01.wav | Local | Có | | | | | |

Nhân các dòng mẫu cho 9 file còn lại. Mười sample này là bộ thử nhỏ để chọn công cụ và phát hiện vấn đề, chưa đủ đại diện cho độ chính xác trên mọi người học hoặc mọi chất lượng ghi âm.
