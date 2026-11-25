import socket
import ssl

HOST = "50.0.5.173"
PORT = 5000

context = ssl.create_default_context(
    cafile="certs/server.crt"
)

with socket.create_connection((HOST, PORT)) as sock:
    with context.wrap_socket(
        sock,
        server_hostname="localhost"
    ) as secure_sock:

        message = secure_sock.recv(1024).decode()

        print("Server message:", message)
        print("TLS version:", secure_sock.version())
        print("Cipher:", secure_sock.cipher()[0])