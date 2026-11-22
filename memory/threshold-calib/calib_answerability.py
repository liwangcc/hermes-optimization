"""Offline top-one admission experiment on a frozen store and a calib_dump score matrix.

Use --plugin-src and --core-src for the pinned plugin and Hermes core (or KG-1 core_shim).
Only aggregate counts leave this process. The provider opens a disposable database and
receives precomputed cosines at _meaning_of. Its normal lexical blend, coverage, entity
stream and name checks still run. Each question starts a fresh session, with rerank off
and the default unlimited token budget. This file is an experiment, not a runtime plugin.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import statistics
import sys
import tempfile
import time

import calib_probes
import calib_replay
import calib_vendor


INSTRUCTION = ("Decide whether the document alone supplies a concrete answer to the query, "
               "including the requested entity and attribute. A shared topic without the "
               "requested information is insufficient.")
MODEL_CARD_INSTRUCTION = 'Given a web search query, retrieve relevant passages that answer the query'
PREFIX = ('<|im_start|>system\nJudge whether the Document meets the requirements based on the '
          'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
          '<|im_end|>\n<|im_start|>user\n')
SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'


class AnswerVerifier:
    """Qwen3-Reranker yes/no logit difference, using the model card's input format."""

    def __init__(self, model_dir, instruction=INSTRUCTION):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        path = Path(model_dir).resolve(strict=True)
        self.instruction = instruction
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        dtype = torch.bfloat16 if self.device == 'cuda' and torch.cuda.is_bf16_supported() else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, dtype=dtype).to(self.device).eval()
        self.yes, self.no = self.tokenizer.convert_tokens_to_ids(['yes', 'no'])
        self.prefix = self.tokenizer.encode(PREFIX, add_special_tokens=False)
        self.suffix = self.tokenizer.encode(SUFFIX, add_special_tokens=False)
        self.score('What colour is the cup?', 'The cup is blue.')  # exclude model warm-up from timings

    def score(self, query, content):
        import torch

        text = f'<Instruct>: {self.instruction}\n<Query>: {query}\n<Document>: {content}'
        middle = self.tokenizer.encode(text, add_special_tokens=False)
        if len(self.prefix) + len(middle) + len(self.suffix) > self.model.config.max_position_embeddings:
            return float('-inf')
        inputs = torch.tensor([self.prefix + middle + self.suffix], device=self.device)
        with torch.inference_mode():
            logits = self.model(input_ids=inputs, use_cache=False, logits_to_keep=1).logits[0, -1].float()
            return (logits[self.yes] - logits[self.no]).item()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_plugin(src, core):
    sys.path.insert(0, str(Path(core).resolve(strict=True)))
    spec = importlib.util.spec_from_file_location('hermes_plugin_holographic', Path(src) / '__init__.py')
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def open_fixture(pkg, args, tmp):
    path = tmp / 'fixture.db'
    if args.store:
        with closing(sqlite3.connect(Path(args.store).resolve(strict=True).as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(path)) as dst:
                src.backup(dst)
    provider = pkg.HolographicMemoryProvider(config={'db_path': str(path), 'embeddings': 'off'})
    provider.initialize(session_id='fixture', hermes_home=str(tmp))
    if provider._store is None:
        raise ValueError('could not open fixture')
    if args.facts:
        kws = read_json(args.keywords)
        for f in sorted(read_json(args.facts), key=lambda row: row['fact_id']):
            words = kws[str(f['fact_id'])]
            answer = json.loads(provider.handle_tool_call('fact_store', {
                'action': 'add', 'origin': 'said', 'content': f['content'], 'keywords': words}))
            if answer.get('fact_id') != f['fact_id'] or answer.get('keywords', []) != words:
                raise ValueError('synthetic store differs from the frozen fixture')
    # _stream_extras reads these settings; _meaning_of below does all vector lookup in memory.
    provider._embedding = pkg.embeddings.Settings({'embeddings': 'on'})
    return provider


def top_unique(ids, values):
    high = max(values)
    return ids[values.index(high)] if values.count(high) == 1 else None


def local_vectors(model_dir, char_limit):
    """Use the frozen bge-m3 directory offline, with the same pooling and precision as calib_dump."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import torch

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = SentenceTransformer(str(Path(model_dir).resolve(strict=True)), device=device, local_files_only=True,
                                model_kwargs={'torch_dtype': torch.float16} if device == 'cuda' else {})

    def encode(texts):
        result = model.encode([s[:char_limit] for s in texts], batch_size=16,
                              normalize_embeddings=True, show_progress_bar=False)
        return result.astype(np.float64)
    return encode


def alias_checks(rows, pkg, provider, dump, model_dir):
    """Two closest alias owners and the search maxima of blind aliases with their own facts held out."""
    import numpy as np

    ids = dump['fact_ids']
    facts = {i: (content, tags) for i, content, tags in provider._store.read('SELECT fact_id, content, tags FROM facts')}
    texts, owners, passages, first_alias, owner_col = [], [], [], [], []
    for column, fact_id in enumerate(ids):
        content, tags = facts[fact_id]
        words = list(dict.fromkeys(pkg._split_tags(tags)[1]))
        joined = f"{content}\nkeywords: {', '.join(words)}"
        if words and pkg._sendable(joined):
            first_alias.append(len(texts))
            owner_col.append(column)
            texts.extend(words)
            owners.extend([fact_id] * len(words))
            passages.append(joined)
        else:
            passages.append(content)
    for row in rows:
        row.update(two_aliases=False, alias_null=False)
    pending = [r for r in rows if r['candidate'] is not None]
    if len(texts) < 3 or len(ids) < 2 or not pending:
        return
    encode = local_vectors(model_dir, pkg.embeddings.TEXT_MAX_CHARS)
    aliases = encode(texts)
    background = aliases[first_alias] @ encode(passages).T
    background[np.arange(len(first_alias)), owner_col] = -np.inf
    maxima = background.max(axis=1)
    for row, scores in zip(pending, encode([r['query'] for r in pending]) @ aliases.T, strict=True):
        first, second, third = np.argsort(-scores, kind='stable')[:3]
        row['two_aliases'] = scores[second] > scores[third] and owners[first] == owners[second] == row['candidate']
        best = max(row['probe']['cos']['content+keywords'])
        row['alias_null'] = (1 + np.sum(maxima >= best)) / (1 + len(maxima)) <= 0.05


def prepare(pkg, provider, dump, query_files, arms=('baseline', 'floor', 'H1', 'H3')):
    ids = dump['fact_ids']
    facts = {f['fact_id']: dict(f) for f in provider._store.read('SELECT fact_id, content, tags, trust_score FROM facts')}
    if set(ids) != {i for i, f in facts.items() if pkg._sendable(f['content'])}:
        raise ValueError('score columns and sendable store facts differ')
    qs = [q for path in query_files for q in calib_probes.labelled_probes(path, set(facts))]
    queries = {q['qid']: q for q in qs}
    probes = dump['probes']
    if len(qs) != len(queries) or len(probes) != len(queries) or set(queries) != {p['qid'] for p in probes}:
        raise ValueError('query and dump rows differ')
    original_lookup = provider._meaning_of
    original_extras = provider._stream_extras
    rows = []

    class Floor(pkg.embeddings.Meaning):
        def standout(self, fact_id, margin, min_score):
            return self.sims[fact_id] >= 0.55

    class WiderMargin(pkg.embeddings.Meaning):
        def standout(self, fact_id, margin, min_score):
            return super().standout(fact_id, 0.5, min_score)

    for p in probes:
        q = queries[p['qid']]
        query = q['q']
        if q['kind'] != p['kind'] or set(q['targets']) != set(p['targets']):
            raise ValueError('labels and dump rows differ')
        ok = p['meaning_call'] == 'ok'
        if ok != (not pkg._secret_in(query) and pkg.embeddings.worth_asking(query, before_turn=True)):
            raise ValueError('embedding eligibility differs from the dump')
        raw = joined = floor = wider = winner = None
        lift_agrees = False
        if ok:
            cos = p['cos']['content']
            kw = p['cos']['content+keywords']
            if len(cos) != len(ids) or len(kw) != len(ids):
                raise ValueError('incomplete score row')
            weight = provider._embedding.weight
            raw = pkg.embeddings.Meaning(ids, cos, weight)
            floor = Floor(ids, cos, weight)
            wider = WiderMargin(ids, cos, weight)
            joined = pkg.embeddings.Meaning(ids, kw, weight)
            winner = top_unique(ids, kw)
            lift_agrees = winner is not None and winner == top_unique(ids, [b - a for a, b in zip(cos, kw)])
        row = {'probe': p, 'query': query, 'candidate': None, 'margin_candidate': None, 'lift': lift_agrees}
        for arm in arms:
            # Every arm uses the original content vectors for the lexical search. Only the semantic append varies.
            meaning = floor if arm == 'floor' else raw
            def lookup(text, *, before_turn):
                if text != query or not before_turn:
                    raise ValueError('the dump does not represent the query passed to prefetch')
                return meaning

            def extras(text, vec, have, key, turn):
                def fits(f):
                    return (provider._not_recent(key, f, turn) and provider._recallable(f)
                            and provider._retriever.names_fit(text, f))

                if arm in ('baseline', 'floor') or vec is None:
                    result = original_extras(text, vec, set(have), key, turn)
                    if arm == 'baseline' and vec is not None:
                        sem, entities, _ = result
                        shown = have | {f['fact_id'] for f in entities}
                        if not sem and len(shown) < 5:
                            offered, _, _ = original_extras(text, wider, set(have), key, turn)
                            if offered and offered[0]['fact_id'] not in shown:
                                row['margin_candidate'] = offered[0]['fact_id']
                                row['margin_text'] = pkg._one_line(offered[0]['content'])
                            if (winner is not None and winner not in shown and winner in dump['eligible']
                                    and winner in dump['recallable'] and fits(facts[winner])):
                                row['candidate'] = winner
                                row['visible_text'] = pkg._one_line(facts[winner]['content'])
                    return result
                _, entities, _ = original_extras(text, None, set(have), key, turn)
                shown = have | {f['fact_id'] for f in entities}
                if arm == 'H1':
                    candidates = provider._retriever.by_meaning(joined, exclude=shown, min_trust=provider._min_trust,
                                                               limit=4, margin=0.5 if shown else 0.7)
                else:
                    first, score = joined.ranked()[0]
                    candidates = [facts[first]] if score >= 0.55 and first not in shown and first in dump['eligible'] else []
                added = next((f for f in candidates if fits(f)), None)
                return ([added], entities, {added['fact_id']}) if added else ([], entities, set())

            provider._meaning_of = lookup
            provider._stream_extras = extras
            try:
                block = provider.prefetch(query, session_id=f"{arm}-{p['qid']}")
            finally:
                provider._meaning_of = original_lookup
                provider._stream_extras = original_extras
            if provider._recall_error:
                raise ValueError('prefetch failed for a fixture row')
            row[arm] = [int(i) for i in re.findall(r'^- #(\d+) ', block, re.MULTILINE)]
        rows.append(row)
    return rows


def summarize(rows, old, new, gate):
    hit = rescued = lost = lost_targets = noise = confusion = new_noise = new_confusion = right = wrong = 0
    for row, before, after in zip(rows, old, new, strict=True):
        p = row['probe']
        targets = set(p['targets'])
        left, current = set(before[:5]), set(after[:5])
        had, has = bool(targets & left), bool(targets & current)
        hit += has
        rescued += has and not had
        lost += had and not has
        lost_targets += len((targets & left) - current)
        noisy = not targets and bool(after)
        confused = bool(targets and (current - targets))
        noise += noisy
        confusion += confused
        new_noise += noisy and not before
        new_confusion += confused and not (left - targets)
        right += len((set(after) - set(before)) & targets)
        wrong += len(set(after) - set(before) - targets)
    return dict(hit=hit, b=rescued, c=lost, lost_targets=lost_targets, p=gate.mcnemar(rescued, lost), noise=noise,
                confusion=confusion, new_noise=new_noise, new_confusion=new_confusion, added_target=right, added_other=wrong)


def evaluate(rows, gate, verifier=None, calibration=None):
    base = [r['baseline'] for r in rows]
    metrics = {arm: summarize(rows, base, [r[arm] for r in rows], gate) for arm in ('baseline', 'H1', 'H3')}
    pending = [r for r in rows if r['candidate'] is not None]
    times = []
    if verifier:
        for r in pending:
            start = time.perf_counter()
            r['score'] = verifier.score(r['query'], r['visible_text'])
            times.append(1000 * (time.perf_counter() - start))
    rules = {'always': lambda r: True, 'top_lift': lambda r: r['lift'],
             'oracle': lambda r: r['candidate'] in r['probe']['targets']}
    if rows and 'two_aliases' in rows[0]:
        rules.update(two_aliases=lambda r: r['two_aliases'], alias_null=lambda r: r['alias_null'],
                     H1_or_two_aliases=lambda r: r['candidate'] in r['H1'] or r['two_aliases'])
    if verifier:
        rules.update(yes=lambda r: r['score'] > 0, yes_and_lift=lambda r: r['score'] > 0 and r['lift'])
        if calibration is not None:
            rules['transfer'] = lambda r: r['score'] > calibration
    for name, rule in rules.items():
        result = [r['baseline'] + [r['candidate']] if r['candidate'] is not None and rule(r) else r['baseline'] for r in rows]
        metrics[name] = summarize(rows, base, result, gate)
    summary = {'rows': len(rows), 'labelled': sum(bool(r['probe']['targets']) for r in rows), 'candidates': len(pending),
               'median_ms': round(statistics.median(times), 1) if times else None, 'arms': metrics}
    if verifier:
        wrong = [r['score'] for r in pending if r['candidate'] not in r['probe']['targets']]
        summary['scored_non_targets'] = len(wrong)
        summary['max_non_target_logit'] = max(wrong, default=None)
        margin_output = []
        for r in rows:
            candidate = r['margin_candidate']
            extra = []
            if candidate is not None:
                score = r['score'] if candidate == r['candidate'] else verifier.score(r['query'], r['margin_text'])
                if score > 0:
                    extra = [candidate]
            margin_output.append(r['baseline'] + extra)
        metrics['margin_yes'] = summarize(rows, base, margin_output, gate)
    summary['margin_candidates'] = sum(r['margin_candidate'] is not None for r in rows)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dump', required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--facts')
    group.add_argument('--store', help='frozen SQLite copy, opened read-only')
    ap.add_argument('--keywords', help='blind keywords for synthetic --facts')
    ap.add_argument('--queries', required=True, nargs='+')
    ap.add_argument('--plugin-src', default=calib_vendor.DEFAULT_SRC, type=Path)
    ap.add_argument('--core-src', required=True, type=Path)
    ap.add_argument('--verifier', help='local Qwen3-Reranker-0.6B model directory')
    ap.add_argument('--model-card-instruction', action='store_true', help='use the published web-search instruction as a control')
    ap.add_argument('--alias-model', type=Path, help='same local bge-m3 as the dump, to also test the blind alias controls')
    ap.add_argument('--calibration', type=float, help='max_non_target_logit from an independent development set with the same verifier')
    ap.add_argument('--check-zc', help='published content/zbar rows for this store snapshot')
    ap.add_argument('--check-fc', help='published content/floor rows for this store snapshot')
    args = ap.parse_args()
    if args.facts and not args.keywords:
        ap.error('--facts needs --keywords')
    if (args.model_card_instruction or args.calibration is not None) and not args.verifier:
        ap.error('verifier controls need --verifier')
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DISABLE_PROGRESS_BARS='1')
    sys.dont_write_bytecode = True
    dump = read_json(args.dump)
    with tempfile.TemporaryDirectory(prefix='recall-fixture-') as work:
        os.environ['HERMES_HOME'] = work
        pkg = load_plugin(args.plugin_src, args.core_src)
        provider = open_fixture(pkg, args, Path(work))
        try:
            rows = prepare(pkg, provider, dump, args.queries)
            if args.alias_model:
                alias_checks(rows, pkg, provider, dump, args.alias_model)
        finally:
            provider.shutdown()
    v = calib_vendor.load(args.plugin_src)
    instruction = MODEL_CARD_INSTRUCTION if args.model_card_instruction else INSTRUCTION
    verifier = AnswerVerifier(args.verifier, instruction) if args.verifier else None
    summary = evaluate(rows, v.mcnemar_gate, verifier, args.calibration)
    for label, path in [('baseline', args.check_zc), ('floor', args.check_fc)]:
        if path:
            ref = calib_replay._rows(path)
            if set(ref) != {r['probe']['qid'] for r in rows} or any(
                    set(ref[r['probe']['qid']]['targets']) != set(r['probe']['targets']) for r in rows):
                raise ValueError('reference queries or targets differ')
            summary['matches_' + label] = sum(ref[r['probe']['qid']]['keys'] == r[label] for r in rows)
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    main()
