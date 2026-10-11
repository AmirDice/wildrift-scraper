"""Hold the OCR models in memory and serve crops over a local socket.

PaddleOCR costs roughly 45-75s to become usable: about 30s of imports alone
(paddlex pulls in modelscope, which imports torch), then model construction
and a graph warm-up. That is paid per PROCESS, so a short extraction spends
longer starting up than reading, and a batch of them pays it again every run.

This pays it ONCE and stays resident. Point clients at it with:

    WRTM_OCR_SERVER=127.0.0.1:8765

Unset, or with this not running, every caller behaves exactly as before and
loads the models itself -- src/ocr.py falls back to local on any failure, so
forgetting to start this costs speed and nothing else.

Run (leave it in its own terminal):
    python -m scripts.ocr_server
    python -m scripts.ocr_server --port 8765 --langs en
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _stub_langchain() -> None:
    """Keep paddlex's eager import of langchain from dragging in the world.

    paddlex imports RecursiveCharacterTextSplitter at module scope for its
    RAG retrievers, which pulls langchain -> transformers. Nothing in OCR
    touches it, and paddlex only needs the NAME to exist at import time.
    Measured: 30.9s -> ~12s on the import alone.

    Only installed if the real package has not already been imported, and
    removed again afterwards, so anything later in this process that
    genuinely wants langchain still gets the real one.
    """
    if "langchain_text_splitters" in sys.modules:
        return
    stub = types.ModuleType("langchain_text_splitters")

    class RecursiveCharacterTextSplitter:  # never called; only imported
        def __init__(self, *args, **kwargs):
            raise RuntimeError("stub: paddlex's text splitter is not available")

    stub.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter
    sys.modules["langchain_text_splitters"] = stub


def _unstub_langchain(stubbed: bool) -> None:
    if stubbed and type(sys.modules.get("langchain_text_splitters")) is types.ModuleType:
        mod = sys.modules["langchain_text_splitters"]
        if getattr(mod, "__file__", None) is None:
            del sys.modules["langchain_text_splitters"]


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    chunks = []
    while n > 0:
        part = sock.recv(min(n, 1 << 20))
        if not part:
            raise ConnectionError("client closed the connection")
        chunks.append(part)
        n -= len(part)
    return b"".join(chunks)


def serve(host: str, port: int, ocr, cv2, np) -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR means the OPPOSITE thing on Windows: rather than just
    # allowing a quick rebind after close, it lets a SECOND process bind a
    # port another process is already listening on. Both then accept, and
    # connections land on whichever -- which is exactly what happened here,
    # with a stale server still answering on the old models while a new one
    # looked like it had started fine. On Windows ask for the opposite
    # guarantee; elsewhere keep the usual quick-rebind behaviour.
    if sys.platform == "win32":
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
    except OSError as exc:
        print(f"cannot bind {host}:{port}: {exc}", file=sys.stderr)
        print("another ocr_server may already be running, which is fine -- "
              "point clients at that one.", file=sys.stderr)
        return 2
    srv.listen(8)
    print(f"ready on {host}:{port}")
    print(f"  export WRTM_OCR_SERVER={host}:{port}   (or set it per command)")
    print("  ctrl-c to stop")

    served = 0
    t_start = time.time()
    try:
        while True:
            conn, _addr = srv.accept()
            with conn:
                try:
                    while True:
                        header = conn.recv(8)
                        if not header:
                            break
                        if len(header) < 8:
                            header += _recv_exactly(conn, 8 - len(header))
                        size = struct.unpack("!Q", header)[0]
                        raw = _recv_exactly(conn, size)
                        img = cv2.imdecode(np.frombuffer(raw, np.uint8),
                                           cv2.IMREAD_COLOR)
                        try:
                            if img is None:
                                raise ValueError("undecodable image")
                            # _local, not the dispatcher: the dispatcher would
                            # try to reach a server, which is this process.
                            text, score, words = ocr._run_paddle_local(img)
                            body = {
                                "text": text,
                                "score": score,
                                "words": [w.__dict__ for w in words],
                            }
                        except Exception as exc:  # noqa: BLE001
                            body = {"error": f"{type(exc).__name__}: {exc}"}
                        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
                        conn.sendall(struct.pack("!Q", len(payload)) + payload)
                        served += 1
                        if served % 200 == 0:
                            rate = served / max(1e-9, time.time() - t_start)
                            print(f"  {served} crops served ({rate:.1f}/s)")
                except (ConnectionError, OSError) as exc:
                    print(f"  client dropped: {exc}")
    except KeyboardInterrupt:
        print(f"\nstopping after {served} crops")
    finally:
        srv.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1",
                    help="loopback by default; this speaks an unauthenticated "
                         "protocol and has no business on a real interface")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--langs", default="en",
                    help="PADDLE_LANGS for this server. 'en' reads digits and "
                         "Chinese; add 'korean' only if you are serving the "
                         "leaderboard's player names too.")
    args = ap.parse_args()

    import os
    os.environ["PADDLE_LANGS"] = args.langs
    os.environ.pop("WRTM_OCR_SERVER", None)   # never call ourselves

    print(f"loading OCR models (langs={args.langs}) ...")
    t0 = time.time()
    _stub_langchain()
    stubbed = True
    try:
        import cv2
        import numpy as np
        from src import ocr
    finally:
        _unstub_langchain(stubbed)

    # Warm the graph so the first real client is not the one that pays for it.
    ocr._run_paddle_local(np.full((60, 160, 3), 30, dtype=np.uint8))
    print(f"models ready in {time.time() - t0:.1f}s")

    return serve(args.host, args.port, ocr, cv2, np)


if __name__ == "__main__":
    raise SystemExit(main())
