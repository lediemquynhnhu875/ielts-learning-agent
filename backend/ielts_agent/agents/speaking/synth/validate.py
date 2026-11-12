"""Lớp rules của validator Speaking (generate-format.docx mục 5.2).

Hai nhóm hàm:
  * check(prompt_id, data, payload) — chạy ngay trong vòng lặp gen_job, trả về
    danh sách lỗi bằng tiếng Anh để gửi lại cho model (feedback loop).
  * các hàm suite_* — chạy trên toàn tập sau khi lắp ráp, cho báo cáo W2/W4/W6.
"""

import math
import re
import unicodedata

VIET_CHARS = set("ăâđêôơưĂÂĐÊÔƠƯ")
VIET_WORDS = {"là", "của", "và", "những", "không", "được", "tôi", "mình", "rất",
              "cũng", "nhưng", "thì", "này", "cho", "với", "một", "có", "khi",
              "người", "nhiều", "vì", "đã", "sẽ", "để", "ở", "lại", "nên"}
META = re.compile(
    r"\b(as an ai|as a language model|band\s*\d|band score|ielts band|overall band|"
    r"target level|synthetic|simulat(?:ed|ion)|prompt|chatgpt|openai)\b", re.I)
MARKDOWN = re.compile(r"(^|\n)\s*(#{1,6}\s|\*\s|-\s|\d+\.\s)|\*\*|```")


def words(text):
    return [w for w in re.findall(r"[^\W_]+(?:'[^\W_]+)?", text, re.UNICODE) if w]


def is_vietnamese(text):
    """Nhận tiếng Việt qua ký tự riêng và từ chức năng, không chỉ qua dấu."""
    if any(ch in VIET_CHARS for ch in text):
        return True
    lowered = [w.lower() for w in words(text)]
    hits = sum(1 for w in lowered if w in VIET_WORDS)
    if hits >= 2:
        return True
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn")
    return stripped != text and hits >= 1


def viet_sentence_ratio(text):
    parts = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not parts:
        return 0.0
    return sum(1 for s in parts if is_vietnamese(s)) / len(parts)


def _meta_errors(label, text, allow_vietnamese=False):
    errors = []
    hit = META.search(text)
    if hit:
        errors.append(f"{label} leaks meta text {hit.group(0)!r}; remove it (W5)")
    if MARKDOWN.search(text):
        errors.append(f"{label} contains markdown; use plain sentences only (W5)")
    if not allow_vietnamese and is_vietnamese(text):
        errors.append(f"{label} contains Vietnamese; the transcript must be English (W5)")
    return errors


def _turns_shape(data, key="turns"):
    turns = data.get(key)
    if not isinstance(turns, list) or not turns:
        return None, [f"{key} must be a non-empty array"]
    for turn in turns:
        if not isinstance(turn, dict) or not isinstance(turn.get("text"), str):
            return None, [f"every item of {key} needs a string field 'text'"]
        if turn.get("role") not in ("examiner", "candidate"):
            return None, ["role must be exactly 'examiner' or 'candidate'"]
    return turns, []


STOP = {
    "about", "above", "after", "again", "against", "always", "another", "anything",
    "because", "before", "being", "below", "between", "could", "different", "during",
    "either", "enough", "especially", "every", "everything", "first", "friends",
    "further", "generally", "going", "important", "instead", "later", "little",
    "maybe", "might", "money", "months", "mostly", "myself", "never", "often",
    "other", "people", "perhaps", "place", "quite", "rather", "really", "right",
    "should", "since", "something", "sometimes", "still", "their", "there", "these",
    "thing", "things", "think", "those", "though", "through", "times", "under",
    "until", "usually", "where", "which", "while", "whole", "would", "years",
    "yourself", "actually", "course", "example", "exactly", "little", "making",
    "number", "person", "problem", "reason", "around", "better", "cannot",
}


def content_words(text, minimum=5):
    return {w.lower() for w in words(text)
            if len(w) >= minimum and w.lower() not in STOP}


