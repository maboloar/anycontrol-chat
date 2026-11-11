"""BM25 검색 (외부 패키지 없음). 카드 검색에 쓴다.

점수 말고 coverage(질문의 중요한 단어 중 이 문서가 맞춘 비율)도 같이 돌려준다.
BM25 점수는 문서마다 크기가 달라 '충분히 맞았는지'를 판단하기 어렵지만, coverage 는 0~1 이라 문턱을 정하기 쉽다.
"""
from __future__ import annotations
import math
import re
from collections import Counter

from .textutil import tokenize

K1 = 1.4
B = 0.55


class Index:
    def __init__(self, docs: list[list[tuple[str, float]]], glossary: dict[str, list[str]] | None = None) -> None:
        """docs[i] = [(텍스트, 가중치), ...] — 가중치가 큰 필드(질문·키워드)가 점수에 더 크게 반영된다."""
        self.tf: list[Counter] = []
        self.dl: list[float] = []
        df: Counter = Counter()
        for fields in docs:
            c: Counter = Counter()
            for text, w in fields:
                for t, n in Counter(tokenize(text)).items():
                    c[t] += n * w
            self.tf.append(c)
            self.dl.append(sum(c.values()))
            df.update(c.keys())
        self.N = len(docs)
        self.avgdl = (sum(self.dl) / self.N) if self.N else 1.0
        self.idf = {t: math.log(1.0 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.gloss = _symmetric(glossary or {})

    def expand(self, query: str) -> dict[str, float]:
        """질문 토큰 → 가중치. 용어집에 있는 표현이 질문에 있으면 번역어 토큰도 약하게 더한다."""
        w: dict[str, float] = {}
        for t in tokenize(query):
            w[t] = max(w.get(t, 0.0), 1.0)
        q = query.lower()
        for key, alts in self.gloss.items():
            if _contains(q, key):
                for alt in alts:
                    for t in tokenize(alt):
                        w[t] = max(w.get(t, 0.0), 0.7)
        return w

    def search(self, query: str, k: int = 5) -> list[tuple[int, float, float]]:
        """[(문서 번호, BM25 점수, coverage), ...] 점수 내림차순."""
        full = self.expand(query)
        qw = {t: x for t, x in full.items() if t in self.idf}
        if not qw:
            return []
        orig = set(tokenize(query))
        cw = {t: (1.0 if t in orig else 0.25) for t in qw}     # 용어집으로 더한 번역어는 coverage 에 약하게만 반영
        total = sum(cw[t] * self.idf[t] for t in qw)
        # 질문에 있는데 자료에는 한 번도 안 나온 단어는 '맞추지 못한 단어'다. coverage 분모에 넣어야
        # 엉뚱한 질문이 우연히 맞은 한두 단어만으로 높은 coverage 를 받지 않는다. (용어집으로 더한 번역어는 제외)
        unseen = set(tokenize(query)) - set(self.idf)
        if unseen:
            max_idf = math.log(1.0 + (self.N + 0.5) / 0.5)
            total += len(unseen) * max_idf
        out = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            hit = 0.0
            norm = K1 * (1 - B + B * self.dl[i] / self.avgdl)
            for t, x in qw.items():
                f = tf.get(t)
                if not f:
                    continue
                s += x * self.idf[t] * f * (K1 + 1) / (f + norm)
                hit += cw[t] * self.idf[t]
            if s > 0:
                out.append((i, s, hit / total if total else 0.0))
        out.sort(key=lambda r: -r[1])
        return out[:k]


def _contains(text: str, key: str) -> bool:
    if re.search(r"[가-힣]", key):
        return key in text
    return re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", text) is not None


def _symmetric(g: dict[str, list[str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, vs in g.items():
        k = k.lower()
        out.setdefault(k, [])
        for v in vs:
            v = v.lower()
            if v not in out[k]:
                out[k].append(v)
            out.setdefault(v, [])
            if k not in out[v]:
                out[v].append(k)
    return out
