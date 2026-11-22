"""Replay one local answerability check on the five upstream public margin traces.

The 0.95 and 0.5 traces have the same git SHA. The archived 1.0 baseline has a
different SHA, so first check that its observable outputs match 0.95 on every row.
The published traces identify candidates admitted by margin 0.5. They do not
contain the raw cosine ranks of the rest of the store.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
import logging
import os
from pathlib import Path
import runpy
import statistics
import sys
import tempfile
import time
from types import SimpleNamespace

from calib_answerability import AnswerVerifier, INSTRUCTION, MODEL_CARD_INSTRUCTION, load_plugin, local_vectors, open_fixture, prepare
import calib_vendor


SETS = ('multi', 'contrast_en', 'contrast_ru', 'contrast_zh', 'household_test')


def public_facts(root, name):
    if name == 'multi':
        path, variable = root / 'tests/test_holographic_languages.py', 'CORPUS'
    else:
        path = root / 'tools' / ('household.py' if name == 'household_test' else name + '.py')
        variable = 'FACTS'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError(f'{variable} missing from the public fixture')


def documents_for(facts, name, lang):
    if name == 'multi':
        return facts[lang]
    if name == 'household_test':
        return {key: variants[lang] for key, variants in facts.items()}
    return facts


def key(row):
    return row['set'], row['lang'], row['qid']


def unchanged(gate, first, second):
    return (all(first[k] == second[k] for k in ('q', 'kind', 'split', 'keys', 'sources', 'out_n', 'hit5'))
            and set(first['targets']) == set(second['targets'])
            and gate._noise(first) == gate._noise(second) and gate._confused(first) == gate._confused(second))


def new_candidate(base, wide, documents):
    old, new = base['keys'], wide['keys']
    if len(old) >= 5 or any('meaning' in tags for tags in base['sources'].values()):
        return None
    addition = [f for f in new if f not in old]
    if len(addition) != 1 or [f for f in new if f in old] != old:
        return None
    fact = addition[0]
    # provenance_probe.store_facts inserts in dictionary order; sources is keyed by the resulting SQLite ID.
    # Check the entire ID -> public key mapping before assigning the new fact a semantic provenance.
    key_for_id = {str(i): name for i, name in enumerate(documents, 1)}
    sources = {key_for_id[i]: tags for i, tags in wide['sources'].items()}
    if set(sources) != set(new) or len(sources) != len(new):
        raise ValueError('public fact IDs and traced keys differ')
    semantic = {name for name, tags in sources.items() if 'meaning' in tags}
    return fact if semantic == {fact} else None


def count(gate, base, point):
    before, after = set(base['keys'][:5]), set(point['keys'][:5])
    targets = set(base['targets'])
    had, hit = bool(targets & before), bool(targets & after)
    noise, confused = gate._noise(point), point['kind'] == 'real' and gate._confused(point)
    added = set(point['keys']) - set(base['keys'])
    any_other = bool(targets and (after - targets))
    return dict(rows=1, labelled=bool(targets), hit=hit, b=hit and not had, c=had and not hit,
                lost_targets=len((before & targets) - after), noise=noise, confusion=confused,
                new_noise=noise and not gate._noise(base), new_confusion=confused and not gate._confused(base),
                any_other_top5=any_other, new_any_other_top5=any_other and not (before - targets),
                added_target=len(added & targets), added_other=len(added - targets),
                added_to_no_answer=len(added) if not targets else 0)


def evaluate(root, model):
    gate = calib_vendor.load(root).mcnemar_gate
    totals = {name: Counter() for name in ('baseline', 'wide', 'verified')}
    rescues = {}
    times = []
    heads = set()
    for name in SETS:
        paths = [root / 'results' / f'provenance_{name}_m{margin}_on.jsonl' for margin in ('0.5', '0.95', '1')]
        _, _, by, _ = gate._paired(paths[:2], 'margin', gate._HEAD, value=float)
        archived = [json.loads(line) for line in paths[2].read_text(encoding='utf-8').splitlines() if line.strip()]
        if len(archived) != len(by[0.95]) or {key(r) for r in archived} != set(by[0.95]):
            raise ValueError('default and same-head control have different queries')
        facts = public_facts(root, name)
        rescues[name] = 0
        for reference in archived:
            k = key(reference)
            base, wide = by[0.95][k], by[0.5][k]
            heads.add(tuple(base[field] for field in gate._HEAD))
            if len(heads) != 1:
                raise ValueError('public sets have different run metadata')
            if float(reference['margin']) != 1.0 or not unchanged(gate, reference, base):
                raise ValueError('default and same-head control disagree')
            docs = documents_for(facts, name, base['lang'])
            fact = new_candidate(base, wide, docs)
            approved = False
            if fact is not None:
                start = time.perf_counter()
                # Same 300-character visible fact line as the upstream prefetch renderer, without metadata.
                flat = ' '.join(docs[fact][0].split())
                approved = model.score(base['q'], flat if len(flat) <= 300 else flat[:299] + '…') > 0
                times.append(1000 * (time.perf_counter() - start))
            for arm, take in [('baseline', False), ('wide', fact is not None), ('verified', approved)]:
                # The addition fits by the fifth position. All three upstream confuser definitions depend on
                # top-five membership, so wide's own confusion field is valid for an append after all old keys.
                counts = count(gate, base, wide if take else base)
                totals[arm].update(counts)
                if arm == 'verified':
                    rescues[name] += counts['b']
    for counts in totals.values():
        counts['p'] = gate.mcnemar(counts['b'], counts['c'])
    return {'arms': totals, 'calls': len(times), 'median_ms': round(statistics.median(times), 1) if times else None,
            'rescued_by_set': rescues}


def household_dev(root, core, model, bge_dir):
    """Independent questions on the published household dev split. Both arms run on the same local build."""
    pkg = load_plugin(root, core)
    data = runpy.run_path(str(root / 'tools/household.py'))
    gate = calib_vendor.load(root).mcnemar_gate
    encode = local_vectors(bge_dir, pkg.embeddings.TEXT_MAX_CHARS)
    totals = {name: Counter() for name in ('baseline', 'wide', 'verified')}
    candidates = 0
    rescued_ids = set()
    for lang in data['LANGS']:
        with tempfile.TemporaryDirectory(prefix='recall-household-') as tmp:
            os.environ['HERMES_HOME'] = tmp
            provider = open_fixture(pkg, SimpleNamespace(store=None, facts=None), Path(tmp))
            try:
                by_name = {}
                contents = []
                for name, variants in data['FACTS'].items():
                    content, entities = variants[lang]
                    added = json.loads(provider.handle_tool_call('fact_store', {
                        'action': 'add', 'content': content, 'entities': entities}))
                    if added.get('status') != 'added' or not pkg._sendable(content):
                        raise ValueError('incomplete public household store')
                    by_name[name] = added['fact_id']
                    contents.append(content)
                ids = list(by_name.values())
                qs = []
                for group, kind in [('QUERIES', 'real'), ('CHITCHAT', 'chit')]:
                    for qid, q in data[group].items():
                        if q['split'] == 'dev':
                            qs.append({'qid': qid, 'kind': kind, 'q': q[lang],
                                       'targets': [by_name[n] for n in q.get('targets', [])]})
                qfile = Path(tmp) / 'public_queries.json'
                qfile.write_text(json.dumps(qs), encoding='utf-8')
                asked = [q for q in qs if not pkg._secret_in(q['q']) and pkg.embeddings.worth_asking(q['q'], before_turn=True)]
                scores = encode([q['q'] for q in asked]) @ encode(contents).T
                by_qid = dict(zip((q['qid'] for q in asked), scores.tolist(), strict=True))
                probes = [{**q, 'meaning_call': 'ok' if q['qid'] in by_qid else 'skipped',
                           'cos': dict.fromkeys(('content', 'content+keywords'), by_qid.get(q['qid']))} for q in qs]
                dump = {'fact_ids': ids, 'eligible': ids, 'recallable': ids, 'probes': probes}
                rows = prepare(pkg, provider, dump, [qfile], arms=('baseline',))
            finally:
                provider.shutdown()
        names = {i: n for n, i in by_name.items()}
        for r in rows:
            q = r['probe']
            gold = data['QUERIES'].get(q['qid']) if q['kind'] == 'real' else None
            def result(keys):
                return {**q, 'set': 'household', 'keys': keys, 'out_n': len(keys),
                        'confused': data['confusion'](gold, [names[i] for i in keys[:5]]) if gold else []}
            old = result(r['baseline'])
            candidate = r['margin_candidate']
            candidates += candidate is not None
            approved = candidate is not None and model.score(r['query'], r['margin_text']) > 0
            for arm, take in [('baseline', False), ('wide', candidate is not None), ('verified', approved)]:
                point = result(r['baseline'] + [candidate]) if take else old
                counts = count(gate, old, point)
                totals[arm].update(counts)
                if arm == 'verified' and counts['b']:
                    rescued_ids.add(q['qid'])
    for counts in totals.values():
        counts['p'] = gate.mcnemar(counts['b'], counts['c'])
    return {'arms': totals, 'calls': candidates, 'distinct_rescued_qids': len(rescued_ids)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plugin-src', type=Path, required=True)
    ap.add_argument('--verifier', required=True, help='local Qwen3-Reranker-0.6B directory')
    ap.add_argument('--model-card-instruction', action='store_true', help='use the published web-search instruction as a control')
    ap.add_argument('--household-dev', type=Path, metavar='BGE_DIR', help='run the public dev questions using local bge-m3')
    ap.add_argument('--core-src', type=Path, help='Hermes core or KG-1 core_shim for the fresh dev run')
    args = ap.parse_args()
    if args.household_dev and not args.core_src:
        ap.error('--household-dev needs --core-src')
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DISABLE_PROGRESS_BARS='1')
    verifier = AnswerVerifier(args.verifier, MODEL_CARD_INSTRUCTION if args.model_card_instruction else INSTRUCTION)
    if args.household_dev:
        print(json.dumps(household_dev(args.plugin_src, args.core_src, verifier, args.household_dev)))
    else:
        print(json.dumps(evaluate(args.plugin_src, verifier)))
