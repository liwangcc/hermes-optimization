"""The upstream PR #10 gate branches (tools/mcnemar_gate.py report()) recomputed on our dumps."""
import ast, math, re
from pathlib import Path
import daily_eval as d, frozen_rules as fr

PLUG = Path(__file__).resolve().parents[3] / "vendor" / "holographic-0.30.0"
tree = ast.parse((PLUG / "tests/test_holographic_languages.py").read_text(encoding="utf-8"))
ns = {}
for s in tree.body:  # ANTON, IRMA = {...}, {...}; then PROBES uses them
    if isinstance(s, ast.Assign) and len(s.targets) == 1:
        t = s.targets[0]
        if isinstance(t, ast.Tuple) and [getattr(e, "id", "") for e in t.elts] == ["ANTON", "IRMA"]:
            ns["ANTON"], ns["IRMA"] = ast.literal_eval(s.value)
        elif getattr(t, "id", "") == "PROBES":
            ns["PROBES"] = eval(compile(ast.Expression(s.value), "probes", "eval"), {}, ns)
PROBES = ns["PROBES"]

def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)

def gate_rows(fx):
    name = fx.name; id_of = {f["key"]: f["fact_id"] for f in fx.facts}
    out = []
    if name.startswith("household"):
        for q in fx.q:
            out.append(("chit" if q["qid"].startswith("h") else "real", set(q["targets"]), set(q.get("confusers", [])), q.get("split")))
    elif name.startswith("contrast"):
        tq = {q["qid"]: q for q in fx.q}
        for q in fx.q:
            m = re.fullmatch(r"p(\d+)q(\d)", q["qid"])
            if m:
                sib = tq.get(f"p{m.group(1)}q{1 - int(m.group(2))}")
                out.append(("real", set(q["targets"]), (set(sib["targets"]) - set(q["targets"])) if sib else set(), "all"))
            else:
                out.append(("chit", set(), set(), "all"))
    elif name.startswith("multi"):
        lang = name.split("-")[1]
        persons = {n: {id_of[k] for k in ks if k in id_of} for n, ks in dict(PROBES[lang]).items()}
        for q in fx.q:
            other = set()
            if q["targets"]:
                for n in persons:
                    if n in q["q"]:
                        other = set().union(*(v for m, v in persons.items() if m != n))
            out.append(("real" if q["targets"] else "chit", set(q["targets"]), other, "all"))
    else:
        return None
    return out

def gate(fxs, rule, ref=d.daily, split=None):
    g = dict(n=0, h_off=0, h=0, b=0, c=0, conf_off=0, conf=0, neg_off=0, neg=0, l5=0)
    for fx in fxs:
        rows = gate_rows(fx)
        if rows is None:
            continue
        for i, (kind, gold, conf, sp) in enumerate(rows):
            if split and fx.name.startswith("household") and sp != split:
                continue
            a, o = rule(fx, i), ref(fx, i)
            if kind == "chit":
                g["neg_off"] += bool(o); g["neg"] += bool(a); continue
            ho, h = bool(set(o[:5]) & gold), bool(set(a[:5]) & gold)
            g["n"] += 1; g["h_off"] += ho; g["h"] += h; g["b"] += h and not ho; g["c"] += ho and not h
            g["conf_off"] += bool(set(o[:5]) & conf); g["conf"] += bool(set(a[:5]) & conf)
            g["l5"] += len((set(o[:5]) & gold) - set(a[:5]))
    pts = 100 * (g["h"] - g["h_off"]) / g["n"]; p = mcnemar(g["b"], g["c"])
    guard = g["conf"] <= g["conf_off"] and g["neg"] <= g["neg_off"]
    A = guard and pts >= 5 and p < 0.05; B = guard and g["l5"] == 0 and g["conf"] < g["conf_off"]
    return (f"hit5 {g['h_off']}->{g['h']}/{g['n']} ({pts:+.1f} pts, b={g['b']} c={g['c']}, p={p:.3f}) "
            f"confused {g['conf_off']}->{g['conf']} neg {g['neg_off']}->{g['neg']} l5={g['l5']} | A {'PASS' if A else 'no'}, B {'PASS' if B else 'no'}")

def veto_view(view):
    """The veto on the base block alone, with a chosen vector text: the closest offline analog of upstream's shape."""
    def rule(fx, i):
        base = d.base(fx, i); c = fx.cos(i, view)
        if c is None or not base:
            return base
        cos = {f: float(c[fx.pos[f]]) for f in base}; top = max(cos.values()); r1 = fx.q[i]["fresh"][:1]
        return [f for f in base if cos[f] >= fr.FLOOR and (top - cos[f] <= fr.GAP or f in r1)]
    return rule

if __name__ == "__main__":
    import sys
    dev_dir, test_dir = sys.argv[1:3]  # recall_dump.py output: dev (household) and test (contrast, multi)
    test = [fx for fx in d.load(test_dir) if not fx.name.startswith("two_topics")]
    hh = [fx for fx in d.load(dev_dir) if fx.name.startswith("household")]
    print("[daily shape] contrast+multi, P1 vs daily:", gate(test, fr.RULES["P1"]))
    print("[daily shape] contrast+multi, P2 vs daily:", gate(test, fr.RULES["P2"]))
    print("[daily shape] household test split, P1:  ", gate(hh, fr.RULES["P1"], split="test"))
    print("[daily shape] household dev split, P1:   ", gate(hh, fr.RULES["P1"], split="dev"))
    for view in ("daily", "content"):
        print(f"[base only, veto on {view} vectors] contrast+multi:", gate(test, veto_view(view), ref=d.base))
        print(f"[base only, veto on {view} vectors] household test:", gate(hh, veto_view(view), ref=d.base, split="test"))
    for name, fxs in (("test", d.load(test_dir)), ("dev", d.load(dev_dir))):
        for view in ("daily", "content"):
            r = d.evaluate(fxs, veto_view(view), ref=d.base)["ALL"]
            print(f"{name} base-only veto on {view:7s}: lost targets {r['lost_targets']}, removed non-targets {r['removed_other']}")
