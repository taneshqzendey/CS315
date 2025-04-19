from flask import Flask, render_template, request, redirect, session, url_for
from flask_socketio import SocketIO, join_room, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'
socketio = SocketIO(app)
DATABASE = 'chat.db'

# Create tables if not exist
def init_db():
    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT, hashed_password TEXT,
            contact_number TEXT, role TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS rooms (
            room_id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name TEXT, created_on TEXT, created_by_user INTEGER)''')

        c.execute('''CREATE TABLE IF NOT EXISTS room_members (
            user_id INTEGER, room_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(room_id) REFERENCES rooms(room_id))''')

        c.execute('''CREATE TABLE IF NOT EXISTS chats (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_text TEXT, sent_at TEXT,
            sender_id INTEGER, room_id INTEGER,
            FOREIGN KEY(sender_id) REFERENCES users(user_id),
            FOREIGN KEY(room_id) REFERENCES rooms(room_id))''')
        con.commit()

init_db()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['full_name']
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        with sqlite3.connect(DATABASE) as con:
            c = con.cursor()
            c.execute("INSERT INTO users (full_name, contact_number, hashed_password, role) VALUES (?, ?, ?, ?)",
                      (name, username, hashed_pw, 'user'))
        return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DATABASE) as con:
            c = con.cursor()
            c.execute("SELECT user_id, full_name, hashed_password FROM users WHERE contact_number=?", (username,))
            user = c.fetchone()
            if user and check_password_hash(user[2], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                return redirect('/')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/')
def index():
    if 'username' not in session:
        return redirect('/login')
    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        c.execute("SELECT room_name FROM rooms")
        rooms = [r[0] for r in c.fetchall()]
    return render_template('index.html', username=session['username'], rooms=rooms)



@app.route('/join', methods=['POST'])
def join():
    room = request.form['room']
    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        # check if room exists
        c.execute("SELECT room_id FROM rooms WHERE room_name=?", (room,))
        r = c.fetchone()
        if not r:
            c.execute("INSERT INTO rooms (room_name, created_on, created_by_user) VALUES (?, ?, ?)",
                      (room, datetime.utcnow(), user_id))
            con.commit()
            c.execute("SELECT room_id FROM rooms WHERE room_name=?", (room,))
            r = c.fetchone()
        room_id = r[0]
        c.execute("INSERT OR IGNORE INTO room_members (user_id, room_id) VALUES (?, ?)", (user_id, room_id))
        con.commit()
    return redirect('/')



@socketio.on('join_room')
def handle_join(data):
    join_room(data['room'])
    emit('message', {'msg': f"{data['username']} joined {data['room']}!"}, room=data['room'])


@socketio.on('send_message')
def handle_send(data):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        c.execute("SELECT room_id FROM rooms WHERE room_name=?", (data['room'],))
        room_id = c.fetchone()[0]
        c.execute("INSERT INTO chats (message_text, sent_at, sender_id, room_id) VALUES (?, ?, ?, ?)",
                  (data['msg'], now, session['user_id'], room_id))
        con.commit()
    emit('message', {'msg': f"{data['username']}: {data['msg']}"}, room=data['room'])


if __name__ == '__main__':
    socketio.run(app, debug=True)
