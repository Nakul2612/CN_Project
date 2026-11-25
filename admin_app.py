from pathlib import Path
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file
)
from werkzeug.utils import secure_filename
import re

app = Flask(__name__)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "server_files"

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# FILE VALIDATION
# --------------------------------------------------

def valid_filename(filename):
    if not isinstance(filename, str):
        return False

    if not filename or filename in {".", ".."}:
        return False

    # Prevent directory traversal
    if "/" in filename or "\\" in filename:
        return False

    # Reject null bytes and control characters
    if any(ord(char) < 32 for char in filename):
        return False

    # Reject Windows-invalid filename characters
    if any(char in '<>:"|?*' for char in filename):
        return False

    # Windows does not allow filenames ending in spaces or dots
    if filename.endswith((" ", ".")):
        return False

    return True


def get_server_files():
    files = []

    for path in UPLOAD_DIR.iterdir():
        if path.is_file() and not path.is_symlink():
            files.append({
                "filename": path.name,
                "size": path.stat().st_size
            })

    return sorted(files, key=lambda item: item["filename"].lower())


# --------------------------------------------------
# DASHBOARD HOME
# --------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("admin.html")


# --------------------------------------------------
# SERVER DASHBOARD STATUS
# --------------------------------------------------

@app.route("/api/status")
def status():
    files = get_server_files()

    total_size = sum(item["size"] for item in files)

    return jsonify({
        "status": "success",
        "dashboard": "online",
        "total_files": len(files),
        "total_storage": total_size,
        "storage_mb": round(total_size / (1024 * 1024), 2)
    })


# --------------------------------------------------
# LIST SERVER FILES
# --------------------------------------------------

@app.route("/api/files")
def list_files():
    return jsonify({
        "status": "success",
        "files": get_server_files()
    })


# --------------------------------------------------
# DOWNLOAD A FILE
# --------------------------------------------------

@app.route("/api/download/<filename>")
def download_file(filename):
    if not valid_filename(filename):
        return jsonify({
            "status": "error",
            "message": "Invalid filename."
        }), 400

    file_path = UPLOAD_DIR / filename

    if not file_path.is_file() or file_path.is_symlink():
        return jsonify({
            "status": "error",
            "message": "File not found."
        }), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename
    )


# --------------------------------------------------
# DELETE A FILE
# --------------------------------------------------

@app.route("/api/delete/<filename>", methods=["POST"])
def delete_file(filename):
    if not valid_filename(filename):
        return jsonify({
            "status": "error",
            "message": "Invalid filename."
        }), 400

    file_path = UPLOAD_DIR / filename

    if not file_path.is_file() or file_path.is_symlink():
        return jsonify({
            "status": "error",
            "message": "File not found."
        }), 404

    try:
        file_path.unlink()

        return jsonify({
            "status": "success",
            "message": f"{filename} deleted successfully."
        })

    except OSError as error:
        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


# --------------------------------------------------
# RUN ADMIN DASHBOARD
# --------------------------------------------------

if __name__ == "__main__":
    print("Secure File Transfer Admin Dashboard")
    print("Open http://127.0.0.1:8001")

    app.run(
        host="127.0.0.1",
        port=8001,
        debug=False,
        threaded=True
    )