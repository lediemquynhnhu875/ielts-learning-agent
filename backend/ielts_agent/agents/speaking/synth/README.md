# Sinh dữ liệu giả lập — phần Speaking

Bộ này hiện thực phần Speaking của `generate-format.docx` v1.0: prompt **P6a,
P6b, P7, P10**, tập benchmark 18 phiên, kho placement 54 bộ và 10 biến thể
edge-case. Thêm **P6q1/P6q2/P6q3** sinh chính ngân hàng đề Speaking — **10 bộ
đề hoàn chỉnh** theo mục tiêu "Speaking × 10 bộ" của mục 11.2 — nên mọi câu hỏi
trong bộ dữ liệu đều do LLM viết và truy được nguồn.

> **Ngân hàng đề.** Trước đây chủ đề Part 1 và cue card Part 2 lấy từ
> `agents/speaking/questions.py` — 15 câu và 6 cue card viết tay trong prototype, không
> có nguồn gốc nào ghi lại được. Vì vậy `CONTENT_ITEM.source =
> llm_generated_verified` chỉ đúng với transcript, còn R9 provenance và mục 1.5
> về bản quyền thì không kiểm được bằng file. Từ 30/10/2026 bank do LLM sinh ở
> giai đoạn 0 và lưu ở `out/question_bank.json` kèm model, `prompt_version`,
> `job_id` và seed của từng lệnh gọi.

### Ngân hàng đề có gì

| Phần | Nguồn | Số lượng |
| --- | --- | --- |
| `topics` | P6q1 | 6 chủ đề Part 1 × 6 câu = **36 câu** |
| `cue_cards` | P6q2 | **10** thẻ đề Part 2 |
| `part3_bank` | P6q3 | **50** câu Part 3 **dự phòng** (5 × 10 thẻ) |
| `exam_sets` | **code ghép** | **10 bộ đề hoàn chỉnh** = 2 chủ đề Part 1 + 1 cue card + 1 bộ Part 3 |
| `selection_rule` | code | Quy tắc chọn đề, viết thành chữ ngay trong file |

