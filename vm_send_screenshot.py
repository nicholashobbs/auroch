# ~/auroch/vm_send_screenshot.py
# Stability-aware sender with control server (MUTE ON/OFF).
# Requires: Pillow (pip install pillow), gnome-screenshot

import socket
import time
import subprocess
import threading
from collections import deque
from pathlib import Path
import io
import json

from PIL import Image  # pip install pillow
from screenshot_pb2 import Screenshot

# ------------ CONFIG (adjust HOST_IP) ------------
HOST_IP = "192.168.1.220"   # the host running screenshot_server.py
PORT    = 5001              # screenshot server port

CAPTURE_PATH = Path("/tmp/screen.png")

SAMPLE_INTERVAL_SEC = 0.35
STABLE_WINDOW_MS    = 1000
HAMMING_MAX         = 4
MIN_PUBLISH_MS      = 500

# Control server (listen here for Pi commands)
CTRL_HOST = "0.0.0.0"
CTRL_PORT = 5002
# -------------------------------------------------

STATE_MUTED = "MUTED"
STATE_AWAIT = "AWAITING_FIRST_STABLE"
STATE_HOLD  = "HOLD"

class ReflexState:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = STATE_MUTED
        self.last_published_hash = None
        self.last_publish_ms = 0

    def set_muted(self, muted: bool):
        with self.lock:
            if muted:
                self.state = STATE_MUTED
            else:
                self.state = STATE_AWAIT

    def mark_published(self, h, ts_ms):
        with self.lock:
            self.last_published_hash = h
            self.last_publish_ms = ts_ms
            self.state = STATE_HOLD

    def get(self):
        with self.lock:
            return self.state, self.last_published_hash, self.last_publish_ms

def capture_screen(out_path=CAPTURE_PATH):
    subprocess.run(["gnome-screenshot", "-f", str(out_path)], check=True)
    return out_path

def dhash_bytes(img_bytes):
    with Image.open(io.BytesIO(img_bytes)) as im:
        im = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pix = list(im.getdata())
    rows = [pix[i*9:(i+1)*9] for i in range(8)]
    bits = 0
    for r in rows:
        for x in range(8):
            bits <<= 1
            bits |= 1 if r[x] > r[x+1] else 0
    return bits

def hamming64(a, b):
    return (a ^ b).bit_count()

def send_to_host(image_bytes):
    msg = Screenshot(
        filename="screen.png",
        image_data=image_bytes,
        timestamp=int(time.time() * 1000),
    )
    data = msg.SerializeToString()
    with socket.create_connection((HOST_IP, PORT), timeout=5) as s:
        s.sendall(len(data).to_bytes(4, "big"))
        s.sendall(data)

def control_server_thread(reflex: ReflexState):
    """
    Tiny TCP server for commands: {"cmd":"MUTE","value":"ON"|"OFF"}
    """
    with socket.socket() as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((CTRL_HOST, CTRL_PORT))
        srv.listen(5)
        print(f"[VM] Control server on {CTRL_HOST}:{CTRL_PORT}")

        while True:
            conn, addr = srv.accept()
            with conn:
                try:
                    # simple len-prefixed JSON
                    l = int.from_bytes(conn.recv(4), "big")
                    payload = conn.recv(l)
                    obj = json.loads(payload.decode("utf-8"))
                    if obj.get("cmd") == "MUTE":
                        val = (obj.get("value") or "").upper()
                        if val == "ON":
                            reflex.set_muted(True)
                            print("[VM] MUTE -> ON")
                        elif val == "OFF":
                            reflex.set_muted(False)
                            print("[VM] MUTE -> OFF (awaiting stable)")
                except Exception as e:
                    print(f"[VM] control error: {e}")

def main():
    print("[VM] Stability loop starting…")
    reflex = ReflexState()

    # Start control server
    t = threading.Thread(target=control_server_thread, args=(reflex,), daemon=True)
    t.start()

    history = deque()  # {"ts_ms": int, "hash": int}

    while True:
        t0 = time.time()
        now_ms = int(t0 * 1000)

        # Capture
        try:
            capture_screen(CAPTURE_PATH)
            img_bytes = CAPTURE_PATH.read_bytes()
        except Exception as e:
            time.sleep(SAMPLE_INTERVAL_SEC); continue

        # Hash
        try:
            dh = dhash_bytes(img_bytes)
        except Exception:
            time.sleep(SAMPLE_INTERVAL_SEC); continue

        # Stability window
        history.append({"ts_ms": now_ms, "hash": dh})
        while history and (now_ms - history[0]["ts_ms"] > STABLE_WINDOW_MS):
            history.popleft()

        # Check stability
        stable = False
        if len(history) >= 2:
            prev = history[0]["hash"]
            max_adj = 0
            for i in range(1, len(history)):
                d = hamming64(prev, history[i]["hash"])
                if d > max_adj: max_adj = d
                prev = history[i]["hash"]
            stable = (max_adj <= HAMMING_MAX)

        # Decide publish by state
        state, last_hash, last_pub_ms = reflex.get()
        if state == STATE_MUTED:
            pass  # never publish
        elif state == STATE_HOLD:
            pass  # wait for next OFF
        elif state == STATE_AWAIT:
            min_interval_ok = (now_ms - last_pub_ms) >= MIN_PUBLISH_MS
            content_new = (last_hash is None or hamming64(dh, last_hash) > 0)
            if stable and min_interval_ok and content_new:
                try:
                    send_to_host(img_bytes)
                    reflex.mark_published(dh, now_ms)
                    print("[VM] Published stable frame (one per act).")
                except Exception as e:
                    print(f"[VM] publish error: {e}")

        # Pace loop
        elapsed = time.time() - t0
        time.sleep(max(0.0, SAMPLE_INTERVAL_SEC - elapsed))

if __name__ == "__main__":
    main()
