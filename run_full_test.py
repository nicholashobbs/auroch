# ~/auroch/run_full_test.py
import zmq
import sys
import time
import json
from handuz import Humanizer

PI_IP_ADDRESS = "192.168.1.214" 

def send_plan_to_pi(socket, humanizer, log_file):
    """Generates pi_commands, saves a log, and sends the plan."""
    if not humanizer.action_plan:
        return
    
    # Save the detailed human-readable log for this step
    humanizer.generate_output(format='human', log_file=log_file)
    
    # Send the actual plan to the Pi
    plan_json = json.dumps(humanizer.action_plan)
    socket.send_string(plan_json)
    reply = socket.recv_string()
    print(f"<-- Pi replied: '{reply}'")

def main():
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(f"tcp://{PI_IP_ADDRESS}:5555")
    print(f"--> Connected to Pi.")
    
    h = Humanizer()
    
    # --- The Sequence ---
    print("\nStep 1: Waking up screen...")
    h.wake_up_screen()
    send_plan_to_pi(socket, h, "log_step1_wakeup.txt")
    
    print("\nStep 2: Pausing for 3 seconds...")
    time.sleep(3)

    print("\nStep 3: Moving to (500, 500)...")
    h.clear_plan()
    h.move_to(500, 500)
    send_plan_to_pi(socket, h, "log_step3_move1.txt")
    
    print("\nStep 4: Moving to (5, 5)...")
    h.clear_plan()
    h.move_to(5, 5)
    send_plan_to_pi(socket, h, "log_step4_move2.txt")
    
    print("\nStep 5: Clicking Left Button...")
    h.clear_plan()
    h.click('LEFT')
    send_plan_to_pi(socket, h, "log_step5_click.txt")
    
    # Step 6: Type 'fire' and hit Enter
    print("\nStep 6: Typing 'fire' and hitting Enter...")
    h.clear_plan()
    h.type_text('fire\n')
    send_plan_to_pi(socket, h, "log_step6_type_fire.txt")
    
   # Step 7: Pause for 3 seconds
    print("\nStep 7: Pausing for 3 seconds...")
    start_time = time.time()
    time.sleep(3)
    end_time = time.time()
    print(f"--> Actual pause duration: {end_time - start_time:.2f} seconds.")

    # Step 8: Type 'wikipedia.org/wiki/Nader_Shah' and hit Enter
    print("\nStep 8: Typing 'wikipedia.org/wiki/Nader_Shah' and hitting Enter...")
    h.clear_plan()
    h.type_text('wikipedia.org/wiki/Nader_Shah\n')
    send_plan_to_pi(socket, h, "log_step8_type_wiki.txt")

    # Step 9: Pause for half a second
    print("\nStep 9: Pausing...")
    time.sleep(1.5)

    # Step 10: Move the mouse to (300, 300)
    print("\nStep 10: Moving to (300, 300)...")
    h.clear_plan()
    h.move_to(320, 320)
    send_plan_to_pi(socket, h, "log_step10_move.txt")
    
    # Step 11: Scroll down 20 ticks
    print("\nStep 11: Scrolling down...")
    h.clear_plan()
    print("Sending scroll 20")
    h.scroll(-20) # NEGATIVE value for scroll down
    send_plan_to_pi(socket, h, "log_step11_scroll.txt")
    print("\n✅ Sequence complete.")
    socket.close()
    context.term()

if __name__ == "__main__":
    main()