def _answer_length(answers, bounds, key, label, lo=0.75, hi=1.25):
    low, high = bounds.get(key, (0, 10 ** 6))
    mean = sum(len(words(a)) for a in answers) / len(answers)
    if not low * lo <= mean <= high * hi:
        return [f"{label} answers average {mean:.0f} words; each should be about"
                f" {low}-{high} words (W6)"]
    return []


def _verbatim(expected, asked, label):
    if len(asked) != len(expected):
        return [f"{label} must contain exactly {len(expected)} examiner questions,"
                f" got {len(asked)}"]
    for want, got in zip(expected, asked):
        if want.lower().rstrip("?. ") not in got.lower():
            return [f"examiner question {want!r} was changed; use the given"
                    " questions verbatim"]
    return []


# Part 1 có cả câu dạng "Can you tell me ...?" nên nhận cả động từ khuyết thiếu
# lẫn từ hỏi. Bắt buộc kết thúc bằng dấu hỏi để kiểm được bằng code.
OPENER = re.compile(
    r"^(what|where|when|why|how|which|who|whose|do|does|did|are|is|was|were|"
    r"have|has|had|can|could|would|will|shall|should|may|might|tell)\b", re.I)


def _normalise(text):
    return re.sub(r"[^\w\s]+", " ", text.lower()).strip()


def _question_errors(label, text):
    errors = []
    body = text.strip()
    count = len(words(body))
    if not body.endswith("?"):
        errors.append(f"{label}: {body[:48]!r} must end with a question mark")
    if not 5 <= count <= 18:
        errors.append(f"{label}: {body[:48]!r} is {count} words;"
                      " every question must be 5 to 18 words")
    if not OPENER.match(body):
        errors.append(f"{label}: {body[:48]!r} must open with a question word,"
                      " an auxiliary verb or 'tell'")
    return errors + _meta_errors(label, body)


def check_p6q1(data, payload):
    """Ngân hàng đề Part 1: đếm, dạng câu, trùng lặp và vùng chủ đề đã dùng."""
    topics = data.get("topics")
    want = int(payload.get("n_topics", 0))
    if not isinstance(topics, list) or len(topics) != want:
        return [f"topics must be an array of exactly {want} objects"]
    per = int(payload.get("per_topic", 0))
    avoid = {_normalise(a) for a in payload.get("_avoid", []) if str(a).strip()}
    errors, seen = [], {}
    for index, topic in enumerate(topics, 1):
        if not isinstance(topic, dict):
            return [f"topic {index} must be an object"]
        name = topic.get("name")
        if not isinstance(name, str) or not 1 <= len(words(name)) <= 6:
            errors.append(f"topic {index} needs a name of 1 to 6 words")
            name = str(name)
        elif _normalise(name) in avoid:
            errors.append(f"topic {name!r} is already in the bank;"
                          " choose a different area")
        questions = topic.get("questions")
        if not isinstance(questions, list) or len(questions) != per:
            got = len(questions) if isinstance(questions, list) else 0
            errors.append(f"topic {name!r} needs exactly {per} questions, got {got}")
            continue
        bags = []
        for question in questions:
            if not isinstance(question, str) or not question.strip():
                return ["every question must be a non-empty string"]
            errors += _question_errors(f"topic {name!r}", question)
            key = _normalise(question)
            if key in seen:
                errors.append(f"question {question[:48]!r} repeats"
                              f" {seen[key][:48]!r}; every question must differ")
            seen[key] = question
            bags.append(frozenset(content_words(question, 4)))
        for first in range(len(bags)):
            for second in range(first + 1, len(bags)):
                if bags[first] and bags[first] == bags[second]:
                    errors.append(
                        f"topic {name!r}: {questions[first][:40]!r} and"
                        f" {questions[second][:40]!r} ask the same thing;"
                        " make them about different things")
    return errors[:6]


# Từ có trong hầu hết cue card nên không nói gì về chủ đề. Không trừ ra thì mọi
# cặp thẻ đều trùng ở "describe" và bị báo trùng chủ đề oan.
CARD_BOILER = {"describe", "recently", "something", "someone", "experience",
               "memorable", "favorite", "favourite", "important", "interesting",
               "special", "enjoyed", "enjoy"}


