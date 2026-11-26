"""One synthetic request to the loopback /v1/rerank of rerank_endpoint.py, its raw response, and the verdict the
plugin's default check (recall_check.cross_encoder) reads from it: yes when the score is above 0 on the logit scale.

    python -X utf8 synthetic_check.py <plugin checkout> <core dir> [endpoint]

The request body is the one rerank.Rescorer.scores sends for a single document with single=True: model, query (the
message), documents (the one fact, as recall shows it), top_n (rerank_top_k, 40 by default). Facts are made up.
"""
import functools
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

plugin, core = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
endpoint = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:12372/v1/rerank"
sys.path.insert(0, str(core))
spec = importlib.util.spec_from_file_location("hermes_plugin_holographic", plugin / "__init__.py",
                                              submodule_search_locations=[str(plugin)])
pkg = importlib.util.module_from_spec(spec)
sys.modules["hermes_plugin_holographic"] = pkg
spec.loader.exec_module(pkg)
from hermes_plugin_holographic import recall_check, rerank  # noqa: E402

MODEL = "Qwen/Qwen3-Reranker-0.6B"
PAIRS = [("Where is the spare key?", "The spare key hangs behind the blue flowerpot on the balcony."),
         ("Where is the spare key?", "The spare bulb lies behind the green bucket in the cellar.")]
check = functools.partial(recall_check.cross_encoder, rerank.Rescorer(rerank.Settings(
    {"rerank_url": endpoint, "rerank_model": MODEL, "rerank_scale": "logit"})))
for message, fact in PAIRS:
    body = {"model": MODEL, "query": message, "documents": [fact], "top_n": rerank.DEFAULT_TOP_K}
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        answer = response.read().decode("utf-8")
    print("request: ", json.dumps(body, ensure_ascii=False))
    print("response:", answer)
    print("recall_check.cross_encoder ->", check(message, fact))
    print()
