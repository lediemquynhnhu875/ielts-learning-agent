"""Local near-duplicate detection for exam questions.

Cosine similarity over content-word unigrams and bigrams, weighted by how
distinctive each term is inside the compared set. This catches rewordings that
reuse the same vocabulary and structure. It is not a trained paraphrase model:
two questions that mean the same thing in entirely different words can still
score low, so a pass here is not proof that two questions differ in meaning.
Callers compare question stems, so a grounding quote shared by two different
discussion angles is removed by the caller before scoring. No learner text is
sent anywhere.
"""

from collections import Counter
import math
import re


# Only closed-class words are dropped. Question words such as why/how/what carry
# the discussion intent, so they must stay in the comparison.
STOP = frozenset("a an the of to and or is are was were be been being am do does did "
                 "in on at for with by from as it its this that these those there".split())
NEAR_DUPLICATE = 0.62


def shingles(text):
    words = [w for w in re.findall(r"[^\W\d_]+", str(text or "").lower()) if w not in STOP]
    counts = Counter(words)
    counts.update(" ".join(pair) for pair in zip(words, words[1:]))
    return counts


def cosine(left, right):
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    if not shared:
        return 0.0
    dot = sum(left[key] * right[key] for key in shared)
    size = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(sum(v * v for v in right.values()))
    return dot / size if size else 0.0


def weighted(counts, idf):
    return Counter({term: value * idf.get(term, 1.0) for term, value in counts.items()})


def inverse_frequency(documents):
    """Discount wording shared by many questions in this session.

    Frames such as 'what ... most about your ...' recur across unrelated bank
    questions, so unweighted cosine rates them as similar. Terms are weighted by
    how distinctive they are inside the set being compared.
    """
    frequency = Counter(term for document in documents for term in set(document))
    total = len(documents)
    return {term: math.log((1 + total) / (1 + count)) + 1 for term, count in frequency.items()}


def nearest(text, existing):
    """Closest already-asked question as (score, text), or (0.0, None)."""
    candidate = shingles(text)
    others = [shingles(other) for other in existing]
    idf = inverse_frequency([candidate, *others])
    target = weighted(candidate, idf)
    scored = [(round(cosine(target, weighted(other, idf)), 4), text)
              for other, text in zip(others, existing)]
    return max(scored, default=(0.0, None))


def is_near_duplicate(text, existing, threshold=NEAR_DUPLICATE):
    score, match = nearest(text, existing)
    return (score >= threshold, score, match)
