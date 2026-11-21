"""The Desktop job "Initialize threshold": calibrate the recall threshold of the embedding mode in use on this
profile's own facts (threshold_calib.py) and propose a value beside its field.

  local  semantic_tau: vectors from the sidecar's /embed, admission as the sidecar and prefetch do it (cosine >= tau
         among facts above the trust floor, the closest semantic_max_extra).
  cloud  embedding_min_score: vectors from the base provider's own client, admission by its own Meaning.standout
         (the floor on top of its z-score bar), walked as its by_meaning and prefetch walk it.

Nothing is written to the config here: the proposal is kept beside the service receipt, and the Desktop writes it once
the user confirms. Too few facts, or a model that cannot tell them apart, says why and proposes nothing.
"""
from __future__ import annotations

import importlib
import json
from array import array
from pathlib import Path
from typing import Any, Generator

from . import cloud_setup, managed_local, settings, sidecar_index
from . import threshold_calib as calib
from .setup_common import message, progress, result

JOB_ID = "semantic-threshold"
_FILE = "threshold.json"
_LOCAL_BATCH = 16  # the sidecar's own batch size
_LOCAL_SECONDS = 600.0  # one batch on a CPU
_CLOUD_SECONDS = 120.0  # per request, as the calibration tool waits


def _field(mode: str) -> str:
    return "embedding_min_score" if mode == "cloud" else "semantic_tau"


def _identity(home: str, section: dict, mode: str, base) -> str:
    """Which model a proposal was made for: with another model or address it is stale."""
    if mode == "cloud":
        return "cloud " + base.embeddings.Settings(section).tag
    url = str(section.get("semantic_url") or settings.DEFAULTS["semantic_url"])
    model = managed_local.deployed(home, url)
    return f"local {url} {model.id} {model.rev}" if model else f"local {url}"


def _path(home: str) -> Path:
    return managed_local._root(Path(home)) / _FILE


