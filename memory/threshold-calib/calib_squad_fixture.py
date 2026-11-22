"""Construct a fixed public transfer set from the original SQuAD 2.0 dev JSON."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re


def digest(s):
    return sha256(s.encode("utf-8")).hexdigest()


def first_excerpt(paragraph):
    text = paragraph["context"]
    if len(text) <= 300:
        return text
    # Full sentences fit in the provider's 300-character displayed line.
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", text[:300])]
    return text[:ends[-1]] if ends else ""


def squad_fixture(path, article_limit=50):
    data = json.loads(Path(path).read_text(encoding="utf-8"))["data"]
    docs, questions = {}, []
    for article in sorted(data, key=lambda a: digest(a["title"])):
        paragraphs = sorted(article["paragraphs"], key=lambda p: digest(p["context"]))
        for par in paragraphs:
            text = first_excerpt(par)
            if len(text) < 50:
                continue
            pos = [q for q in par["qas"] if not q["is_impossible"] and any(
                text[a["answer_start"]:a["answer_start"]+len(a["text"])] == a["text"] for a in q["answers"])]
            neg = [q for q in par["qas"] if q["is_impossible"]]
            if not pos or not neg:
                continue
            name = article["title"]
            docs[name] = (text, [])
            for group, target in [(pos, [name]), (neg, [])]:
                for q in sorted(group, key=lambda q: digest(q["id"]))[:3]:
                    questions.append(dict(qid=q["id"], q=q["question"], targets=target, split="transfer"))
            break
        if len(docs) == article_limit:
            break
    tokenized = {k: re.findall(r"[a-z][a-z'-]{2,}", text.lower()) for k, (text, _) in docs.items()}
    freq = Counter(t for ts in tokenized.values() for t in set(ts))
    # A deterministic fact-only keyword baseline; source questions and answers are never used here.
    kw = {k: sorted(dict.fromkeys(ts), key=lambda t: (freq[t], -ts.count(t), ts.index(t)))[:6]
          for k, ts in tokenized.items()}
    return docs, kw, questions

