"""Thư viện prompt Speaking: P0, P6a, P6b, P7, P10 (generate-format.docx mục 7).

Placeholder dạng {{ten_bien}} do code điền từ spec.yaml. Prompt viết bằng tiếng
Anh vì đầu ra là nội dung IELTS. Sửa prompt thì tăng VERSIONS để truy vết được
qua CONTENT_ITEM.prompt_version và synth_manifest.

Lệch so với đặc tả: P6a của mục 7 là một lệnh gọi cho cả Part 1-3. Groq free tier
chặn ở 1.000 token ĐẦU RA mỗi phút mỗi model (OTPM), còn một transcript đủ ba
phần cần 1.300-3.000 token, nên P6a được tách thành P6a1 (Part 1, một chủ đề),
P6a2 (Part 2) và P6a3 (Part 3). Việc tách còn cho phép nạp câu trả lời thật của
Part 1-2 vào Part 3, nên tiêu chí nghiệm thu UC04 - mỗi câu Part 3 sau câu đầu
phải tham chiếu một ý đã nói - kiểm tra được bằng code chứ không chỉ bằng lời.

Thêm so với đặc tả: P6q1, P6q2 và P6q3 sinh chính NGÂN HÀNG ĐỀ Speaking (chủ đề
Part 1, cue card Part 2 và bộ câu Part 3 dự phòng). Mục 7 không có prompt nào cho việc này vì mục 11 giao phần
sinh đề (P1-P4) cho người làm ngân hàng đề. Nhưng bank viết tay trong
speaking/questions.py không ghi được nguồn gốc, nên R9 provenance và mục 1.5 bản
quyền không kiểm được bằng file. Hai prompt này lấp chỗ đó trong phạm vi
Speaking; khi người làm ngân hàng đề giao bộ đề chính thức thì thay bằng bộ đó.
"""

VERSIONS = {
    "P6q1": "sp_qbank_part1_v1",
    "P6q2": "sp_qbank_part2_v1",
    "P6q3": "sp_qbank_part3_v1",
    "P6a1": "sp_part1_v1",
    "P6a2": "sp_part2_v1",
    "P6a3": "sp_part3_v1",
    "P6a_placement": "sp_placement_v1",
    "P6b": "sp_points_v1",
    "P7_switch": "sp_langswitch_v1",
    "P10": "sp_judge_v1",
}

TEMPERATURES = {
    "P6q1": 0.9,
    "P6q2": 0.9,
    "P6q3": 0.9,
    "P6a1": 0.9,
    "P6a2": 0.9,
    "P6a3": 0.9,
    "P6a_placement": 0.9,
    "P6b": 0.3,
    "P7_switch": 0.7,
    "P10": 0.0,
}

# Trần token đầu ra. Groq tính prompt_tokens + max_completion_tokens vào TPM và
# ước lượng riêng đầu ra cho OTPM, nên mọi cap phải nằm dưới 1.000.
MAX_TOKENS = {
    "P6q1": 700,
    "P6q2": 700,
    "P6q3": 600,
    "P6a1": 750,
    "P6a2": 800,
    "P6a3": 900,
    "P6a_placement": 900,
    "P6b": 500,
    "P7_switch": 900,
    "P10": 600,
}

P0 = """You are a data generator for an IELTS practice platform test dataset.
Write original, realistic IELTS-style material and follow the requested schema exactly.
Output a single JSON object and nothing else: no markdown fences, no commentary.
Never mention AI, prompts or band scores inside learner-written text.
Do not quote or closely imitate any published text. Use fictional names for people, companies and studies."""


P6Q1 = """TASK: Write original IELTS Speaking Part 1 topic cards for a practice
question bank. The bank is shared by every candidate, so write nothing that
depends on a candidate's level.
Write {{n_topics}} topics. Each topic has a short name and exactly {{per_topic}}
examiner questions.
RULES:
- Part 1 asks about the candidate's own life: habits, preferences, surroundings,
  study or work, past and future plans.
- Everyday register, one clause each, 5 to 18 words, and every question ends with
  a question mark.
- No question may need specialist knowledge, and none may be sensibly answered
  with only 'yes' or 'no' - ask for a reason, a preference or a description.
- Inside one topic, no two questions may ask the same thing in other words.
- Write your own wording. Do not copy or closely imitate questions from published
  IELTS papers, coursebooks or test-preparation websites.
- Topic areas already in the bank, do not repeat them: {{avoid}}
OUTPUT SCHEMA:
{ topics: [{ name: string, questions: [string] }] }"""

