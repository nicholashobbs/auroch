# pngsend.py — Change-detect sender with stability-before-send + proper unmute behavior

import os, io, json, time, socket, threading, subprocess
from pathlib import Path
from datetime import datetime

# --- DEPENDENCIES ---
try:
    from PIL import Image
    from screenshot_pb2 import Screenshot
except ImportError as e:
    print(f"FATAL: Missing dependency. pip install pillow protobuf. Error: {e}")
    exit(1)

try:
    from vm_ui_perception import process_screenshot
except ImportError:
    process_screenshot = None

# ---------------- CONFIG ----------------
HOST_IP = "192.168.1.220"
HOST_PORT = 5001
CONTROL_BIND_IP = "0.0.0.0"
CONTROL_BIND_PORT = 5002
CAPTURE_PATH = Path("/tmp/screen.png")

SAMPLE_INTERVAL_SEC = 0.5
ENABLE_PERCEPTION = False

# Stability/quarantine tuning
STABLE_CONSEC = 3            # frames required for stability
STABLE_MIN_MS = 800          # minimum time new state must persist before send
QUARANTINE_MAX_MS = 6000     # post-send quiet window to re-baseline

# ---- SHARED STATE ----
muted_until_ms = 0
capture_now_event = threading.Event()

# Baseline / quarantine
baseline_hash = None
quarantine_until_ms = 0
stable_hash = None
stable_count = 0

# NEW: pre-send candidate tracking (stability-before-send)
candidate_hash = None
candidate_count = 0
candidate_start_ms = 0

# -----------------------------------------------------------------------------

def _recv_line(conn):
    buf = b""
    while True:
        chunk = conn.recv(1024)
        if not chunk:
            break
        buf += chunk
        if b"\n" in chunk:
            break
    return buf.decode("utf-8", errors="replace").strip()

def now_ms():
    return int(time.time() * 1000)

def log(_msg):
    # Intentionally silent to avoid perturbing the VM display
    pass

def capture_screen(out_path: Path):
    try:
        subprocess.run(["gnome-screenshot", "-f", str(out_path)], check=True, capture_output=True)
    except FileNotFoundError:
        # Last message we print; fatal
        print("FATAL: 'gnome-screenshot' not found. Install it or change the capture command.")
        exit(1)
    except subprocess.CalledProcessError as e:
        # Silent error; just raise
        raise RuntimeError(f"screenshot failed: {e.stderr.decode(errors='replace')}")

def dhash(image_bytes: bytes) -> int:
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(im.getdata())
    hb = 0
    for row in range(8):
        for col in range(8):
            idx = row * 9 + col
            hb = (hb << 1) | (1 if pixels[idx] > pixels[idx + 1] else 0)
    return hb

def send_to_host(image_bytes: bytes, event: str):
    ui_graph = {}
    if ENABLE_PERCEPTION and process_screenshot:
        try:
            CAPTURE_PATH.write_bytes(image_bytes)
            ui_graph = process_screenshot(str(CAPTURE_PATH))
        except Exception:
            pass


    try:
        h_hex = f"{dhash(image_bytes):016x}"
    except Exception:
        h_hex = None

    payload = {
        "meta": {"vm_event": event, "hash": h_hex, "ts_ms": now_ms()},
        "graph": ui_graph,
    }

    msg = Screenshot(
        image_data=image_bytes,
        timestamp=now_ms(),
        ui_json=json.dumps(payload).encode("utf-8"),
    )
    data = msg.SerializeToString()
    with socket.create_connection((HOST_IP, HOST_PORT), timeout=5) as s:
        s.sendall(len(data).to_bytes(4, "big"))
        s.sendall(data)