def check_p6q2(data, payload):
    """Ngân hàng cue card Part 2: khuôn thẻ đề và chủ đề không trùng nhau."""
    cards = data.get("cards")
    want = int(payload.get("n_cards", 0))
    if not isinstance(cards, list) or len(cards) != want:
        return [f"cards must be an array of exactly {want} objects"]
    avoid = {_normalise(a) for a in payload.get("_avoid", []) if str(a).strip()}
    errors, bags = [], []
    for index, card in enumerate(cards, 1):
        if not isinstance(card, dict):
            return [f"card {index} must be an object"]
        label = f"card {index}"
        title, text = card.get("title"), card.get("text")
        points, explain = card.get("points"), card.get("explain")
        if not isinstance(title, str) or not 1 <= len(words(title)) <= 6:
            errors.append(f"{label} needs a title of 1 to 6 words")
            title = str(title)
        elif _normalise(title) in avoid:
            errors.append(f"card title {title!r} is already in the bank;"
                          " choose a different subject")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label} needs a task line in 'text'")
            text = ""
        else:
            count = len(words(text))
            if not text.strip().lower().startswith("describe"):
                errors.append(f"{label}: the task line must start with 'Describe'")
            if not 6 <= count <= 24:
                errors.append(f"{label}: the task line is {count} words;"
                              " it must be 6 to 24 words")
        if not isinstance(points, list) or len(points) != 3:
            got = len(points) if isinstance(points, list) else 0
            errors.append(f"{label} needs exactly 3 points, got {got}")
            points = []
        for point in points:
            if not isinstance(point, str) or not point.strip():
                return [f"{label}: every point must be a non-empty string"]
            length = len(words(point))
            if not 2 <= length <= 10:
                errors.append(f"{label}: point {point[:40]!r} is {length} words;"
                              " each point must be 2 to 10 words")
            if point.strip().endswith("."):
                errors.append(f"{label}: point {point[:40]!r} must not end with"
                              " a full stop")
            errors += _meta_errors(f"{label} point", point)
        if not isinstance(explain, str) or not explain.strip().lower().startswith(
                "and explain"):
            errors.append(f"{label}: 'explain' must start with 'and explain'")
            explain = str(explain)
        errors += _meta_errors(label, text)
        errors += _meta_errors(f"{label} explain", explain)
        bag = frozenset(content_words(f"{title} {text}", 5)) - CARD_BOILER
        for other, seen in enumerate(bags, 1):
            if bag and seen and len(bag & seen) >= 2:
                errors.append(f"{label} and card {other} are about the same"
                              " subject; each card needs its own subject")
        bags.append(bag)
    return errors[:6]


# Khuôn câu Part 1 lọt vào Part 3. Chỉ bắt mấy dạng rõ ràng: "Do you think ..."
# là câu Part 3 hợp lệ nên không được dính.
PART1_FRAME = re.compile(
    r"^(what|which)(?:\'s| is| are)?\s+your\s+favou?rite\b"
    r"|^how often do you\b"
    r"|^do you (?:usually|often|normally|personally|like|have|prefer|enjoy)\b"
    r"|^have you ever\b"
    r"|^where do you\b", re.I)


# Part 3 thường mở bằng cụm giới từ trước từ hỏi: "In what ways ...",
# "To what extent ...". Dùng OPENER của Part 1 ở đây là loại oan, nên chỉ yêu
# cầu có từ hỏi hoặc trợ động từ trong vài từ đầu.
PART3_OPENER = re.compile(
    r"^(?:[\w'’-]+[\s,]+){0,4}?(what|where|when|why|how|which|who|whose|do|"
    r"does|did|are|is|was|were|have|has|had|can|could|would|will|shall|should|"
    r"may|might)\b", re.I)


