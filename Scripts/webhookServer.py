from flask import Flask, request, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import os

app = Flask(__name__)
auth = HTTPBasicAuth()

# Change these
USERNAME = "max"
PASSWORD_HASH = generate_password_hash("KeepMoVing4WARD!")

users = {USERNAME: PASSWORD_HASH}


@auth.verify_password
def verifyPassword(username, password):
    if username in users and check_password_hash(users[username], password):
        return username


@app.route("/webhook", methods=["POST"])
@auth.login_required
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "No JSON payload"}), 400

    action = data.get("action")

    if action == "captureTask":
        task = data.get("task", "").strip()
        due = data.get("due", "skip").strip() or "skip"
        priority = data.get("priority", "skip").strip() or "skip"

        if not task:
            return jsonify({"ok": False, "error": "No task text provided"}), 400

        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        env["XAUTHORITY"] = "/home/max/.Xauthority"
        env["HOME"] = "/home/max"
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"

        result = subprocess.run(
            ["/home/max/Scripts/captureTaskRemote.sh", task, due, priority],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )

        if result.returncode == 0:
            return jsonify({"ok": True, "action": action, "task": task})
        else:
            return jsonify({"ok": False, "error": result.stderr}), 500
    else:
        return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400