# ---- CONTROL LISTENER (mute/unmute/capture_now) ----
def control_listener_thread():
    global muted_until_ms, quarantine_until_ms, stable_hash, stable_count
    global candidate_hash, candidate_count, candidate_start_ms
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((CONTROL_BIND_IP, CONTROL_BIND_PORT))
            s.listen(5)
            print(f"[{datetime.now().isoformat()}] [VM-CTL] Listening on {CONTROL_BIND_IP}:{CONTROL_BIND_PORT}")
            while True:
                conn, _ = s.accept()
                with conn:
                    try:
                        line = _recv_line(conn)
                        if not line:
                            conn.sendall(b"ok\n"); continue
                        obj = json.loads(line)
                        cmd = str(obj.get("cmd", "")).lower()

                        if cmd == "mute":
                            ttl = int(obj.get("ttl_ms", 120_000))
                            muted_until_ms = now_ms() + ttl
                            # Clear any in-flight tracking
                            quarantine_until_ms = 0
                            stable_hash = None; stable_count = 0
                            candidate_hash = None; candidate_count = 0; candidate_start_ms = 0
                            conn.sendall(b"ok\n"); continue

                        if cmd == "unmute":
                            # IMPORTANT: keep baseline_hash as-is so we can detect change vs. pre-mute snapshot
                            muted_until_ms = 0
                            quarantine_until_ms = 0
                            stable_hash = None; stable_count = 0
                            candidate_hash = None; candidate_count = 0; candidate_start_ms = 0
                            conn.sendall(b"ok\n"); continue

                        if cmd == "capture_now":
                            capture_now_event.set()
                            conn.sendall(b"ok\n"); continue

                        conn.sendall(b"ok\n")
                    except Exception:
                        try: conn.sendall(b"ok\n")
                        except: pass
    except Exception as e:
        print(f"[VM-CTL] FATAL: control listener failed: {e} (continuing without UI control)")

# ---- MAIN LOOP ----
def main():
    threading.Thread(target=control_listener_thread, daemon=True).start()

    global baseline_hash, quarantine_until_ms, stable_hash, stable_count
    global candidate_hash, candidate_count, candidate_start_ms
    global muted_until_ms

    muted_until_ms = now_ms() +31_536_000_000

    while True:
        try:
            # Highest priority: manual capture
            if capture_now_event.is_set():
                capture_now_event.clear()
                capture_screen(CAPTURE_PATH)
                img_bytes = CAPTURE_PATH.read_bytes()
                send_to_host(img_bytes, "manual_capture")
                # Adopt as baseline to prevent churn
                baseline_hash = dhash(img_bytes)
                quarantine_until_ms = 0
                stable_hash = None; stable_count = 0
                candidate_hash = None; candidate_count = 0; candidate_start_ms = 0
                time.sleep(SAMPLE_INTERVAL_SEC); continue

            now = now_ms()

            # Muted: do nothing
            if now < muted_until_ms:
                time.sleep(0.2); continue

            # Post-send quarantine: silently seek a stable baseline
            if quarantine_until_ms > now:
                capture_screen(CAPTURE_PATH)
                h = dhash(CAPTURE_PATH.read_bytes())
                if stable_hash is None or h != stable_hash:
                    stable_hash = h; stable_count = 1
                else:
                    stable_count += 1
                if stable_count >= STABLE_CONSEC:
                    baseline_hash = stable_hash
                    quarantine_until_ms = 0
                    stable_hash = None; stable_count = 0
                time.sleep(SAMPLE_INTERVAL_SEC); continue

            # Quarantine timed out: adopt last candidate if any
            if quarantine_until_ms != 0 and quarantine_until_ms <= now:
                baseline_hash = stable_hash
                quarantine_until_ms = 0
                stable_hash = None; stable_count = 0
                time.sleep(SAMPLE_INTERVAL_SEC); continue

            # Normal change-detect polling
            capture_screen(CAPTURE_PATH)
            img_bytes = CAPTURE_PATH.read_bytes()
            h = dhash(img_bytes)

            # First boot baseline
            if baseline_hash is None:
                baseline_hash = h
                time.sleep(SAMPLE_INTERVAL_SEC); continue

            if h == baseline_hash:
                # No change: reset candidate tracking
                candidate_hash = None; candidate_count = 0; candidate_start_ms = 0
                time.sleep(SAMPLE_INTERVAL_SEC); continue

            # h != baseline_hash → track candidate until stable
            if candidate_hash is None or h != candidate_hash:
                candidate_hash = h
                candidate_count = 1
                candidate_start_ms = now
                time.sleep(SAMPLE_INTERVAL_SEC); continue
            else:
                candidate_count += 1
                # Send only once the new state is stable enough
                if candidate_count >= STABLE_CONSEC and (now - candidate_start_ms) >= STABLE_MIN_MS:
                    send_to_host(img_bytes, "change_send")
                    # Enter quarantine to finalize a new baseline after any ripple
                    quarantine_until_ms = now_ms() + QUARANTINE_MAX_MS
                    stable_hash = None; stable_count = 0
                    # Clear candidate tracking
                    candidate_hash = None; candidate_count = 0; candidate_start_ms = 0
                    time.sleep(SAMPLE_INTERVAL_SEC); continue

            time.sleep(SAMPLE_INTERVAL_SEC)

        except KeyboardInterrupt:
            break
        except BaseException:
            # Sleep briefly and keep going on any transient error
            time.sleep(5)

if __name__ == "__main__":
    main()
