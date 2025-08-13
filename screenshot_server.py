# screenshot_server.py  (HOST)
# Listens on 0.0.0.0:5001, accepts many connections, each sends 1 protobuf Screenshot.
# Saves into runs/screens/<run_id>/ and updates latest.json + current_run.txt.
# Also runs a tiny VM control bridge so the Pi can reach the VM via the host.

import socket
import time
import json
from pathlib import Path
from datetime import datetime
from screenshot_pb2 import Screenshot
import threading
import os

HOST = "0.0.0.0"
PORT = 5001

# Base: $SKADVAZ_ROOT or default to ~/skadvaz
BASE = Path(os.environ.get("SKADVAZ_ROOT", str(Path.home() / "skadvaz")))
ROOT = BASE / "runs" / "screens"

# VM control (where pngsend.py listens)
VM_IP = "192.168.122.4"     # <-- your VM's IP
VM_CTRL_PORT = 5002         # <-- pngsend.py control port

# Host bridge endpoint (what the Pi will call)
BRIDGE_LISTEN_HOST = "0.0.0.0"
BRIDGE_LISTEN_PORT = 5006   # <-- Pi will send mute/unmute here


# ---- host logging helper -----------------------------------------------------
def host_log(run_dir: Path, message: str):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {message}"
    print(f"[HOST] {line}")
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[HOST] warn: could not write events.log: {e}")


# ---- tiny TCP bridge: Pi -> (host) -> VM pngsend.py --------------------------
def start_vm_ctl_bridge(
    listen_host: str,
    listen_port: int,
    vm_ip: str,
    vm_port: int,
    run_dir: Path,
):
    """
    Lightweight TCP bridge: Pi -> (host:listen_port) -> VM:vm_port.
    Forwards one newline-terminated JSON line and returns the VM's reply (if any).
    Logs each forwarded command into runs/screens/<run_id>/events.log.
    """

    def handle_client(conn: socket.socket, vm_ip=vm_ip, vm_port=vm_port, run_dir=run_dir):
        with conn:
            try:
                data = b""
                # Read until newline or 4 KiB
                while b"\n" not in data and len(data) < 4096:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    return

                # Log what we got from the Pi
                try:
                    obj = json.loads(data.decode("utf-8").strip())
                    host_log(run_dir, f"vm_ctl forward {obj}")
                except Exception:
                    host_log(run_dir, f"vm_ctl forward raw={data[:80]!r}")

                # Forward to VM control port
                with socket.create_connection((vm_ip, vm_port), timeout=2.0) as upstream:
                    upstream.sendall(data)
                    # Try to read a small reply (e.g., "ok\n"); it's fine if there's none
                    upstream.settimeout(2.0)
                    try:
                        reply = upstream.recv(1024)
                    except socket.timeout:
                        reply = b""
                # Send reply back to Pi
                conn.sendall(reply)
            except Exception as e:
                try:
                    conn.sendall(f"error: {e}\n".encode())
                except Exception:
                    pass

    def server(run_dir=run_dir):
        addr = (listen_host, listen_port)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(addr)
        srv.listen(5)
        print(f"[HOST] VM_CTL bridge listening on {listen_host}:{listen_port} -> {vm_ip}:{vm_port}")
        while True:
            conn, _peer = srv.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

    threading.Thread(target=server, daemon=True).start()


# ---- screenshot server helpers ----------------------------------------------
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

def save_and_update(run_dir: Path, msg: Screenshot, meta: dict | None = None):
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    ms_timestamp = msg.timestamp if msg.timestamp else int(time.time() * 1000)

    fname_img = f"shot_{ts_str}_{ms_timestamp % 1000:03d}.png"
    out_img = run_dir / fname_img
    out_img.write_bytes(msg.image_data)

    ui_rel = None
    if getattr(msg, "ui_json", None) and len(msg.ui_json) > 0:
        fname_ui = f"shot_{ts_str}_{ms_timestamp % 1000:03d}.json"
        out_ui = run_dir / fname_ui
        out_ui.write_bytes(msg.ui_json)
        ui_rel = fname_ui

    latest = {
        "latest_index": fname_img,
        "image_path": fname_img,
        "path": fname_img,
        "ui_json_path": ui_rel
    }
    (run_dir / "latest.json").write_text(json.dumps(latest))

    # Log exactly what we created, plus meta if any
    ev = meta or {}
    host_log(
        run_dir,
        f"created image={fname_img}"
        + (f" ui_json={ui_rel}" if ui_rel else "")
        + (f" vm_event={ev.get('vm_event')} hash={ev.get('hash')}" if ev else "")
    )


# ---- main --------------------------------------------------------------------
def main():
    run_id, run_dir = ensure_run_folder()
    start_vm_ctl_bridge(BRIDGE_LISTEN_HOST, BRIDGE_LISTEN_PORT, VM_IP, VM_CTRL_PORT, run_dir)
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

                    # Safely parse ui_json -> meta (if provided)
                    meta = {}
                    try:
                        if getattr(msg, "ui_json", None) and len(msg.ui_json) > 0:
                            payload = json.loads(msg.ui_json.decode("utf-8"))
                            # Accept either the new envelope {"meta":{...}} or legacy flat
                            meta = payload.get("meta", payload if "vm_event" in payload else {})
                    except Exception:
                        meta = {}

                    save_and_update(run_dir, msg, meta)
                    print(f"[HOST] saved {len(data)} bytes from {addr}")
                except Exception as e:
                    print(f"[HOST] error handling client {addr}: {e}")

if __name__ == "__main__":
    main()
