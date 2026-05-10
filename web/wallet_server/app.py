"""Wallet Server (Alice + Agent + Issuer) — port 8002.

Holds: sk_I, sk_a, sk_d, sk_agent. Auto-issues mDoc on first run.
Serves Client UI at /, exposes /api/wallet/* and /api/agent/*.
"""
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import json as _json
import requests
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from queue import Empty

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bins  # noqa: E402
import agent_runner  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HOLDER_DIR = DATA / "wallet" / "holder"
DELEGATION_DIR = DATA / "wallet" / "delegation"
TASKS_DIR = DATA / "wallet" / "tasks"
ISSUER_PUBLIC_DIR = DATA / "shared" / "issuer_public"
STATIC_DIR = Path(__file__).resolve().parent / "static"

TRIPGO_BASE = os.environ.get("TRIPGO_BASE", "http://localhost:8003")
PORT = int(os.environ.get("WALLET_PORT", "8002"))

_bootstrap_lock = threading.Lock()


def _holder_present() -> bool:
    return HOLDER_DIR.exists() and (HOLDER_DIR / "device_response.cbor").exists()


def _issuer_public_present() -> bool:
    return ISSUER_PUBLIC_DIR.exists() and (ISSUER_PUBLIC_DIR / "issuer_pkx.txt").exists()


def bootstrap_if_needed():
    """If no mDoc on disk, run issuer once and place artifacts."""
    with _bootstrap_lock:
        if _holder_present() and _issuer_public_present():
            return
        print("[bootstrap] no mDoc found — running Issuer", flush=True)
        with tempfile.TemporaryDirectory(prefix="zkaa_issue_") as tmp:
            tmp_path = Path(tmp)
            bins.issuer_issue(tmp_path, example=3,
                              on_line=lambda l: print(f"  [issuer] {l}", flush=True))
            # move outputs into place
            HOLDER_DIR.parent.mkdir(parents=True, exist_ok=True)
            ISSUER_PUBLIC_DIR.parent.mkdir(parents=True, exist_ok=True)
            if HOLDER_DIR.exists():
                shutil.rmtree(HOLDER_DIR)
            if ISSUER_PUBLIC_DIR.exists():
                shutil.rmtree(ISSUER_PUBLIC_DIR)
            shutil.copytree(tmp_path / "holder", HOLDER_DIR)
            shutil.copytree(tmp_path / "issuer_public", ISSUER_PUBLIC_DIR)
        print(f"[bootstrap] mDoc → {HOLDER_DIR}", flush=True)
        print(f"[bootstrap] issuer_public → {ISSUER_PUBLIC_DIR}", flush=True)


def _read_supported_claims() -> list[str]:
    if not _issuer_public_present():
        return []
    n_file = ISSUER_PUBLIC_DIR / "supported_claims_count.txt"
    if not n_file.exists():
        return []
    n = int(n_file.read_text().strip())
    return [(ISSUER_PUBLIC_DIR / f"supported_claim_{i}.txt").read_text().strip()
            for i in range(n)]


def _read_holder_claims() -> list[str]:
    if not _holder_present():
        return []
    n_file = HOLDER_DIR / "claims_count.txt"
    if not n_file.exists():
        return []
    n = int(n_file.read_text().strip())
    return [(HOLDER_DIR / f"claim_alias_{i}.txt").read_text().strip()
            for i in range(n)]


app = Flask(__name__, static_folder=None)


# ---- static UI ----
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:fname>")
def static_files(fname):
    return send_from_directory(STATIC_DIR, fname)


# ---- API ----
@app.route("/api/wallet/status")
def wallet_status():
    if not _holder_present():
        return jsonify({"has_mdoc": False, "claims": []})
    return jsonify({
        "has_mdoc": True,
        "claims": _read_holder_claims(),
        "supported_claims": _read_supported_claims(),
        "device_pkx": (HOLDER_DIR / "device_pkx.txt").read_text().strip()[:32] + "...",
    })


@app.route("/api/wallet/reissue", methods=["POST"])
def wallet_reissue():
    if HOLDER_DIR.exists():
        shutil.rmtree(HOLDER_DIR)
    if ISSUER_PUBLIC_DIR.exists():
        shutil.rmtree(ISSUER_PUBLIC_DIR)
    bootstrap_if_needed()
    return jsonify({"ok": True, "claims": _read_holder_claims()})


@app.route("/api/catalog")
def catalog_proxy():
    try:
        # trust_env=False bypasses HTTP_PROXY/HTTPS_PROXY/ALL_PROXY env vars
        # (e.g., a local Clash proxy on 7890) for localhost cross-service calls.
        s = requests.Session(); s.trust_env = False
        r = s.get(f"{TRIPGO_BASE}/api/catalog", timeout=10)
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except requests.RequestException as e:
        return jsonify({"error": f"TripGo unreachable: {e}"}), 502


@app.route("/api/agent/dispatch", methods=["POST"])
def agent_dispatch():
    body = request.get_json(force=True, silent=True) or {}
    if not _holder_present():
        return jsonify({"error": "no mDoc on wallet — call /api/wallet/reissue first"}), 400
    params = {
        "hotel_id": int(body.get("hotel_id", 0)),
        "checkin": body.get("checkin", "2026-05-10"),
        "checkout": body.get("checkout", "2026-05-12"),
        "claims": body.get("claims") or ["age_over_18"],
        "expires": body.get("expires", "2027-01-01T00:00:00Z"),
        "agent_id": body.get("agent_id", "tripgo-agent"),
    }
    if not params["hotel_id"]:
        return jsonify({"error": "hotel_id required"}), 400
    task = agent_runner.dispatch(
        params=params,
        holder_dir=HOLDER_DIR,
        issuer_public_dir=ISSUER_PUBLIC_DIR,
        tasks_dir=TASKS_DIR,
        tripgo_base=TRIPGO_BASE,
    )
    return jsonify({"task_id": task.id})


@app.route("/api/agent/task/<tid>")
def agent_task(tid):
    task = agent_runner.get_task(tid)
    if not task:
        return jsonify({"error": "not found"}), 404
    return jsonify({**task.to_summary(), "events": task.events})


@app.route("/api/agent/task/<tid>/stream")
def agent_task_stream(tid):
    task = agent_runner.get_task(tid)
    if not task:
        return jsonify({"error": "not found"}), 404
    q = task.subscribe()

    @stream_with_context
    def gen():
        try:
            yield ": stream open\n\n"
            while True:
                try:
                    ev = q.get(timeout=30)
                except Empty:
                    yield ": ping\n\n"
                    continue
                if ev is None:
                    break
                yield f"event: {ev['phase']}\ndata: {_json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev["phase"] in ("done", "failed"):
                    break
        finally:
            task.unsubscribe(q)

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/agent/history")
def agent_history():
    return jsonify(agent_runner.list_tasks(50))


def main():
    DATA.mkdir(exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    bootstrap_if_needed()
    print(f"[wallet] listening on http://localhost:{PORT}", flush=True)
    app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False)


if __name__ == "__main__":
    main()