def check_p6q3(data, payload):
    """Kho câu Part 3 dự phòng: dạng câu, không trùng nhau, không phải Part 1."""
    questions = data.get("questions")
    want = int(payload.get("n_questions", 0))
    if not isinstance(questions, list) or len(questions) != want:
        got = len(questions) if isinstance(questions, list) else 0
        return [f"questions must be an array of exactly {want} strings, got {got}"]
    errors, seen, bags = [], {}, []
    for question in questions:
        if not isinstance(question, str) or not question.strip():
            return ["every question must be a non-empty string"]
        body = question.strip()
        count = len(words(body))
        if not body.endswith("?"):
            errors.append(f"{body[:48]!r} must end with a question mark")
        if not 6 <= count <= 28:
            errors.append(f"{body[:48]!r} is {count} words;"
                          " every question must be 6 to 28 words")
        if not PART3_OPENER.match(body):
            errors.append(f"{body[:48]!r} needs a question word or an auxiliary"
                          " verb near the start")
        if PART1_FRAME.match(body):
            errors.append(f"{body[:48]!r} asks about the candidate's own habits;"
                          " Part 3 asks about people in general")
        errors += _meta_errors("part 3 bank", body)
        key = _normalise(body)
        if key in seen:
            errors.append(f"{body[:48]!r} repeats {seen[key][:48]!r};"
                          " every question must differ")
        seen[key] = body
        bag = frozenset(content_words(body, 5))
        for other, previous in enumerate(bags, 1):
            if bag and bag == previous:
                errors.append(f"{body[:48]!r} asks the same thing as question"
                              f" {other}; make them about different angles")
        bags.append(bag)
    return errors[:6]


def check_p6a1(data, payload):
    turns, errors = _turns_shape(data)
    if errors:
        return errors
    expected = payload.get("_part1_questions") or []
    asked = [t["text"].strip() for t in turns if t["role"] == "examiner"]
    answers = [t["text"] for t in turns if t["role"] == "candidate"]
    errors += _verbatim(expected, asked, "part 1")
    if len(answers) != len(asked):
        errors.append("give exactly one candidate answer after each question")
    elif answers:
        errors += _answer_length(answers, payload.get("_bounds", {}), "part1", "part 1")
    for index, turn in enumerate(turns):
        errors += _meta_errors(f"turn {index + 1}", turn["text"])
    return errors[:5]


def check_p6a2(data, payload):
    body = data.get("text")
    if not isinstance(body, str) or not body.strip():
        return ["text must be a non-empty string holding the whole long turn"]
    errors = []
    count = len(words(body))
    low, high = payload.get("_bounds", {}).get("part2", (0, 10 ** 6))
    if not low * 0.85 <= count <= high * 1.3:
        errors.append(f"the long turn is {count} words; it must be"
                      f" {low}-{high} words (W6)")
    errors += _meta_errors("the long turn", body)
    return errors[:4]


def check_p6a3(data, payload):
    turns, errors = _turns_shape(data)
    if errors:
        return errors
    want = int(payload.get("part3_questions", 0))
    asked = [t for t in turns if t["role"] == "examiner"]
    answers = [t["text"] for t in turns if t["role"] == "candidate"]
    if want and len(asked) != want:
        errors.append(f"part 3 must contain exactly {want} examiner questions,"
                      f" got {len(asked)}")
    if len(answers) != len(asked):
        errors.append("give exactly one candidate answer after each question")
    if answers:
        errors += _answer_length(answers, payload.get("_bounds", {}), "part3", "part 3")

    # Tiêu chí nghiệm thu UC04: mỗi câu sau câu đầu phải bám một ý đã nói.
    pool = content_words(payload.get("_prior_text", ""))
    ungrounded = []
    for index, turn in enumerate(turns):
        if turn["role"] == "candidate":
            pool |= content_words(turn["text"])
            continue
        order = sum(1 for t in turns[:index] if t["role"] == "examiner")
        if order and not content_words(turn["text"]) & pool:
            ungrounded.append(turn["text"][:70])
    if ungrounded:
        errors.append("these examiner questions pick up nothing the candidate said;"
                      " reuse a distinctive word from an earlier answer: "
                      + "; ".join(repr(q) for q in ungrounded[:2]))
    for index, turn in enumerate(turns):
        errors += _meta_errors(f"turn {index + 1}", turn["text"])
    return errors[:5]


