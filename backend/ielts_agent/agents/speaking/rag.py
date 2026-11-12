"""Local rubric retrieval: BM25 + dense LSA, reciprocal rank fusion, reranking.

No learner transcript is sent to an embedding provider. LSA is a corpus-trained
linear semantic approximation, not a pretrained embedding or cross encoder.
"""

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re

import numpy as np

DEFAULT_CORPUS = Path(__file__).resolve().parents[4] / ".cache/rag/descriptors.json"
SOURCE_URL = "https://takeielts.britishcouncil.org/sites/default/files/%5Bdownloads%5D/ielts_speaking_band_descriptors.pdf"
QUERIES = {
    "FC": "fluency coherence hesitation repetition self correction pauses linking connectives development topics",
    "LR": "lexical resource vocabulary flexibility paraphrase idiomatic collocation meaning word choice",
    "GRA": "grammatical range accuracy complex structures sentences errors comprehension",
    "PR": "pronunciation intelligibility phonological features stress rhythm intonation individual sounds",
}
STOP = set("a an the of to and or is are in on for with it this that i my me at as by be has have can does how what band speaking criterion".split())


def tokens(text):
    return [t for t in re.findall(r"[^\W\d_]+", text.lower()) if t not in STOP]


class RubricIndex:
    def __init__(self, corpus):
        self.corpus = corpus
        self.counts = [Counter(tokens(d["text"])) for d in corpus]
        self.vocab = sorted({t for counts in self.counts for t in counts})
        self.positions = {t: i for i, t in enumerate(self.vocab)}
        n = len(corpus)
        self.df = np.array([sum(t in c for c in self.counts) for t in self.vocab])
        self.idf = np.log((1 + n) / (1 + self.df)) + 1
        matrix = np.array([[c.get(t, 0) for t in self.vocab] for c in self.counts], dtype=float).reshape(n, len(self.vocab))
        self.lengths = matrix.sum(axis=1)
        self.average_length = float(self.lengths.mean()) if n else 1
        weighted = np.log1p(matrix) * self.idf
        if weighted.size:
            _, _, vt = np.linalg.svd(weighted, full_matrices=False)
            # Truncated latent semantic space; deterministic local embeddings.
            self.basis = vt[:min(16, max(1, n - 1))].T
            self.embeddings = weighted @ self.basis
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            self.embeddings /= np.maximum(norms, 1e-12)
        else:
            self.basis = np.zeros((len(self.vocab), 0))
            self.embeddings = np.zeros((n, 0))

    def search(self, query, criterion=None, band=None, top_k=4, method="hybrid_rerank", require_overlap=True):
        if require_overlap and re.search(r"\b(writing|listening|reading|refund|registration|test fee|exam date|medical|visa)\b", query, re.I):
            return []
        selected = [i for i, d in enumerate(self.corpus) if d["test_part"] == "speaking" and
                    (criterion is None or d["criterion"] == criterion) and (band is None or d.get("band") == band)]
        counts = Counter(tokens(query))
        qvec = np.array([counts.get(t, 0) for t in self.vocab], dtype=float)
        lexical = np.zeros(len(self.corpus))
        for token in counts:
            if token not in self.positions:
                continue
            j = self.positions[token]
            freq = np.array([c.get(token, 0) for c in self.counts], dtype=float)
            lexical += np.log(1 + (len(self.corpus) - self.df[j] + .5) / (self.df[j] + .5)) * freq * 2.5 / (freq + 1.5 * (.25 + .75 * self.lengths / max(self.average_length, 1)))
        dense_query = (np.log1p(qvec) * self.idf) @ self.basis
        dense = self.embeddings @ (dense_query / max(float(np.linalg.norm(dense_query)), 1e-12))
        bm_order = sorted(selected, key=lambda i: (-lexical[i], self.corpus[i]["chunk_id"]))
        dense_order = sorted(selected, key=lambda i: (-dense[i], self.corpus[i]["chunk_id"]))
        fusion = {i: 1 / (60 + bm_order.index(i) + 1) + 1 / (60 + dense_order.index(i) + 1) for i in selected}
        # Lightweight feature reranker: lexical coverage + cosine + fused ranks.
        coverage = {i: sum(t in self.counts[i] for t in counts) / max(len(counts), 1) for i in selected}
        rerank = {i: fusion[i] + .02 * coverage[i] + .01 * max(float(dense[i]), 0) for i in selected}
        order = bm_order if method == "bm25" else sorted(selected, key=lambda i: (-rerank[i], self.corpus[i]["chunk_id"]))
        if require_overlap:
            order = [i for i in order if lexical[i] > 0]
        return [{**self.corpus[i], "retrieval": {"bm25": round(float(lexical[i]), 6), "dense_lsa": round(float(dense[i]), 6),
                                                "rrf": round(fusion[i], 6), "rerank": round(rerank[i], 6), "rank": rank}}
                for rank, i in enumerate(order[:top_k], 1)]


@lru_cache(maxsize=4)
def cached_index(serialized):
    return RubricIndex(json.loads(serialized))


def search(corpus, query, **kwargs):
    return cached_index(json.dumps(corpus, sort_keys=True, ensure_ascii=False)).search(query, **kwargs)


def grading_context(corpus, criterion, answers):
    # Retain the entire band ladder (<=10 chunks) to avoid restricting score range
    # based on retrieval. Rank by criterion concepts plus observed transcript.
    query = QUERIES[criterion] + " " + " ".join(a["transcript"] for a in answers)[:4000]
    return search(corpus, query, criterion=criterion, top_k=len(corpus), require_overlap=False)
