"""A loopback /v1/embeddings endpoint over a local sentence-transformers model, so the upstream probe
(tools/provenance_probe.py, EMB_URL / EMB_MODEL) can be run without a cloud key.

    python embed_endpoint.py <model directory> <port>

Local files only, fp16 on CUDA, unit vectors. Bound to 127.0.0.1; prints "ready" when the model is loaded.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock


def main():
    model_dir, port = Path(sys.argv[1]).resolve(strict=True), int(sys.argv[2])
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(str(model_dir), device=device, local_files_only=True,
                                model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {})
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            texts = body.get("input", [])
            texts = [texts] if isinstance(texts, str) else list(texts)
            if not self.path.endswith("/embeddings") or not all(isinstance(t, str) for t in texts):
                self.send_error(400)
                return
            with lock:
                vectors = model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
            data = json.dumps({"object": "list", "model": body.get("model") or model_dir.name, "data": [
                {"object": "embedding", "index": i, "embedding": v.astype(float).tolist()}
                for i, v in enumerate(vectors)]}).encode()
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