def _proposal(home: str) -> dict:
    try:
        raw = json.loads(_path(home).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _same(suggested: str, stored: Any) -> bool:
    try:
        return abs(float(suggested) - float(stored)) < 1e-9
    except (TypeError, ValueError):
        return False


def action(home: str, section: dict, facts: int | None, base) -> dict:
    """The job as the Desktop lists it: bound to the threshold of the mode in use, with the last proposal for the
    model in use until the stored value is that one."""
    mode = settings.mode(section)
    field = _field(mode)
    ready, status, zh = True, "", ""
    if not mode:
        ready, status, zh = False, "Connect a cloud or local embedding model first.", "请先连接云端或本地向量模型。"
    elif facts is None:
        ready, status, zh = False, "Calibration needs a profile-wide fact store.", "校准需要配置级事实库。"
    elif facts < calib.MIN_FACTS:
        ready = False
        status = f"Too few facts to calibrate: {facts} stored, {calib.MIN_FACTS} needed. The current value stays."
        zh = f"样本不足：事实库只有 {facts} 条事实，至少需要 {calib.MIN_FACTS} 条。保留当前值。"
    job: dict[str, Any] = {"id": JOB_ID, "label": "Initialize threshold", "field": field, "ready": ready}
    if mode == "cloud":
        description = ("Sends this profile's fact text and questions cut from it to the connected embedding API (what "
                       "it already receives), and proposes a minimum similarity. Nothing is saved until you confirm.")
        zh_description = "向已连接的向量接口发送当前档案的事实文本和从中截取的探针（与日常向量化的内容相同），给出建议的最低相似度。确认前不写入配置。"
    else:
        description = ("Embeds this profile's facts and questions cut from them on the local model, and proposes the "
                       "lowest threshold that keeps unrelated questions out. Nothing leaves this machine; nothing is "
                       "saved until you confirm.")
        zh_description = "用本机模型向量化当前档案的事实和从中截取的探针，给出能挡住无关问题的最低阈值。数据留在本机，确认前不写入配置。"
    last = _proposal(home)
    if ready and last.get("field") == field and last.get("identity") == _identity(home, section, mode, base):
        status, zh = str(last.get("status") or ""), str(last.get("status_zh") or "")
        suggested = last.get("suggested")
        if isinstance(suggested, str) and suggested and not _same(suggested, section.get(field, settings.DEFAULTS[field])):
            job["suggestion"] = suggested
    return {**job, "description": description, "status": status,
            "translations": {"zh": {"label": "一键初始化阈值", "description": zh_description, "status": zh}}}


def _local_rule(section: dict, rows: list[dict], base) -> dict:
    """semantic_tau, as the sidecar and _add_semantic admit: a fact above the trust floor whose cosine reaches tau,
    the closest semantic_max_extra of them. The sidecar's vector text is content and tags."""
    is_greeting = importlib.import_module(f"{base.__name__}.text").is_greeting
    url = str(section.get("semantic_url") or settings.DEFAULTS["semantic_url"])
    floor = float(section.get("min_trust_threshold", 0.3))
    keep = int(section.get("semantic_max_extra", settings.DEFAULTS["semantic_max_extra"]))
    held = [r for r in rows if r["trust_score"] is not None and r["trust_score"] >= floor]

    def embed(batch: list[str]) -> list:
        try:
            vectors = sidecar_index._call(url, "/embed", {"texts": batch}, timeout=_LOCAL_SECONDS).get("vectors")
        except (OSError, ValueError):
            vectors = None
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise ValueError(message("The local embedding service did not return vectors.", "本地向量服务未返回向量。"))
        return vectors

    return {
        "texts": {r["fact_id"]: (r["content"] or "") + " " + (r["tags"] or "") for r in held},
        "pool": {r["fact_id"]: r["content"] or "" for r in held},
        "askable": lambda text: bool(text) and not is_greeting(text),
        "embed": embed, "batch": _LOCAL_BATCH,
        "scored": calib.ranked,
        "admit": lambda ranked, tau: [fact_id for fact_id, cosine in ranked[:keep] if cosine >= tau],
        "candidates": calib.GRID,
        "current": float(section.get("semantic_tau", settings.DEFAULTS["semantic_tau"])),
    }


def _cloud_rule(section: dict, rows: list[dict], base) -> dict:
    """embedding_min_score, as the base admits a fact on meaning alone: its Meaning.standout at RECALL_MARGIN over
    every vector it holds, then by_meaning's trust filter and prefetch's cut to embedding_prefetch_facts."""
    from agent.secret_scope import get_secret_str

    emb = base.embeddings
    screen = importlib.import_module(f"{base.__name__}.screen")
    conf = emb.Settings(section)
    slot = conf.key_env
    client = emb.Embedder(conf, environ={slot: "" if slot == cloud_setup.NO_KEY else get_secret_str(slot)})
    why = client.unavailable()
    if why:
        raise ValueError(message(f"The embedding API cannot be used: {why}.", f"向量接口不可用：{why}。"))
    keep = conf.recall_facts
    if not keep:
        raise ValueError(message("Facts recalled on meaning alone is 0: the minimum similarity has no effect.",
                                 "「仅凭语义召回的事实数」为 0，最低相似度不起作用。"))
    floor = float(section.get("min_trust_threshold", 0.3))
    sendable = [r for r in rows if screen._sendable(r["content"] or "")]  # what the base ever embeds
    eligible = {r["fact_id"] for r in sendable if r["trust_score"] is not None and r["trust_score"] >= floor}
    recallable = {r["fact_id"] for r in sendable if not screen._role_prompt(r["content"] or "")}

    def embed(batch: list[str]) -> list:
        vectors = client.embed(batch, budget=_CLOUD_SECONDS)
        if vectors is None:  # status() names a category, never the key or the address
            raise ValueError(message(f"The embedding API failed: {client.status()}.", f"向量接口请求失败：{client.status()}。"))
        return vectors

    def scored(vector, ids, vectors, holdout):
        ranked = calib.ranked(vector, ids, vectors, holdout)  # the store without a held-out fact, as the base holds it
        return emb.Meaning([i for i, _ in ranked], [s for _, s in ranked], 0.0), ranked

    def admit(scored_, min_score):
        meaning, ranked = scored_
        picked = []
        for fact_id, _ in ranked:  # standout falls with similarity: the first miss ends the list
            if not meaning.standout(fact_id, emb.RECALL_MARGIN, min_score):
                break
            if fact_id in eligible:
                picked.append(fact_id)
                if len(picked) >= keep + 3:
                    break
        return [fact_id for fact_id in picked if fact_id in recallable][:keep]

    return {
        "texts": {r["fact_id"]: emb.vector_text(r["content"] or "", r["tags"]) for r in sendable},
        "pool": {r["fact_id"]: r["content"] or "" for r in sendable if r["fact_id"] in eligible & recallable},
        "askable": lambda text: not screen._secret_in(text) and emb.worth_asking(text, before_turn=True),
        "embed": embed, "batch": emb.BATCH,
        "scored": scored, "admit": admit,
        "candidates": (None, *calib.GRID),  # None: the z-score bar alone
        "current": conf.min_score,
    }


def _shown(value) -> tuple[str, str]:
    return ("unset", "未设置") if value is None else (f"{value:g}",) * 2


def _named(value) -> tuple[str, str]:
    return ("no floor", "不设下限") if value is None else _shown(value)


def _counts(measures: list[dict]) -> tuple[str, str]:
    """Fragments recalled and unanswerable probes let in, over every draw."""
    total = {key: sum(m[key] for m in measures) for key in measures[0]}
    return (f"{total['hits']}/{total['positives']} fragments recalled, {total['noise']}/{total['negatives']} "
            "unanswerable probes let in",
            f"片段召回 {total['hits']}/{total['positives']}、无答案探针误召回 {total['noise']}/{total['negatives']}")


def _verdict(found: dict | None, measured, current, loosest, facts: int) -> tuple[str, str, str]:
    """(the value to suggest or "", what it rests on in English, in Chinese). *measured(value)*: what a value does
    on every draw; *loosest*: the first candidate."""
    now, now_zh = _shown(current)
    kept, kept_zh = f"The current value ({now}) stays.", f"保留当前值（{now_zh}）。"
    if found is None:
        return ("", f"No suggestion: no threshold up to {calib.GRID[-1]} keeps the unanswerable probes out. {kept}",
                f"未给出建议：阈值取到 {calib.GRID[-1]} 仍挡不住无答案探针。{kept_zh}")
    counts, counts_zh = _counts(found["at"])
    value, value_zh = _named(found["value"])
    if not found["ok"]:
        base, base_zh = _counts(measured(loosest))
        loose, loose_zh = _named(loosest)
        return ("", f"No suggestion: keeping every unanswerable probe out takes {value}, where too few fragments are "
                    f"still recalled ({counts}; {calib.MIN_RECALL:.0%} needed on each draw). At the loosest setting "
                    f"({loose}): {base}. This model does not tell related from unrelated text on this store. {kept}",
                f"未给出建议：要挡住全部无答案探针需取 {value_zh}，此时片段召回不足（{counts_zh}；每批需不低于 "
                f"{calib.MIN_RECALL:.0%}）。最宽松的设置（{loose_zh}）下：{base_zh}。该模型在这个事实库上分不开相关与无关内容。"
                f"{kept_zh}")
    if found["value"] is None:
        return ("", f"No floor needed: the default admission lets no unanswerable probe in ({counts}). {kept}",
                f"无需设置下限：默认准入在两批探针上没有误召回（{counts_zh}）。{kept_zh}")
    each = " and ".join(_named(v)[0] for v in found["each"])
    each_zh = "、".join(_named(v)[1] for v in found["each"])
    was, was_zh = _counts(measured(current))
    return (f"{found['value']:.2f}",
            f"Suggested {value} (was {now}). Basis: {facts} facts and two draws of probes cut from them. The lowest "
            f"value that lets no unanswerable probe in is {each} on the two draws; the stricter is taken: {counts}. "
            f"At {now}: {was}. Fragments share words with their fact, so recall reads high; the unanswerable side is "
            "the dependable one.",
            f"建议值 {value_zh}（校准时为 {now_zh}）。依据：{facts} 条事实、两批从事实截取的探针。两批各自挡住全部无答案探针的"
            f"最低值为 {each_zh}，取较严的一个：{counts_zh}。取 {now_zh} 时：{was_zh}。片段与原事实字面重叠，召回偏乐观，"
            "误召回一侧可信。")


def run(home: str, section: dict, rows: list[dict], base) -> Generator[dict, None, None]:
    """*rows*: every fact of the store (fact_id, content, tags, trust_score)."""
    from utils import atomic_json_write

    mode = settings.mode(section)
    if not mode:
        raise ValueError(message("Connect a cloud or local embedding model first.", "请先连接云端或本地向量模型。"))
    identity = _identity(home, section, mode, base)

    def finish(suggested: str, en: str, zh: str) -> dict:
        _path(home).parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(_path(home), {"identity": identity, "field": _field(mode), "suggested": suggested,
                                        "status": en, "status_zh": zh}, mode=0o600)
        return result(en, zh)

    yield progress("Reading the fact store…", "正在读取事实库…")
    rule = _cloud_rule(section, rows, base) if mode == "cloud" else _local_rule(section, rows, base)
    now, now_zh = _shown(rule["current"])
    sets = calib.probe_sets(rule["pool"], rule["askable"])
    if len(rule["pool"]) < calib.MIN_FACTS or not calib.enough(sets):
        yield finish("", f"Too few facts to calibrate: {len(rule['pool'])} can be recalled on meaning, "
                         f"{calib.MIN_FACTS} with usable text are needed. The current value ({now}) stays.",
                     f"样本不足：可按语义召回的事实只有 {len(rule['pool'])} 条，至少需要 {calib.MIN_FACTS} 条"
                     f"且文本可用作探针。保留当前值（{now_zh}）。")
        return
    ids, batch = list(rule["texts"]), rule["batch"]
    vectors: list = []
    for start in range(0, len(ids), batch):
        vectors += [array("f", v) for v in rule["embed"]([rule["texts"][i] for i in ids[start:start + batch]])]
        yield progress(f"Embedded {len(vectors)} of {len(ids)} facts…", f"已向量化 {len(vectors)}/{len(ids)} 条事实…")
    questions = [probe["q"] for probes in sets for probe in probes]
    asked: list = []
    for start in range(0, len(questions), batch):
        asked += [array("f", v) for v in rule["embed"](questions[start:start + batch])]
    if len({len(v) for v in vectors + asked}) != 1:
        raise ValueError(message("The vectors differ in size: the model changed during the run.",
                                 "向量维度不一致：校准期间模型发生了变化。"))
    yield progress(f"Scoring {len(questions)} probes…", f"正在比对 {len(questions)} 条探针…")
    answers = iter(asked)
    draws = [[(probe, rule["scored"](next(answers), ids, vectors, probe["holdout"])) for probe in probes]
             for probes in sets]
    found = calib.pick(draws, rule["admit"], rule["candidates"])

    def measured(value) -> list[dict]:
        return [calib.measure(draw, rule["admit"], value) for draw in draws]

    yield finish(*_verdict(found, measured, rule["current"], rule["candidates"][0], len(rule["pool"])))
