# screenshot_server.py  (HOST)
# Listens on 0.0.0.0:5001, accepts many connections, each sends 1 protobuf Screenshot.
# Saves into runs/screens/<run_id>/ and updates latest.json + current_run.txt.

import socket
import time
import json
from pathlib import Path
from datetime import datetime
from screenshot_pb2 import Screenshot

HOST = "0.0.0.0"
PORT = 5001

ROOT = Path("runs/screens")

def recv_all(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("client disconnected while reading")
        buf += chunk
    return buf

def ensure_run_folder():
    ROOT.mkdir(parents=True, exist_ok=True)
    cur = ROOT / "current_run.txt"
    if cur.exists():
        run_id = cur.read_text().strip()
        d = ROOT / run_id
        if d.exists():
            return run_id, d
    # else create a new one
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = ROOT / run_id
    d.mkdir(parents=True, exist_ok=True)
    cur.write_text(run_id)
    return run_id, d

def save_and_update(run_dir: Path, msg: Screenshot):
    ts_ms = int(time.time() * 1000)
    # name: shot_<index>_<ts>.png — index is implicit in latest.json; for now, use monotonically increasing filenames
    # If you want an explicit counter, you could read+increment a counter file here.
    fname = f"shot_{ts_ms}.png"
    out_path = run_dir / fname
    out_path.write_bytes(msg.image_data)

    latest = {
        "latest_index": ts_ms,        # simple monotonic index; UI just compares numbers
        "path": str(out_path.resolve())
    }
    (run_dir / "latest.json").write_text(json.dumps(latest))

def main():
    run_id, run_dir = ensure_run_folder()
    print(f"[HOST] Screenshot server listening on {HOST}:{PORT}")
    print(f"[HOST] Current run: {run_id}  -> {run_dir}")

    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)

        while True:
            conn, addr = s.accept()
            with conn:
                try:
                    length = int.from_bytes(recv_all(conn, 4), "big")
                    data = recv_all(conn, length)
                    msg = Screenshot()
                    msg.ParseFromString(data)
                    save_and_update(run_dir, msg)
                    # Optionally ack (not required by VM sender)
                    # conn.sendall(b"OK")
                    print(f"[HOST] saved {len(data)} bytes from {addr}")
                except Exception as e:
                    print(f"[HOST] error handling client {addr}: {e}")

if __name__ == "__main__":
    main()
