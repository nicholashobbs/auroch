import zmq
import sys
import time
import json
from handuz import Humanizer

# --- Configuration ---
PI_IP_ADDRESS = "192.168.1.214" 
# Seconds to wait for the VM's screen to stabilize after the wake-up wiggle
WAKE_UP_PAUSE_S = 0.5 

def send_plan_to_pi(socket, plan):
    """Serializes and sends a full action plan to the Pi, and waits for a reply."""
    if not plan:
        return
    plan_json = json.dumps(plan)
    socket.send_string(plan_json)
    reply = socket.recv_string()
    print(f"<-- Received reply from Pi: '{reply}'")

def main(target_x, target_y):
    # --- Connect to the Pi ---
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(f"tcp://{PI_IP_ADDRESS}:5555")
    print(f"--> Connected to Pi at {PI_IP_ADDRESS}.")

    # --- 1. The Wake-Up Routine ---
    print("--> Generating and sending wake-up plan...")
    h = Humanizer()
    h.wake_up_screen()
    send_plan_to_pi(socket, h.action_plan)

    # --- 2. The Pause ---
    print(f"--> Pausing for {WAKE_UP_PAUSE_S}s to let screen stabilize...")
    time.sleep(WAKE_UP_PAUSE_S)

    # --- 3. The Main Movement Plan ---
    print("--> Generating and sending main movement plan...")
    h.clear_plan() # Clear the old plan
    h.move_to(target_x, target_y)
    send_plan_to_pi(socket, h.action_plan)
    
    print("\n✅ All plans sent. TEST COMPLETE.")
    socket.close()
    context.term()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 run_humanizer_test.py <target_x> <target_y>")
        sys.exit(1)
    
    main(int(sys.argv[1]), int(sys.argv[2]))