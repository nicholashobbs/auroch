import socket
from screenshot_pb2 import Screenshot

def recv_all(sock, size):
    buf = b""
    while len(buf) < size:
        data = sock.recv(size - len(buf))
        if not data:
            raise ConnectionError("Socket closed")
        buf += data
    return buf

def start_server(port=5001):
    with socket.socket() as s:
        s.bind(("0.0.0.0", port))
        s.listen(1)
        print(f"Listening on port {port}...")
        conn, addr = s.accept()
        with conn:
            print(f"Connected from {addr}")
            length = int.from_bytes(recv_all(conn, 4), "big")
            data = recv_all(conn, length)
            msg = Screenshot()
            msg.ParseFromString(data)
            with open(f"recv_{msg.filename}", "wb") as f:
                f.write(msg.image_data)
            print(f"Saved to recv_{msg.filename}")

if __name__ == "__main__":
    start_server()