def check_p6a_unused(data, payload):
    turns, errors = _turns_shape(data)
    if errors:
        return errors
    for turn in turns:
        try:
            turn["part"] = int(turn.get("part"))
        except (TypeError, ValueError):
            return ["every turn needs part = 1, 2 or 3"]
        if turn["part"] not in (1, 2, 3):
            return ["every turn needs part = 1, 2 or 3"]

    for part in (1, 2, 3):
        if not any(t["part"] == part for t in turns):
            errors.append(f"part {part} is missing")
    if errors:
        return errors

    expected = payload.get("_part1_questions") or []
    asked = [t["text"].strip() for t in turns if t["part"] == 1 and t["role"] == "examiner"]
    if len(asked) != len(expected):
        errors.append(f"part 1 must contain exactly {len(expected)} examiner questions,"
                      f" got {len(asked)}")
    else:
        for want, got in zip(expected, asked):
            if want.lower().rstrip("?. ") not in got.lower():
                errors.append(f"part 1 examiner question {want!r} was changed; "
                              "use the given questions verbatim")
                break

    p3_questions = [t for t in turns if t["part"] == 3 and t["role"] == "examiner"]
    want3 = payload.get("part3_questions")
    if want3 and len(p3_questions) != int(want3):
        errors.append(f"part 3 must contain exactly {want3} examiner questions,"
                      f" got {len(p3_questions)}")

    bounds = payload.get("_bounds", {})
    p2 = [t for t in turns if t["part"] == 2 and t["role"] == "candidate"]
    if not p2:
        errors.append("part 2 has no candidate turn")
    else:
        count = sum(len(words(t["text"])) for t in p2)
        low, high = bounds.get("part2", (0, 10 ** 6))
        # Nới 15% vì LLM không đếm từ chính xác; ngoài khoảng này thì lệch thật.
        if not low * 0.85 <= count <= high * 1.15:
            errors.append(f"the part 2 answer is {count} words; it must be about"
                          f" {low}-{high} words (W6)")

    for part, key in ((1, "part1"), (3, "part3")):
        answers = [t for t in turns if t["part"] == part and t["role"] == "candidate"]
        if not answers:
            errors.append(f"part {part} has no candidate answer")
            continue
        low, high = bounds.get(key, (0, 10 ** 6))
        mean = sum(len(words(t["text"])) for t in answers) / len(answers)
        if not low * 0.75 <= mean <= high * 1.25:
            errors.append(f"part {part} answers average {mean:.0f} words; each should be"
                          f" about {low}-{high} words (W6)")

    for index, turn in enumerate(turns):
        errors += _meta_errors(f"turn {index + 1}", turn["text"])
    return errors[:6]


def check_p6a_placement(data, payload):
    sets = data.get("sets")
    want = int(payload.get("n_sets", 0))
    if not isinstance(sets, list) or len(sets) != want:
        return [f"sets must be an array of exactly {want} objects"]
    low, high = payload.get("_questions_bounds", (4, 6))
    errors = []
    for index, one in enumerate(sets, 1):
        turns, shape = _turns_shape(one if isinstance(one, dict) else {})
        if shape:
            return [f"set {index}: " + shape[0]]
        asked = [t for t in turns if t["role"] == "examiner"]
        answers = [t for t in turns if t["role"] == "candidate"]
        if not low <= len(asked) <= high:
            errors.append(f"set {index} has {len(asked)} examiner questions;"
                          f" it needs {low}-{high}")
        if len(answers) != len(asked):
            errors.append(f"set {index} needs one candidate answer per question")
        for turn in turns:
            errors += _meta_errors(f"set {index}", turn["text"])
    return errors[:6]