P6Q2 = """TASK: Write original IELTS Speaking Part 2 cue cards for a practice question
bank. The bank is shared by every candidate, so write nothing that depends on a
candidate's level.
Write {{n_cards}} cue cards.
RULES:
- 'text' is the task line. It starts with 'Describe', names something the
  candidate can speak about from their own experience for two minutes, is 6 to 20
  words long and ends with a full stop.
- 'points' holds exactly 3 short prompts the candidate should cover, each a noun
  phrase or a 'wh-' clause of 3 to 9 words, lower case, with no final full stop.
- 'explain' starts with 'and explain' and asks for a reason, a feeling or an
  effect. It ends with a full stop.
- 'title' is a 2 to 6 word label for the card.
- Every card must be on a clearly different subject from the others.
- Write your own wording. Do not copy or closely imitate cue cards from published
  IELTS papers, coursebooks or test-preparation websites.
- Card subjects already in the bank, do not repeat them: {{avoid}}
OUTPUT SCHEMA:
{ cards: [{ title: string, text: string, points: [string], explain: string }] }"""

# Câu Part 3 ở ĐÂY là kho dự phòng của ngân hàng đề (UC-05), không phải câu hỏi
# đào sâu của UC-04. UC-04 đòi câu Part 3 bám vào chính câu trả lời của thí sinh
# nên phải sinh lúc thi bằng P6a3; kho này chỉ dùng khi agent không bám được ý
# nào, và không được dùng để đo tiêu chí nghiệm thu UC-04.
P6Q3 = """TASK: Write original IELTS Speaking Part 3 discussion questions for a practice
question bank. They belong to the Part 2 card below and widen its subject into a
general discussion. The bank is shared by every candidate, so write nothing that
depends on a candidate's level and nothing that refers to a particular answer.
PART 2 CARD: {{card}}
Write {{n_questions}} questions, ordered from the most concrete to the most abstract.
RULES:
- Part 3 asks about people in general: causes, consequences, comparisons with the
  past, differences between groups, predictions about the future. It does not ask
  about the candidate's own habits or preferences - that is Part 1.
- One or two clauses, 6 to 28 words, and every question ends with a question mark.
- No two questions may ask the same thing in other words.
- Do not name a real country, company, study or statistic.
- Write your own wording. Do not copy or closely imitate questions from published
  IELTS papers, coursebooks or test-preparation websites.
OUTPUT SCHEMA:
{ questions: [string] }"""

P6A1 = """TASK: Write part of an IELTS Speaking Part 1 exchange, as an automatic speech
recognizer would output it.
CANDIDATE: Vietnamese, age {{age}}, {{years}} years of English, weaknesses {{weakness_list}}.
TARGET LEVEL (never mention it): {{speaking_profile}}
TOPIC: {{topic}}
Use these examiner questions verbatim, in this order, and give the candidate's answer
after each one:
{{part1_script}}
STYLE:
- Punctuated transcript, no timestamps, no stage directions.
- Keep only a few fillers and self-corrections, because ASR drops many of them.
- Examiner turns are exactly the questions given, nothing added.
LENGTH: each candidate answer about {{part1_words}} words.
ERROR PLAN: about {{errors_per_100}} errors per 100 words, mostly of these kinds:
{{weakness_list}}. Spread them out, do not cluster them, do not mark or correct them.
Errors must look like real Vietnamese-learner errors, not typos.
OUTPUT SCHEMA:
{ turns: [{ role: 'examiner'|'candidate', text: string }] }"""

P6A2 = """TASK: Write the candidate's IELTS Speaking Part 2 long turn, as an automatic
speech recognizer would output it.
CANDIDATE: Vietnamese, age {{age}}, {{years}} years of English, weaknesses {{weakness_list}}.
TARGET LEVEL (never mention it): {{speaking_profile}}
CUE CARD: {{cue_card}}
The candidate speaks for up to two minutes and covers every bullet on the card.
LENGTH: {{part2_words}} words. Write at least {{part2_min}} words.
STYLE:
- One continuous spoken answer, punctuated, no headings and no bullet points.
- Keep only a few fillers and self-corrections, because ASR drops many of them.
- Lower levels repeat ideas and run short; higher levels develop each bullet.
ERROR PLAN: about {{errors_per_100}} errors per 100 words, mostly of these kinds:
{{weakness_list}}. Spread them out, do not mark or correct them.
OUTPUT SCHEMA:
{ text: string }"""

P6A3 = """TASK: Write the IELTS Speaking Part 3 discussion, as an automatic speech
recognizer would output it.
CANDIDATE: Vietnamese, age {{age}}, {{years}} years of English, weaknesses {{weakness_list}}.
TARGET LEVEL (never mention it): {{speaking_profile}}
PART 2 THEME: {{theme}}
WHAT THE CANDIDATE ALREADY SAID (earlier answers, quoted for grounding):
{{prior_answers}}
Write {{part3_questions}} examiner questions with the candidate's answer after each.
GROUNDING RULE: every examiner question after the first must pick up a specific idea
the candidate already said above, reusing at least one distinctive word or phrase from
it, and must still open a wider, more abstract discussion.
LENGTH: each candidate answer about {{part3_words}} words.
STYLE:
- Punctuated transcript, no timestamps, no stage directions.
- Examiner turns are short and neutral.
ERROR PLAN: about {{errors_per_100}} errors per 100 words, mostly of these kinds:
{{weakness_list}}. Spread them out, do not mark or correct them.
OUTPUT SCHEMA:
{ turns: [{ role: 'examiner'|'candidate', text: string }] }"""

