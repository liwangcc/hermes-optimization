"""A loopback /v1/rerank endpoint over a local Qwen3-Reranker-0.6B, so the upstream probe's
--recall-check-margin can be run without a cloud key.

    python rerank_endpoint.py <model directory> <port>

The score of a document is the model's yes-minus-no logit for "the document alone supplies a concrete answer to
the query" (calib_answerability.AnswerVerifier and its instruction): the logit scale, 0 in the middle. Local files
only. Bound to 127.0.0.1; prints "ready" when the model is loaded.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock


def main():
    model_dir, port = sys.argv[1], int(sys.argv[2])
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    from calib_answerability import INSTRUCTION, AnswerVerifier

    model = AnswerVerifier(model_dir, INSTRUCTION)
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            query, documents = body.get("query"), body.get("documents")
            if not self.path.endswith("/rerank") or not isinstance(query, str) or not isinstance(documents, list):
                self.send_error(400)
                return
            with lock:
                # a pair too long for the model scores -inf there: sent as a plain no, the answer must be finite
                scores = [max(model.score(query, str(d)), -100.0) for d in documents]
            ranked = sorted(enumerate(scores), key=lambda item: -item[1])[:int(body.get("top_n") or len(scores))]
            data = json.dumps({"model": body.get("model"), "results": [
                {"index": i, "relevance_score": s} for i, s in ranked]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print("ready", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