def check_p6b(data, payload):
    points = data.get("points")
    if not isinstance(points, list) or not 1 <= len(points) <= 3:
        return ["points must be an array of 1 to 3 strings"]
    errors = []
    for point in points:
        if not isinstance(point, str) or not point.strip():
            return ["every point must be a non-empty string"]
        if len(words(point)) > 30:
            errors.append(f"point {point[:40]!r} is too long; one short sentence each")
        errors += _meta_errors("point", point)
    return errors[:4]


def check_p7_switch(data, payload):
    turns, errors = _turns_shape(data)
    if errors:
        return errors
    original = payload.get("_original_turns") or []
    if len(turns) != len(original):
        return [f"return exactly {len(original)} turns, in the original order"]
    candidate = [t for t in turns if t["role"] == "candidate"]
    if not candidate:
        return ["no candidate turn came back"]
    ratio = sum(viet_sentence_ratio(t["text"]) for t in candidate) / len(candidate)
    low, high = payload.get("_ratio_bounds", (0.15, 0.30))
    if not low * 0.6 <= ratio <= high * 1.6:
        errors.append(f"about {ratio:.0%} of candidate sentences are Vietnamese;"
                      f" aim for {low:.0%}-{high:.0%}")
    for index, turn in enumerate(turns):
        errors += _meta_errors(f"turn {index + 1}", turn["text"], allow_vietnamese=True)
    return errors[:5]


def check_p10(data, payload):
    criteria = data.get("criteria")
    if not isinstance(criteria, dict):
        return ["criteria must be an object with FC, LR and GRA"]
    errors = []
    for name in ("FC", "LR", "GRA"):
        value = criteria.get(name)
        if not isinstance(value, (int, float)) or math.isnan(value):
            errors.append(f"criteria.{name} must be a number from 0 to 9")
        elif not 0 <= value <= 9:
            errors.append(f"criteria.{name} = {value} is outside 0 to 9")
    overall = data.get("overall")
    if not isinstance(overall, (int, float)) or not 0 <= overall <= 9:
        errors.append("overall must be a number from 0 to 9")
    realism = data.get("realism_1_5")
    if not isinstance(realism, (int, float)) or not 1 <= realism <= 5:
        errors.append("realism_1_5 must be a number from 1 to 5")
    signals = data.get("signals")
    if not isinstance(signals, list) or len(signals) > 3:
        errors.append("signals must be an array of at most 3 strings")
    return errors[:5]


CHECKS = {
    "P6q1": check_p6q1,
    "P6q2": check_p6q2,
    "P6q3": check_p6q3,
    "P6a1": check_p6a1,
    "P6a2": check_p6a2,
    "P6a3": check_p6a3,
    "P6a_placement": check_p6a_placement,
    "P6b": check_p6b,
    "P7_switch": check_p7_switch,
    "P10": check_p10,
}


def check(prompt_id, data, payload):
    if not isinstance(data, dict):
        return ["output must be a single JSON object"]
    return CHECKS[prompt_id](data, payload)


# ----- suite: chạy trên toàn tập sau khi lắp ráp -----------------------------

def spearman(xs, ys):
    """Spearman rho, có xử lý hạng đồng (W2 cần ngưỡng 0.7)."""
    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = shared
            i = j + 1
        return ranks

    if len(xs) < 3:
        return float("nan")
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def mtld(tokens, threshold=0.72):
    """Measure of Textual Lexical Diversity, hai chiều, cho W2."""
    def run(seq):
        factors, types, count = 0.0, set(), 0
        for token in seq:
            types.add(token.lower())
            count += 1
            if len(types) / count <= threshold:
                factors += 1
                types, count = set(), 0
        if count:
            factors += (1 - len(types) / count) / (1 - threshold)
        return len(seq) / factors if factors else float(len(seq))

    if len(tokens) < 20:
        return float("nan")
    return (run(tokens) + run(tokens[::-1])) / 2


def ngram_overlap(a, b, n=4):
    def grams(text):
        ws = [w.lower() for w in words(text)]
        return {tuple(ws[i:i + n]) for i in range(max(0, len(ws) - n + 1))}
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))
