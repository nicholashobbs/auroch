# ~/auroch/test_raw_control.py
import zmq
import sys

PI_IP_ADDRESS = "192.168.1.214"

if len(sys.argv) < 2:
    print('Usage: python3 test_raw_control.py "DEVICE|HEX_STRING"')
    print('Example: python3 test_raw_control.py "MOUSE|01000000"')
    sys.exit(1)

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect(f"tcp://{PI_IP_ADDRESS}:5555")

command = sys.argv[1]
print(f"--> Sending raw command to Pi: '{command}'")
socket.send_string(command)

message = socket.recv_string()
print(f"<-- Received reply: '{message}'")