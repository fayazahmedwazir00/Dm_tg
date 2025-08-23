from flask import Flask, render_template_string, request, jsonify, redirect
import asyncio
import threading
from telethon import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import FloodWaitError
import sqlite3
from datetime import datetime

# Telegram API credentials
api_id = 12345       # your api_id
api_hash = "your_api_hash"
session_name = "my_session"

# Flask app
app = Flask(__name__)
client = TelegramClient(session_name, api_id, api_hash)

# Status global variable
status = {
    "running": False,
    "sent": 0,
    "skipped": 0,
    "total": 0,
    "current_group": "LetSharePK1100",
    "stop_flag": False
}

# DB init
def init_db():
    conn = sqlite3.connect("sent_users.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS sent_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    last_sent TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY,
                    group_username TEXT)""")
    c.execute("INSERT OR IGNORE INTO settings (id, group_username) VALUES (1, ?)", ("LetSharePK1100",))
    conn.commit()
    conn.close()

def get_group_username():
    conn = sqlite3.connect("sent_users.db")
    c = conn.cursor()
    c.execute("SELECT group_username FROM settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    return row[0]

def set_group_username(new_group):
    conn = sqlite3.connect("sent_users.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET group_username=? WHERE id=1", (new_group,))
    conn.commit()
    conn.close()

async def send_to_all_members():
    global status
    await client.start()
    conn = sqlite3.connect("sent_users.db")
    c = conn.cursor()

    group_username = get_group_username()
    group = await client.get_entity(group_username)
    print(f"Group: {group.title}")

    offset = 0
    limit = 100
    members = []

    while True:
        participants = await client(GetParticipantsRequest(
            channel=group,
            filter=ChannelParticipantsSearch(""),
            offset=offset,
            limit=limit,
            hash=0
        ))
        if not participants.users:
            break
        members.extend(participants.users)
        offset += len(participants.users)

    status["running"] = True
    status["sent"] = 0
    status["skipped"] = 0
    status["total"] = len(members)
    status["current_group"] = group_username
    status["stop_flag"] = False

    for member in members:
        if status["stop_flag"]:  # Stop button pressed
            break

        if member.username:
            c.execute("SELECT last_sent FROM sent_users WHERE user_id = ?", (member.id,))
            row = c.fetchone()
            if not row:
                try:
                    msg = f"""
🔥 سلام @{member.username}  

📝📝📝 
"""
                    await client.send_message(member.username, msg)
                    c.execute("INSERT OR REPLACE INTO sent_users (user_id, username, last_sent) VALUES (?, ?, ?)",
                              (member.id, member.username, datetime.now().isoformat()))
                    conn.commit()
                    status["sent"] += 1
                    await asyncio.sleep(30)
                except FloodWaitError as e:
                    print(f"FloodWaitError: waiting {e.seconds}")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"Error {member.username}: {e}")
                    status["skipped"] += 1
                    await asyncio.sleep(5)
            else:
                status["skipped"] += 1
        else:
            status["skipped"] += 1

    conn.close()
    status["running"] = False

def run_campaign():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_to_all_members())

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        if "start" in request.form and not status["running"]:
            t = threading.Thread(target=run_campaign)
            t.start()
            return redirect("/")
        elif "stop" in request.form:
            status["stop_flag"] = True
            return redirect("/")
        elif "group" in request.form:
            set_group_username(request.form["group"].strip("@"))
            return redirect("/")
    current_group = get_group_username()
    return render_template_string(f"""
        <h2>📢 Current Group: @{current_group}</h2>
        <form method="POST">
            <button type="submit" name="start" {'disabled' if status['running'] else ''}>🚀 Start DM Campaign</button>
            <button type="submit" name="stop" {'disabled' if not status['running'] else ''}>🛑 Stop Campaign</button>
        </form>
        <br>
        <form method="POST">
            <input type="text" name="group" placeholder="New Group Username" required>
            <button type="submit">🔄 Change Group</button>
        </form>
        <br>
        <a href="/history">📜 View DM History</a>
        <br><br>
        <h3>📊 Campaign Status</h3>
        <div id="status">Loading...</div>
        <script>
        async function refreshStatus() {{
            let res = await fetch('/status');
            let data = await res.json();
            document.getElementById("status").innerHTML =
              "Running: " + data.running + "<br>" +
              "Sent: " + data.sent + "<br>" +
              "Skipped: " + data.skipped + "<br>" +
              "Total: " + data.total + "<br>" +
              "Group: @" + data.current_group;
        }}
        setInterval(refreshStatus, 3000);
        refreshStatus();
        </script>
    """)

@app.route("/history")
def history():
    conn = sqlite3.connect("sent_users.db")
    c = conn.cursor()
    c.execute("SELECT username, last_sent FROM sent_users ORDER BY last_sent DESC")
    rows = c.fetchall()
    conn.close()

    table_html = "<table border='1' cellpadding='5'><tr><th>Username</th><th>Last Sent</th></tr>"
    for username, last_sent in rows:
        table_html += f"<tr><td>@{username}</td><td>{last_sent}</td></tr>"
    table_html += "</table>"

    return render_template_string(f"""
        <h2>📜 DM History</h2>
        {table_html}
        <br><a href="/">⬅️ Back to Dashboard</a>
    """)

@app.route("/status")
def get_status():
    return jsonify(status)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)