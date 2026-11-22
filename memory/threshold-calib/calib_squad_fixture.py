"""Construct a fixed public transfer set from the original SQuAD 2.0 dev JSON."""

import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path


def digest(s):
    return sha256(s.encode("utf-8")).hexdigest()


def first_excerpt(paragraph):
    text = paragraph["context"]
    if len(text) <= 300:
        return text
    # Full sentences fit in the provider's 300-character displayed line.
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", text[:300])]
    return text[: ends[-1]] if ends else ""


def squad_fixture(path, article_limit=50, article_offset=0, support_keywords=False):
    if article_offset < 0 or article_limit < 1:
        raise ValueError("invalid article slice")
    data = json.loads(Path(path).read_text(encoding="utf-8"))["data"]
    docs, questions, support = {}, [], {}
    eligible_articles = 0
    for article in sorted(data, key=lambda a: digest(a["title"])):
        paragraphs = sorted(article["paragraphs"], key=lambda p: digest(p["context"]))
        for par in paragraphs:
            text = first_excerpt(par)
            if len(text) < 50:
                continue
            pos = [
                q
                for q in par["qas"]
                if not q["is_impossible"]
                and any(
                    text[a["answer_start"] : a["answer_start"] + len(a["text"])] == a["text"]
                    for a in q["answers"]
                )
            ]
            neg = [q for q in par["qas"] if q["is_impossible"]]
            if not pos or not neg:
                continue
            if support_keywords:
                exemplar = min(pos, key=lambda q: digest(q["id"]))
                phrase = exemplar["question"].strip().casefold()
                pos = [q for q in pos if q["question"].strip().casefold() != phrase]
                neg = [q for q in neg if q["question"].strip().casefold() != phrase]
                if not pos or not neg:
                    continue
            eligible_articles += 1
            if eligible_articles <= article_offset:
                break
            name = article["title"]
            docs[name] = (text, [])
            if support_keywords:
                support[name] = phrase
            for group, target in [(pos, [name]), (neg, [])]:
                for q in sorted(group, key=lambda q: digest(q["id"]))[:3]:
                    questions.append(
                        {"qid": q["id"], "q": q["question"], "targets": target, "split": "transfer"}
                    )
            break
        if len(docs) == article_limit:
            break
    tokenized = {k: re.findall(r"[a-z][a-z'-]{2,}", text.lower()) for k, (text, _) in docs.items()}
    freq = Counter(t for ts in tokenized.values() for t in set(ts))
    # A deterministic fact-only keyword baseline; source questions and answers are never used here.
    kw = {
        k: sorted(dict.fromkeys(ts), key=lambda t: (freq[t], -ts.count(t), ts.index(t)))[:6]
        for k, ts in tokenized.items()
    }
    if support_keywords:
        stop = {
            "the",
            "and",
            "for",
            "are",
            "was",
            "were",
            "this",
            "that",
            "what",
            "which",
            "who",
            "how",
            "where",
            "when",
            "why",
            "does",
            "did",
            "has",
            "have",
            "had",
            "can",
            "may",
            "with",
            "from",
            "into",
            "about",
            "whom",
            "these",
            "those",
            "they",
            "their",
            "its",
            "his",
            "her",
            "she",
            "him",
        }
        for k, phrase in support.items():
            words = [w for w in re.findall(r"[a-z][a-z'-]{2,}", phrase) if w not in stop and len(w) <= 40]
            kw[k] = list(dict.fromkeys([*words, *kw[k]]))[:8]
    return docs, kw, questions