P6A_UNUSED = """TASK: Write a full IELTS Speaking test (Parts 1, 2, 3) as an automatic speech
recognizer would output it.
CANDIDATE: Vietnamese, age {{age}}, {{years}} years of English, weaknesses {{weakness_list}}.
TARGET LEVEL (never mention it): {{speaking_profile}}
PART 1: topics {{topics}}, {{part1_questions}} questions each. Use these examiner questions
verbatim, in this order:
{{part1_script}}
PART 2: cue card {{cue_card}}; the candidate speaks about {{part2_words}} words.
PART 3: {{part3_questions}} follow-up questions on the Part 2 theme, written by you.
Each Part 3 question after the first must pick up at least one idea the candidate
actually said in an earlier answer.
STYLE:
- Punctuated transcript, no timestamps, no stage directions.
- Keep only a few fillers and self-corrections, because ASR drops many of them.
- Lower levels: short answers, repetition, limited vocabulary, frequent grammar errors.
  Higher levels: longer, better developed answers with few errors.
- Examiner turns are short, neutral and scripted.
LENGTH PER ANSWER: Part 1 about {{part1_words}} words, Part 3 about {{part3_words}} words.
ERROR PLAN: about {{errors_per_100}} errors per 100 words, mostly of these kinds:
{{weakness_list}}. Spread them through the transcript, do not cluster them, do not
mark or correct them. Errors must look like real Vietnamese-learner errors, not typos.
OUTPUT SCHEMA:
{ turns: [{ part: 1|2|3, role: 'examiner'|'candidate', text: string }] }"""

P6A_PLACEMENT = """TASK: Write {{n_sets}} short IELTS Speaking Part 1 exchanges, as an automatic
speech recognizer would output them. Each set is an independent candidate.
CANDIDATES: Vietnamese learners, {{profiles}}
Each set has {{questions_per_set}} examiner questions with the candidate's answer after each.
STYLE:
- Punctuated transcript, no timestamps, no stage directions, few fillers (ASR drops them).
- Each candidate's answers must match the target level described for that set:
  lower levels are short with frequent errors, higher levels longer and more accurate.
- Never mention levels, bands, AI or simulation inside the text.
- Examiner turns are short and neutral.
OUTPUT SCHEMA:
{ sets: [{ set_no: number, turns: [{ role: 'examiner'|'candidate', text: string }] }] }"""

P6B = """Given one candidate turn from an IELTS Speaking test, extract 1 to 3 main points the
candidate made, each as a short English sentence. Do not add points the candidate
did not make.
TURN: {{turn_text}}
OUTPUT SCHEMA: { points: [string] }"""

P7_SWITCH = """TASK: Rewrite the IELTS Speaking candidate answers below so that {{ratio}} of the
sentences are in Vietnamese and the rest stay in English, exactly as a speech
recognizer would transcribe a candidate who code-switches.
RULES:
- Keep the same ideas, the same order and roughly the same length.
- Switch whole sentences, not single words. Do not translate the examiner turns.
- Return every turn you were given, in the same order, with the same part and role.
TURNS: {{turns_json}}
OUTPUT SCHEMA:
{ turns: [{ part: 1|2|3, role: 'examiner'|'candidate', text: string }] }"""

P10 = """You are an experienced IELTS examiner screening synthetic test data.
Use the public IELTS band descriptors.
TASK: IELTS Speaking, Parts 1 to 3, judged from transcript only.
TEXT: {{text}}
Estimate a band for each criterion (FC = Fluency and Coherence, LR = Lexical Resource,
GRA = Grammatical Range and Accuracy) and an overall band. Pronunciation cannot be
judged from a transcript, so ignore it.
Also rate how much the text reads like a real learner produced it
(1 = obviously machine-written, 5 = indistinguishable) and list up to 3 signals.
OUTPUT SCHEMA:
{ criteria: { FC: number, LR: number, GRA: number },
  overall: number, realism_1_5: number, signals: [string] }"""

TEMPLATES = {
    "P6q1": P6Q1,
    "P6q2": P6Q2,
    "P6q3": P6Q3,
    "P6a1": P6A1,
    "P6a2": P6A2,
    "P6a3": P6A3,
    "P6a_placement": P6A_PLACEMENT,
    "P6b": P6B,
    "P7_switch": P7_SWITCH,
    "P10": P10,
}


def render(prompt_id, values):
    """Điền placeholder {{x}}. Thiếu biến là lỗi lập trình, không im lặng bỏ qua."""
    text = TEMPLATES[prompt_id]
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    missing = [
        part.split("}}")[0]
        for part in text.split("{{")[1:]
    ]
    if missing:
        raise KeyError(f"{prompt_id} còn placeholder chưa điền: {missing}")
    return text