> **Câu Part 3 trong bank là KHO DỰ PHÒNG, không phải câu hỏi của UC-04.** UC-04
> đòi mỗi câu Part 3 sau câu đầu phải bám vào chính câu trả lời thí sinh vừa
> nói, nên phải sinh lúc thi bằng `P6a3`. Kho này thuộc UC-05 ("ngân hàng đề dự
> phòng"), chỉ dùng khi agent không bám được ý nào. **Không dùng nó để đo tiêu
> chí nghiệm thu UC-04** — toàn bộ 18 phiên benchmark vẫn dùng `P6a3`.

### Quy tắc chọn đề

Ghép bằng code trong `qbank.compose`, tất định từ seed, và chép nguyên văn vào
`question_bank.json → selection_rule` để đọc được mà không cần mở code:

* **Part 1** — mỗi bộ lấy 2 chủ đề. Loại trước các chủ đề trùng đề tài với cue
  card của bộ, rồi ưu tiên chủ đề đang dùng ít nhất, và không lặp lại một cặp
  chủ đề đã dùng ở bộ khác. Kết quả: 6 chủ đề dùng 3–4 lần mỗi chủ đề, 0 cặp
  trùng trên 10 bộ.
* **Part 2** — mỗi cue card đúng một bộ đề.
* **Part 3** — kho dự phòng của chính cue card đó.
* **Trong một phiên** — chọn 4 trong 6 câu của mỗi chủ đề theo seed của phiên.
  Cấu trúc đề cố định ở mức bank; phần đổi giữa các phiên là tập con câu hỏi,
  nên hai phiên cùng bộ đề vẫn không trùng văn bản (W4).

`EXAM`/`EXAM_ITEM` thuộc ERD 1 của cả hệ thống, còn `agents/speaking/database.py` chỉ
mô hình phần Speaking nên không có hai bảng đó. Bộ đề vì vậy nằm ở
`question_bank.json` và được chép vào `extensions.question_bank` của dataset;
mỗi `CONTENT_ITEM.body.question_bank.exam_set` trỏ về bộ đề đã dùng.

> **Quan trọng.** `intended_band` trong mọi file ở đây là **tham số thiết kế**,
> không phải điểm chuẩn. Theo quy định 1.5.3 của đề tài 06, điểm chuẩn chỉ được
> lấy từ giáo viên hoặc người có chứng chỉ IELTS chấm, có ghi tên người chấm và
> ngày chấm — nằm ở `gold_label`. Judge LLM (P10) **chỉ lọc mẫu**. Gọi
> `intended_band` là điểm chuẩn trong báo cáo sẽ làm UC-08 bị 0 điểm.

## Chạy

```sh
set -a && . ./.env && set +a          # cần GROQ_API_KEY

python backend/ielts_agent/agents/speaking/synth/generate.py bank        # giai đoạn 0: bank + 10 bộ đề
python backend/ielts_agent/agents/speaking/synth/generate.py pilot       # 4 phiên: band 4.0, 5.5, 6.5, 8.0
python backend/ielts_agent/agents/speaking/synth/report.py               # xem có đạt ngưỡng mục 6.3 không
python backend/ielts_agent/agents/speaking/synth/generate.py benchmark   # 18 phiên đủ Part 1-3
python backend/ielts_agent/agents/speaking/synth/generate.py placement   # 54 bộ Part 1 ngắn cho UC-01
python backend/ielts_agent/agents/speaking/synth/generate.py judge       # P10 lọc mẫu
python backend/ielts_agent/agents/speaking/synth/assemble.py             # lắp ra record database
python backend/ielts_agent/agents/speaking/synth/report.py               # metric W/P-series
python backend/ielts_agent/agents/speaking/synth/gold_form.py            # phiếu chấm mù cho giáo viên
python backend/ielts_agent/agents/speaking/synth/gold_form.py --set edge # phiếu xác nhận nhãn bất thường
python backend/ielts_agent/agents/speaking/synth/generate.py status      # hàng đợi và quota còn lại
```

Chạy lại lệnh nào cũng an toàn. Mỗi lệnh gọi LLM là một dòng `gen_job` với
`job_id = hash(prompt_version, input, seed)`, nên job đã `ok` được bỏ qua. Hết
hạn mức ngày thì script dừng với thông báo rõ và hôm sau chạy tiếp từ chỗ dừng.

Lệnh `bank` phải chạy **trước** mọi lệnh khác: cả kế hoạch phiên lẫn kho
placement đều lấy chủ đề và cue card từ đó. Thiếu `out/question_bank.json` thì
`plan.py` báo lỗi chứ không âm thầm quay về bank viết tay. Sửa bank là đổi đầu
vào của mọi prompt, nên `job_id` đổi theo và toàn bộ dữ liệu phải sinh lại.

## File

| File | Nội dung |
| --- | --- |
| `spec.yaml` | Lưới sinh: band profile, taxonomy lỗi, persona, quy mô, hạn mức, phân phối `stt_confidence`, ngưỡng lọc judge |
| `qbank.py` | Giai đoạn 0: sinh ngân hàng đề, đặt ID bằng code, ghi provenance |
| `prompts.py` | P0, P6q1/P6q2/P6q3, P6a1/P6a2/P6a3, P6a_placement, P6b, P7_switch, P10 kèm `prompt_version`, temperature, trần token |
| `jobs.py` | Hàng đợi `gen_job`: idempotent, resume, ba hạn mức token, repair loop, feedback loop, luân phiên model |
| `plan.py` | Giai đoạn 1: 200 learner, persona, lịch phiên, ID và timestamp suy ra từ seed |
| `validate.py` | Lớp rules: shape, verbatim câu hỏi, số từ theo band, rò rỉ meta, grounding Part 3 |
| `assemble.py` | Giai đoạn 4: lắp văn bản vào khung, ra record `ielts-speaking-db-1.0` |
| `report.py` | Metric W2, W4, W5, W6, W7, P-series, grounding UC04, kết quả lọc judge |
| `gold_form.py` | Phiếu chấm mù cho giáo viên và phiếu xác nhận nhãn cho người đã từng thi |
| `out/gen_jobs.sqlite3` | Mọi lệnh gọi LLM: prompt_version, model, raw output, token, lỗi |
| `out/question_bank.json` | Ngân hàng đề: 36 câu Part 1, 10 cue card, 50 câu Part 3 dự phòng, 10 bộ đề, `selection_rule`, `calls` ghi model và `job_id` |
| `out/sessions.json` | Transcript đã qua validate, theo phiên |
| `out/speaking_synth_dataset.json` | Record database + `synth_manifest` + `placement_pool` |
| `out/report.json` | Báo cáo metric |
| `out/gold/` | `packet-*.md` gửi người chấm, `gold_label-*.csv` để điền, `blind_map-*.json` **không gửi** |

## Phân công theo kịch bản

Thuộc phần này: **P5 không** (Writing), **P6a, P6b, P7, P10 có**. P1–P4 (sinh
đề) và P9 (solver) thuộc nhóm làm ngân hàng đề.

**P6q1/P6q2 là phần thêm, cần gióng với người làm ngân hàng đề.** Mục 11 giao
việc sinh đề cho người đó, nhưng P1–P4 chỉ có Reading, Listening và Writing —
không có prompt nào cho câu hỏi Speaking, mà bank viết tay thì không khai được
nguồn. Hai prompt này lấp chỗ trống đó trong phạm vi Speaking. Khi người làm
ngân hàng đề giao bộ đề chính thức, thay `out/question_bank.json` bằng bộ đó
(giữ nguyên schema) rồi sinh lại.

## Bốn chỗ lệch so với đặc tả, và lý do

**1. P6a tách thành ba lệnh gọi.** Mục 7 viết P6a là một lệnh gọi cho cả Part
1–3. Groq free tier có một hạn mức thứ ba không ghi trong `.env` và không ghi
trong kịch bản: **OTPM, 1.000 token đầu ra mỗi phút mỗi model**. Một transcript
đủ ba phần cần 1.300–3.000 token đầu ra, nên gọi một lần luôn bị 429
`on output tokens per minute`. P6a vì vậy tách thành `P6a1` (Part 1, một chủ
đề), `P6a2` (Part 2) và `P6a3` (Part 3) — bốn lệnh gọi một phiên.

Việc tách có lợi ngoài dự kiến: `P6a3` được nạp **câu trả lời thật** của Part 1
và Part 2, nên tiêu chí nghiệm thu UC04 — mỗi câu Part 3 sau câu đầu phải tham
chiếu ít nhất một ý từ câu trả lời trước đó — kiểm tra được bằng code ở cả hai
đầu: validator chặn lúc sinh, và `report.py` đo lại trên dữ liệu đã lắp.

**2. `CANDIDATE_POINT` do code trích, không gọi P6b.** Mục 1 ghi "LLM trích ý".
Nhưng agent thật (`agents/speaking/sessions.py`) trích ý bằng rule — ba câu đầu mỗi
lượt, bỏ qua lượt bị gắn cờ. Dùng đúng rule đó cho dữ liệu giả lập thì
`CANDIDATE_POINT` khớp hệt cái pipeline thật sinh ra, đúng tinh thần quyết định
số 2 của kịch bản ("dữ liệu của hệ thống đang được đo phải là kết quả chạy
thật"), và tiết kiệm 24 lệnh gọi. P6b vẫn còn trong thư viện prompt cho nhóm
khác dùng.

**3. Ngân hàng đề Speaking cũng do LLM sinh (P6q1, P6q2, P6q3).** Lý do ở khối trích
dẫn đầu file: bank viết tay không khai được nguồn. Hai ràng buộc đặt thêm bằng
code, không nhờ prompt:

* **Bank không phụ thuộc band.** Trong phòng thi mọi thí sinh nhận cùng bộ đề.
  Nếu đề đổi theo band thì band thiết kế và độ khó của đề lẫn vào nhau, và so
  sánh giữa các band mất nghĩa. Bank sinh một lần, dùng cho cả 9 band.
* **Chủ đề Part 1 không trùng đề tài với cue card Part 2** của cùng phiên. Hỏi
  Part 1 về quà tặng rồi Part 2 lại bắt tả một món quà là lỗi ra đề, và còn làm
  tiêu chí grounding của Part 3 dễ đạt một cách giả. `plan.py` lọc bằng giao từ
  nội dung; lọc theo từ nên chỉ bắt được trùng hiển ngôn.

ID, icon và thứ tự do code gán từ tên chủ đề, không lấy từ đầu ra model, nên đọc
lại file là dựng lại bank y nguyên (quyết định số 1).

**4. `reasoning_effort="low"` cho họ gpt-oss.** Model `openai/gpt-oss-*` tính
token reasoning vào `completion_tokens`. Để mặc định, trần 750 token bị
reasoning ăn hết và JSON trả về bị cắt giữa chừng → 400 `json_validate_failed`.
Đặt `reasoning_effort="low"` thì đầu ra tụt từ 750 xuống ~220 token và JSON đủ.

## Vai model

| Vai | Model | Ghi chú |
| --- | --- | --- |
| Generator | `qwen/qwen3.8-27b` | Khác họ với judge |
| Generator dự phòng | `openai/gpt-oss-120b` | Cùng model với grader B của hệ thống |
| Judge P10 | `openai/gpt-oss-20b` | Khác họ generator, khác cả grader A và B |
| Judge dự phòng | `openai/gpt-oss-120b` | |

Đây là ba model chat duy nhất có trên Groq free tier ở dự án này, và hai model
mạnh đang là grader A/B của hệ thống thật. Vì vậy:

* Judge **khác họ** generator chính (qwen) — tránh được self-preference, thiên
  lệch mạnh nhất mà mục 2.6 cảnh báo.
* Judge **khác cả grader A và grader B**, nên không có vòng tự xác nhận với
  pipeline chấm.
* Nhưng generator dự phòng `gpt-oss-120b` **cùng họ** với judge. Khi job nào
  rơi sang model dự phòng, phần đó có rủi ro self-preference còn lại. Cột
  `model` trong `gen_job` và `synth_manifest` ghi rõ model thật đã dùng cho
  từng bản ghi, nên báo cáo tách được hai nhóm này.

## Kết quả lần chạy 31/10/2026

Ba lần chạy. v1 dùng ngân hàng đề viết tay; v2 bank LLM 8 cue card; **v3 là bản
hiện tại**: bank LLM đủ 10 bộ đề, có câu Part 3 dự phòng và quy tắc chọn đề.
Hai bản cũ ở `out/archive-v1/` và `out/archive-v2/` (gitignore). v3 tổng cộng
209 lệnh gọi LLM, 0 job `failed` còn lại; nút thắt vẫn là OTPM.

| Sản phẩm | Số lượng |
| --- | --- |
| Chủ đề Part 1 trong bank | 6 × 6 câu = **36 câu** |
| Cue card Part 2 | **10** |
| Câu Part 3 dự phòng | **50** (5 × 10) |
| Bộ đề hoàn chỉnh | **10** |
| Phiên benchmark đủ Part 1–3 | 18 (9 band × 2) |
| Biến thể edge-case | 10 (too_short 4, injection 2, low_stt 4) |
| Bộ Part 1 ngắn cho placement | 54 (9 band × 6) |
| `SPEAKING_TURN` / `CANDIDATE_POINT` / `ASKED_QUESTION` | 617 / 707 / 392 |

### Metric

| Mã | Chỉ số | Kết quả | Ngưỡng | |
| --- | --- | --- | --- | --- |
| W2 | ρ số từ theo band | 0.962, KTC95 [0.83, 0.99] | ≥ 0.7 | đạt |
| W2 | ρ tỉ lệ từ dài | 0.807, KTC95 [0.58, 0.92] | ≥ 0.7 | chưa quyết định được |
| W2 | ρ MTLD | 0.776, KTC95 [0.50, 0.92] | ≥ 0.7 | chưa quyết định được |
| W2 | ρ độ dài câu | 0.659, KTC95 [0.27, 0.85] | ≥ 0.7 | chưa quyết định được |
| W2 | ρ mật độ lỗi (proxy) | 0.492, KTC95 [0.08, 0.78] | ≥ 0.7 | chưa quyết định được |
| W4 | trùng 4-gram cao nhất | **0.44%** | ≤ 3% | đạt |
| W5 | rò rỉ meta | 0 | 0 | đạt |
| W6 | số từ trong khoảng band | 54/54 | ≥ 80% | đạt |
| W7 | recall cờ edge-case | 1.0 cả ba nhóm, 0 false positive | ≥ 95% | đạt |
| R9 | provenance điền đủ | 28/28 item, 15/15 lệnh gọi bank | 100% | đạt |
| R9 | câu còn từ bank viết tay | 0 | 0 | đạt |
| P1 | orphan row | 0 | 0 | đạt |
| P2 | thứ tự thời gian | 0 lỗi | 100% | đạt |
| — | `refs_point_id` NULL | 41.4% | ~40% | đạt |
| — | UC04: câu Part 3 bám ý đã nói | 71/72 = 98.6% | ≥ 95% | đạt |

Số từ theo band: 304–346 (4.0), 440–460 (4.5), 526–537 (5.0), 690–729 (5.5),
809–842 (6.0), 833–928 (6.5), 1079–1104 (7.0), 1200–1363 (7.5),
**1036–1255 (8.0)**.

**Band 8.0 viết NGẮN hơn band 7.5.** Đây là chỗ hỏng rõ nhất của lần chạy này
và là lý do ρ số từ tụt từ 0.995 xuống 0.962. Hai phiên 8.0 đều dưới khoảng của
7.5, tức model free không kéo nổi đầu trên của thang — đúng cảnh báo mục 8.3.
W6 vẫn báo 54/54 vì khoảng band của 8.0 trong `spec.yaml` chồng lên 7.5; cần
siết khoảng đó hoặc dùng model trả phí cho nhóm band cao.

**Chỉ `words` là kết luận được.** Bốn đặc trưng còn lại có KTC95 chứa ngưỡng
0.7, nên ρ rơi về bên nào cũng không kết luận được ở n = 18. So ba lần chạy cho
thấy rõ: mật độ lỗi lần lượt 0.463 → 0.170 → 0.492, độ dài câu 0.713 → 0.589 →
0.659 — **dao động của chính phép đo, không phải dữ liệu tốt lên hay xấu đi**.
Muốn W2 có nghĩa thì phải tăng số phiên mỗi band.

**UC04 trượt 1 câu**, và đáng xem: *"What could happen if people stopped
visiting these relaxing places?"* — câu này **có** bám ý trước, nhưng bám bằng
đại từ chỉ định ("these relaxing places") chứ không lặp lại từ đặc trưng nào.
Phép đo của `report.py` dựa trên giao từ nội dung nên không bắt được hồi chiếu.
Đây là giới hạn của chỉ số, không phải lỗi dữ liệu.

### Bộ lọc judge P10

18 bài, giữ 16, loại 2 (`sp-bench-02` thiết kế 4.5 → judge 6; `sp-bench-15`
thiết kế 7.5 → judge 6). QWK intended–judge **0.679, KTC95 [0.47, 0.80]**,
MAE 0.694, Spearman 0.814, realism trung bình 4.0/5.

**Đừng đọc đây là "bank mới làm judge tệ đi".** v2 được QWK 0.823, v3 được
0.679. Bootstrap chênh lệch giữa hai lần chạy cho KTC95 là [−0.04, +0.37] —
**khoảng này chứa 0**, nên ở n = 18 hai con số không phân biệt được.

**Judge co cả hai đầu thang về giữa**, lần này rõ hơn: 4.0 → 5, 4.5 → 5 và 6,
5.0 → 6, còn 7.5 → 6.5 và 6, 8.0 → 7 cả hai bài. Đây là thiên lệch co về trung
bình của LLM-as-judge, đúng lý do mục 2.5 đòi gold phải từ người. Hai bài bị
loại **không được sinh lại**: sinh lại tới khi judge chấp nhận chính là hiệu
ứng chọn lọc mà mục 2.6 bảo phải báo cáo chứ không che. `report.json` ghi cả số
trước và sau lọc.

## Giới hạn phải khai báo trong báo cáo

1. **Chưa có `gold_label`.** Mọi kết luận về chất lượng AI chấm còn bỏ trống
   cho đến khi giáo viên chấm xong. `report.json` cố ý không tính QWK hay MAE
   so với gold.
2. **Pronunciation không benchmark được.** Chỉ có transcript, không có âm
   thanh. Attempt mang `mode = text` và PR phải là `not_assessed` (UC-03).
3. **W2 và QWK chưa quyết định được ở n = 18.** KTC95 của bốn trong năm đặc
   trưng W2, và của QWK judge, đều chứa ngưỡng. Chỉ `words` là chắc chắn đạt.
   Báo cáo phải ghi cả điểm ước lượng và khoảng tin cậy, không ghi riêng điểm.
4. **Band 8.0 viết ngắn hơn band 7.5** ở lần chạy này. Model free không kéo nổi
   đầu trên của thang (mục 8.3). Khoảng số từ của 8.0 trong `spec.yaml` lại
   chồng lên 7.5 nên W6 không bắt được; cần siết khoảng hoặc dùng model trả phí
   cho nhóm band cao.
5. **Mật độ lỗi là proxy bằng rule**, không phải ERRANT hay LanguageTool, nên
   ngưỡng W3 của kịch bản chưa kiểm được.
6. **Chỉ số UC04 không bắt được hồi chiếu.** Nó đo giao từ nội dung, nên câu
   bám ý bằng "these ... places" hay "that idea" bị tính là trượt.
7. **Thiếu danh sách tần suất từ**, nên dùng tỉ lệ từ từ 8 ký tự trở lên thay
   cho chỉ số "ngoài top 2.000" của mục 5.2.
8. **Nhóm `low_stt_confidence` là mô phỏng.** `stt_confidence` lấy mẫu từ phân
   phối trong `spec.yaml`, chưa chạy vòng Azure TTS → nhiễu → Whisper thật vì
   dự án chưa có khóa Azure. Cách tính `stt_confidence` cũng còn là đề xuất
   (giả định số 5, mục 10.3): `exp(avg_logprob)` của Whisper.
9. **Dữ liệu tổng hợp không thay thế phân phối lỗi thật của người học**, và
   không nên dùng bộ này để fine-tune (nguy cơ model collapse).
10. **Ngân hàng đề chưa có người duyệt.** 36 câu Part 1, 10 cue card và 50 câu
    Part 3 dự phòng do LLM
   viết, đã qua validator về khuôn dạng (dấu hỏi, số từ, không trùng nhau,
   `Describe`/`and explain`, đúng 3 gợi ý). Nhưng *đề có đúng độ khó Part 1 và
   Part 2 hay không* thì chỉ người đã thi IELTS mới kết luận được — việc này
   nằm cùng nhóm với phiếu `packet-edge-*`. Validator cũng không chứng minh được
   câu nào là nguyên bản: nó chỉ chặn trùng trong nội bộ bank.
11. **ERD 2 không nằm trong bộ này.** `ASSESSMENT` đến `FINAL_SCORE` phải do
   pipeline chấm thật sinh ra với `purpose = eval`. File dataset chỉ có ERD 1.

## Việc còn lại

* Giáo viên chấm `out/gold/packet-benchmark-round1.md`, rồi chấm lại 20% sau ít
  nhất 7 ngày (`gold_form.py --round 2`) để có intra-rater QWK.
* Người đã từng thi xác nhận nhãn ở `out/gold/packet-edge-round1.md`.
* Chạy pipeline chấm thật với `purpose = eval` trên 18 attempt benchmark để
  sinh ERD 2, rồi tính metric mục 5.4.
* Gióng 26 node trong `spec.yaml: taxonomy_error` với mã ghi chú lỗi của nhóm
  (mục 2.2 đề tài 06) trước khi nạp vào bảng `TAXONOMY_ERROR`.
* Chốt cách tính `stt_confidence` với người phụ trách STT.
* Người đã thi IELTS duyệt `out/question_bank.json`: 36 câu Part 1 và 8 cue
  card, xem có đúng dạng câu của Part 1/Part 2 và có câu nào lạc đề không.
* Gióng với người làm ngân hàng đề (P1–P4): hoặc họ nhận luôn phần đề Speaking,
  hoặc thống nhất giữ `question_bank.json` làm nguồn cho phần Speaking.
