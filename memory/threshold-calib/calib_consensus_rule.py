"""Additional recall for explicit questions when dense and lexical retrieval agree.

This module is the frozen rule used by calib_consensus.py. Build the lexical index
when indexing the store. At query time the caller supplies one vector ranking on
content plus keywords. Ties and already displayed winners do not trigger a substitute.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict

import numpy as np

_QUESTION = re.compile(
    r"[?？؟]|谁|什么|哪|怎么|怎样|为何|为什么|是否|多少|啥|咋|多久|"
    r"几[点次个岁月号年天]|[吗么](?:[呢啊呀嘛]?[。.!！]?)?$|"
    r"\b(?:who|what|when|where|why|which|how|whose)\b",
    re.IGNORECASE,
)
_HAN = re.compile(r"([\u3400-\u9fff]+)")
_WORD = re.compile(r"[\u3400-\u9fff]+|[^\W_]+")


def terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    result = set()
    for word in _WORD.findall(_HAN.sub(r" \1 ", normalized)):
        if "\u3400" <= word[0] <= "\u9fff":
            result.update(word[i : i + 2] for i in range(len(word) - 1))
        else:
            result.add(word)
    return result


def dominant(scores, winner, factor):
    best = scores[winner]
    if best <= 0:
        return False
    second = max((value for i, value in enumerate(scores) if i != winner), default=0.0)
    return best > second and best >= second * factor


class KeywordIndex:
    def __init__(self, facts):
        # Each item contains the fact ID, visible text and its allowed keywords.
        self.ids = [fact_id for fact_id, _, _ in facts]
        self.has_keywords = [bool(words) for _, _, words in facts]
        self.new_terms = [set().union(*(terms(k) for k in words)) - terms(text) for _, text, words in facts]
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("duplicate fact id")
        documents = [terms(" ".join([text, *words])) for _, text, words in facts]
        freq = Counter(t for doc in documents for t in doc)
        n = len(documents)
        self.weights = {t: math.log((n + 1) / (df + 0.5)) for t, df in freq.items()}
        self.doc_postings = defaultdict(list)
        self.alias_postings = defaultdict(list)
        self.alias_owner = []
        for i, ((_, _, words), doc) in enumerate(zip(facts, documents, strict=True)):
            for t in doc:
                self.doc_postings[t].append((i, 1 / math.sqrt(len(doc))))
            for word in dict.fromkeys(words):
                ts = terms(word)
                scale = 1 / math.sqrt(max(1.0, math.fsum(self.weights[t] for t in ts)))
                alias = len(self.alias_owner)
                self.alias_owner.append(i)
                for t in ts:
                    self.alias_postings[t].append((alias, scale))

    def scores(self, query):
        docs = [0.0] * len(self.ids)
        aliases = defaultdict(float)
        for t in sorted(terms(query)):
            weight = self.weights.get(t, 0.0)
            for i, scale in self.doc_postings.get(t, ()):
                docs[i] += weight * scale
            for alias, scale in self.alias_postings.get(t, ()):
                aliases[alias] += weight * scale
        best_alias = [0.0] * len(self.ids)
        for alias, score in aliases.items():
            owner = self.alias_owner[alias]
            best_alias[owner] = max(best_alias[owner], score)
        return docs, best_alias

    def choose(self, query, joined, keyword, shown, floors, *, arm="novel_terms"):
        """Return at most one new ID. Caller applies the provider's admission filters."""
        if arm not in ("novel_terms", "silent_agreement", "agreement", "both", "shown", "silent"):
            raise ValueError("unknown arm")
        n = len(self.ids)
        if len(shown) >= 5 or n < 3:
            return None
        scores = np.asarray(joined)
        if scores.shape != (n,) or not np.all(np.isfinite(scores)):
            return None
        i = int(np.argmax(scores))
        winner = self.ids[i]
        if not self.has_keywords[i] or np.count_nonzero(scores == scores[i]) != 1 or winner in shown:
            return None
        if arm == "novel_terms" and self.new_terms[i].isdisjoint(terms(query)):
            return None
        if (shown and arm in ("silent", "silent_agreement")) or (not shown and arm == "shown"):
            return None
        if shown or arm in ("novel_terms", "agreement", "silent_agreement"):
            key_scores = np.asarray(keyword)
            if key_scores.shape != (n,) or not np.all(np.isfinite(key_scores)):
                return None
            if np.count_nonzero(key_scores >= key_scores[i]) != 1:
                return None
            threshold = math.sqrt(2 * math.log(n))
            joint_z, key_z = separation(scores, i), separation(key_scores, i)
            if shown:
                return winner if min(joint_z, key_z) >= threshold + 1 else None
            if (
                _QUESTION.search(query)
                and joint_z >= threshold
                and key_z >= threshold + 2
                and dominant(self.scores(query)[1], i, 1.5)
            ):
                return winner
        elif arm != "shown" and _QUESTION.search(query) and scores[i] >= floors[i]:
            docs, aliases = self.scores(query)
            if dominant(aliases, i, 1.5) or dominant(docs, i, 3.0):
                return winner
        return None


def separation(scores, i):
    """Standardize a candidate against its competitors, excluding the candidate itself."""
    rest = np.delete(np.asarray(scores, dtype=np.float64), i)
    deviation = float(rest.std())
    if deviation <= 1e-9:
        return -math.inf
    return (float(scores[i]) - float(rest.mean())) / deviation


def background_floors(content, joined, block_size=64):
    """95th percentile of foreign facts' content-to-candidate cosine; computed at indexing."""
    if content.shape != joined.shape or content.ndim != 2:
        raise ValueError("incompatible fact matrices")
    n = len(content)
    if n < 3:
        return np.full(n, np.inf)
    floors = np.empty(n)
    for start in range(0, n, block_size):
        stop = min(n, start + block_size)
        scores = content @ joined[start:stop].T
        scores[np.arange(start, stop), np.arange(stop - start)] = np.nan
        floors[start:stop] = np.nanpercentile(scores, 95, axis=0)
    return floors
