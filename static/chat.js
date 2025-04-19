let socket = io();
let currentRoom = '';

function sendMessage() {
    const msg = document.getElementById('message').value;
    socket.emit('send_message', { username, room: currentRoom, msg });
    document.getElementById('message').value = '';
}

socket.on('connect', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const room = urlParams.get('room');
    if (room) {
        currentRoom = room;
        socket.emit('join_room', { username, room });
    }
});

socket.on('message', data => {
    const box = document.getElementById('messages');
    box.innerHTML += `<p>${data.msg}</p>`;
    box.scrollTop = box.scrollHeight;
});
