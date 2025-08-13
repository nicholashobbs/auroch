# vm_send_screenshot.py — Simplified, Robust Sender
# This version prioritizes stability and clear logging.
# It uses a direct "if hash changed, send" logic.

import os
import io
import json
import time
import socket
import threading
import subprocess
from pathlib import Path
from datetime import datetime

# --- DEPENDENCIES ---
# Make sure these are installed: pip install pillow protobuf
try:
    from PIL import Image
    from screenshot_pb2 import Screenshot
except ImportError as e:
    print(f"FATAL: Missing critical dependency. Please run 'pip install pillow protobuf'. Error: {e}")
    exit(1)

# Optional import, the script will work without it.
try:
    from vm_ui_perception import process_screenshot
except ImportError:
    process_screenshot = None

# ---------------- CONFIG ----------------
HOST_IP = "192.168.1.220"  # IP of the machine running the Rust UI
HOST_PORT = 5001
CONTROL_BIND_IP = "0.0.0.0" # Listen on all network interfaces
CONTROL_BIND_PORT = 5002
CAPTURE_PATH = Path("/tmp/screen.png")
SAMPLE_INTERVAL_SEC = 0.5  # Check the screen twice per second
# ---------------------------------------

# ---- SHARED STATE (for communication between threads) ----
muted_until_ms = 0
capture_now_event = threading.Event()

# ---- HELPER FUNCTIONS ----
def now_ms():
    """Returns the current time in milliseconds."""
    return int(time.time() * 1000)

def log(message):
    """Prints a message with a timestamp."""
    print(f"[{datetime.now().isoformat()}] [VM] {message}")

def capture_screen(out_path):
    """Captures the screen. Exits gracefully if screenshot tool is not found."""
    try:
        subprocess.run(["gnome-screenshot", "-f", str(out_path)], check=True, capture_output=True)
    except FileNotFoundError:
        log("FATAL ERROR: 'gnome-screenshot' command not found. Please install it or change the command in the script.")
        exit(1)
    except subprocess.CalledProcessError as e:
        log(f"ERROR: Screenshot command failed: {e.stderr.decode()}")
        raise  # Let the main loop's error handler catch this

def dhash(image_bytes):
    """Calculates a simple perceptual hash of an image."""
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(im.getdata())
    hash_bits = 0
    for row in range(8):
        for col in range(8):
            idx = row * 9 + col
            hash_bits <<= 1
            if pixels[idx] > pixels[idx + 1]:
                hash_bits |= 1
    return hash_bits

def send_to_host(image_bytes):
    """Sends the screenshot to the host UI server."""
    ui_graph = {}
    if process_screenshot:
        try:
            # We need to write the file to disk for the perception module
            CAPTURE_PATH.write_bytes(image_bytes)
            ui_graph = process_screenshot(str(CAPTURE_PATH))
        except Exception as e:
            log(f"Error running perception module: {e}")
            
    msg = Screenshot(
        image_data=image_bytes,
        timestamp=now_ms(),
        ui_json=json.dumps(ui_graph).encode("utf-8")
    )
    data = msg.SerializeToString()
    log(f"Connecting to host {HOST_IP}:{HOST_PORT}...")
    with socket.create_connection((HOST_IP, HOST_PORT), timeout=5) as s:
        s.sendall(len(data).to_bytes(4, "big"))
        s.sendall(data)
    log("Screenshot sent successfully.")

# ---- CONTROL LISTENER (for UI commands) ----
def control_listener_thread():
    log_prefix = f"[{datetime.now().isoformat()}] [VM-CTL]"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((CONTROL_BIND_IP, CONTROL_BIND_PORT))
            s.listen(5)
            print(f"{log_prefix} Listening for UI commands on {CONTROL_BIND_IP}:{CONTROL_BIND_PORT}")
            while True:
                conn, _ = s.accept()
                with conn:
                    global muted_until_ms
                    try:
                        data = conn.recv(1024)
                        if not data: continue
                        obj = json.loads(data.decode().strip())
                        cmd = obj.get("cmd", "").lower()

                        if cmd == "mute":
                            muted_until_ms = now_ms() + int(obj.get("ttl_ms", 120000))
                            print(f"{log_prefix} Mute command received.")
                        elif cmd == "unmute":
                            muted_until_ms = 0
                            print(f"{log_prefix} Unmute command received.")
                        elif cmd == "capture_now":
                            capture_now_event.set()
                            print(f"{log_prefix} Capture Now command received.")
                    except Exception as e:
                        print(f"{log_prefix} Error processing command: {e}")
    except Exception as e:
        print(f"{log_prefix} FATAL ERROR: Control listener failed: {e}. The script will continue without UI control.")

# ---- MAIN SCRIPT ----
def main():
    """The main continuous loop of the script."""
    log("Starting main capture loop.")
    
    # Start the control listener in a background thread
    threading.Thread(target=control_listener_thread, daemon=True).start()

    last_sent_hash = None
    
    while True:
        try:
            # --- 1. CAPTURE AND HASH ---
            capture_screen(CAPTURE_PATH)
            img_bytes = CAPTURE_PATH.read_bytes()
            current_hash = dhash(img_bytes)
            log(f"Screen captured. Hash: {current_hash:016x}")
            
            # --- 2. DECIDE TO PUBLISH ---
            should_publish = False
            reason = ""

            if capture_now_event.is_set():
                should_publish = True
                reason = "Manual 'Capture Now' request"
                capture_now_event.clear()
            elif now_ms() < muted_until_ms:
                reason = "Muted by UI"
            elif current_hash != last_sent_hash:
                should_publish = True
                reason = "New screen content detected"
            else:
                reason = "Screen content unchanged"

            # --- 3. PUBLISH AND UPDATE STATE ---
            log(f"Decision: {reason}. Should publish: {should_publish}")
            if should_publish:
                send_to_host(img_bytes)
                last_sent_hash = current_hash # CRITICAL: Update state only after a successful send

        except KeyboardInterrupt:
            log("Keyboard interrupt received. Exiting.")
            break # Exit the `while True` loop
        except BaseException as e:
            # This catches ALL other errors (network, permissions, etc.)
            # and ensures the loop continues, preventing any crash.
            log(f"An error occurred in the main loop: {type(e).__name__}: {e}")
            log("Restarting loop in 5 seconds...")
            time.sleep(5)
        
        # --- 4. WAIT FOR NEXT CYCLE ---
        time.sleep(SAMPLE_INTERVAL_SEC)

    log("Script has terminated.")

if __name__ == "__main__":
    main()