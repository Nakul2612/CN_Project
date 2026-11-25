
import socket
import ssl
import json
import struct
import hashlib
import os
import re
from pathlib import Path
import tempfile

HOST = "0.0.0.0"
PORT = 5000

BASE_DIR = Path(__file__).resolve().parent
CERT_FILE = BASE_DIR / "certs" / "server.crt"
KEY_FILE = BASE_DIR / "certs" / "server.key"
UPLOAD_DIR = BASE_DIR / "server_files"

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
CHUNK_SIZE = 64 * 1024              # 64 KB

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def receive_exact(sock, size):
    """Receive exactly the requested number of bytes."""
    data = bytearray()

    while len(data) < size:
        chunk = sock.recv(min(CHUNK_SIZE, size - len(data)))

        if not chunk:
            raise ConnectionError("Connection closed unexpectedly.")

        data.extend(chunk)

    return bytes(data)


def receive_json(sock):
    """Receive a length-prefixed JSON message."""
    header = receive_exact(sock, 4)
    message_size = struct.unpack("!I", header)[0]

    if message_size == 0 or message_size > 65536:
        raise ValueError("Invalid message header.")

    message = receive_exact(sock, message_size)
    return json.loads(message.decode("utf-8"))


def send_json(sock, data):
    """Send a length-prefixed JSON message."""
    message = json.dumps(data).encode("utf-8")
    sock.sendall(struct.pack("!I", len(message)) + message)


def valid_filename(filename):
    """Accept simple filenames only, not directory paths."""
    if not isinstance(filename, str):
        return False

    if filename in ("", ".", ".."):
        return False

    if filename != os.path.basename(filename):
        return False

    if "/" in filename or "\\" in filename:
        return False

    if any(ord(char) < 32 for char in filename):
        return False

    if re.match(r"^[A-Za-z]:", filename):
        return False

    if any(char in '<>:"|?*' for char in filename):
        return False

    if filename.endswith((" ", ".")) or len(filename) > 180:
        return False

    return True


def send_error(conn, message):
    send_json(conn, {
        "status": "error",
        "message": message
    })


def receive_upload(conn, metadata):
    """Receive a file and verify its SHA-256 hash."""
    filename = metadata.get("filename")
    file_size = metadata.get("size")
    expected_hash = metadata.get("sha256")

    if not valid_filename(filename):
        send_error(conn, "Invalid filename.")
        return

    if type(file_size) is not int or not 0 <= file_size <= MAX_FILE_SIZE:
        send_error(conn, "Invalid file size. Maximum allowed size is 100 MB.")
        return

    if (
        not isinstance(expected_hash, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) is None
    ):
        send_error(conn, "Invalid SHA-256 hash.")
        return

    destination = UPLOAD_DIR / filename
    temporary = None

    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=".upload_",
            suffix=".tmp",
            dir=str(UPLOAD_DIR)
        )
        os.close(fd)
        temporary = Path(temporary_name)

        received = 0
        digest = hashlib.sha256()

        with temporary.open("wb") as output:
            while received < file_size:
                amount = min(CHUNK_SIZE, file_size - received)
                chunk = receive_exact(conn, amount)

                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)

                percentage = received * 100 / file_size if file_size else 100
                print(
                    f"\rReceiving {filename}: {percentage:.1f}%",
                    end="",
                    flush=True
                )

        print()

        actual_hash = digest.hexdigest()

        if actual_hash.lower() != expected_hash.lower():
            send_error(conn, "SHA-256 verification failed.")
            return

        os.replace(temporary, destination)
        temporary = None

        print(f"File saved: {destination}")
        print(f"Size: {file_size} bytes")
        print(f"SHA-256: {actual_hash}")

        send_json(conn, {
            "status": "success",
            "message": "File uploaded and verified successfully.",
            "filename": filename,
            "size": file_size,
            "sha256": actual_hash
        })

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def send_download(conn, metadata):
    """Send a requested file to the client."""
    filename = metadata.get("filename")

    if not valid_filename(filename):
        send_error(conn, "Invalid filename.")
        return

    file_path = UPLOAD_DIR / filename

    if not file_path.is_file():
        send_error(conn, "Requested file does not exist on the server.")
        return

    file_size = file_path.stat().st_size

    if file_size > MAX_FILE_SIZE:
        send_error(conn, "File exceeds the 100 MB download limit.")
        return

    # Calculate the SHA-256 hash before sending the file.
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)

    file_hash = digest.hexdigest()

    # Send metadata first, followed by the raw file bytes.
    send_json(conn, {
        "status": "success",
        "message": "Download is ready.",
        "filename": filename,
        "size": file_size,
        "sha256": file_hash
    })

    sent = 0

    with file_path.open("rb") as file:
        while sent < file_size:
            chunk = file.read(min(CHUNK_SIZE, file_size - sent))

            if not chunk:
                raise ConnectionError("File changed or ended unexpectedly.")

            conn.sendall(chunk)
            sent += len(chunk)

            percentage = sent * 100 / file_size if file_size else 100
            print(
                f"\rSending {filename}: {percentage:.1f}%",
                end="",
                flush=True
            )

    print()
    print(f"Download sent: {filename}")
    print(f"Size: {file_size} bytes")
    print(f"SHA-256: {file_hash}")

def list_files(conn):
    """Send the list of available files to the client."""

    try:
        files = []

        for path in UPLOAD_DIR.iterdir():
            if path.is_file() and valid_filename(path.name):
                files.append({
                    "filename": path.name,
                    "size": path.stat().st_size
                })

        files.sort(key=lambda item: item["filename"].lower())

        send_json(conn, {
            "status": "success",
            "message": "File list retrieved successfully.",
            "files": files
        })

        print(f"Sent file listing: {len(files)} files")

    except OSError as error:
        send_error(conn, f"Unable to retrieve file list: {error}")


def handle_request(conn):
    """Read the request and execute the appropriate command."""

    metadata = receive_json(conn)
    command = metadata.get("command")

    if command == "upload":
        receive_upload(conn, metadata)

    elif command == "download":
        send_download(conn, metadata)

    elif command == "list_files":
        list_files(conn)

    else:
        send_error(
            conn,
            "Unsupported command. Use upload, download or list_files."
        )

def main():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    context.load_cert_chain(
        certfile=str(CERT_FILE),
        keyfile=str(KEY_FILE)
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)

        print(f"Secure file server listening on {HOST}:{PORT}")
        print(f"File directory: {UPLOAD_DIR}")

        with context.wrap_socket(server, server_side=True) as secure_server:
            while True:
                try:
                    conn, address = secure_server.accept()

                    with conn:
                        print(f"\nSecure connection from {address}")
                        print(f"TLS version: {conn.version()}")

                        try:
                            handle_request(conn)

                        except (
                            ConnectionError,
                            ValueError,
                            json.JSONDecodeError,
                            OSError,
                            ssl.SSLError
                        ) as error:
                            print(f"Request error: {error}")

                except ssl.SSLError as error:
                    print(f"TLS connection error: {error}")

                except OSError as error:
                    print(f"Network error: {error}")


if __name__ == "__main__":
    main()
