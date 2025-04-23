from flask import Flask, render_template, request, redirect, session, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, UTC

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
        c.execute("SELECT room_name, created_by_user FROM rooms")
        rooms = c.fetchall()
    return render_template('index.html', username=session['username'], user_id=session['user_id'], rooms=rooms)






@app.route('/join', methods=['POST'])
def join():
    room = request.form['room']
    user_id = session['user_id']
    new_room_created = False

    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        # check if room exists
        c.execute("SELECT room_id, created_by_user FROM rooms WHERE room_name=?", (room,))
        r = c.fetchone()
        if not r:
            new_room_created = True
            c.execute("INSERT INTO rooms (room_name, created_on, created_by_user) VALUES (?, ?, ?)",
                      (room, datetime.now(UTC), user_id))
            con.commit()
            c.execute("SELECT room_id FROM rooms WHERE room_name=?", (room,))
            r = c.fetchone()
        room_id = r[0]
        c.execute("INSERT OR IGNORE INTO room_members (user_id, room_id) VALUES (?, ?)", (user_id, room_id))
        con.commit()

    # Emit event if the room is newly created
    if new_room_created:
        socketio.emit("room_created", {
            "room": room,
            "creator_id": user_id,
            "creator_name": session['username']
        }, namespace="/", to=None)

    return redirect('/')


@app.route('/delete_room', methods=['POST'])
def delete_room():
    room_name = request.form['room']
    user_id = session['user_id']

    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        # Check if the current user is the creator of the room
        c.execute("SELECT created_by_user FROM rooms WHERE room_name=?", (room_name,))
        creator = c.fetchone()

        if creator and creator[0] == user_id:
            # Delete the room from the database
            c.execute("DELETE FROM rooms WHERE room_name=?", (room_name,))
            c.execute("DELETE FROM room_members WHERE room_id=(SELECT room_id FROM rooms WHERE room_name=?)", (room_name,))
            c.execute("DELETE FROM chats WHERE room_id=(SELECT room_id FROM rooms WHERE room_name=?)", (room_name,))
            con.commit()

            # Emit a socket event to notify all users
            socketio.emit('room_deleted', {'room': room_name}, namespace="/", to=None)

    return redirect('/')


@app.route('/history/<room_name>')
def get_history(room_name):
    messages = []
    with sqlite3.connect(DATABASE) as con:
        c = con.cursor()
        c.execute('''
            SELECT message_text, sent_at, sender_id, users.full_name
            FROM chats
            JOIN users ON chats.sender_id = users.user_id
            WHERE room_id = (SELECT room_id FROM rooms WHERE room_name = ?)
            ORDER BY sent_at ASC
        ''', (room_name,))
        messages = [{"msg": f"{row[3]} ({row[1]}): {row[0]}"} for row in c.fetchall()]
    return {"messages": messages}



@socketio.on('join_room')
def handle_join(data):
    room = data['room']
    username = data['username']
    join_room(room)
    emit('message', {'msg': f"{username} joined {room}!"}, room=room)

@socketio.on('leave_room')
def handle_leave(data):
    room = data['room']
    username = data['username']
    leave_room(room)
    emit('message', {'msg': f"{username} left {room}."}, room=room)


@socketio.on('send_message')
def handle_send(data):
    now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
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

