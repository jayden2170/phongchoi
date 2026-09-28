import random
import string
import time

from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room


app = Flask(__name__)

app.config["SECRET_KEY"] = "phong-choi-secret"

socketio = SocketIO(
    app,
    cors_allowed_origins="*"
)


# =========================================================
# DỮ LIỆU GAME
# =========================================================

QUESTION_TIME = 15

QUESTIONS = [
    {
        "question": "Thủ đô của Việt Nam là gì?",
        "options": [
            "Hà Nội",
            "Đà Nẵng",
            "Huế",
            "Cần Thơ"
        ],
        "answer": 0
    },

    {
        "question": "2 + 3 bằng bao nhiêu?",
        "options": [
            "4",
            "5",
            "6",
            "7"
        ],
        "answer": 1
    },

    {
        "question": "Hành tinh nào được gọi là Hành tinh Đỏ?",
        "options": [
            "Trái Đất",
            "Sao Kim",
            "Sao Hỏa",
            "Sao Mộc"
        ],
        "answer": 2
    },

    {
        "question": "Nước có công thức hóa học là gì?",
        "options": [
            "CO2",
            "O2",
            "H2O",
            "NaCl"
        ],
        "answer": 2
    },

    {
        "question": "Một năm có bao nhiêu tháng?",
        "options": [
            "10",
            "11",
            "12",
            "13"
        ],
        "answer": 2
    }
]


# =========================================================
# DANH SÁCH PHÒNG
# =========================================================

rooms = {}


# =========================================================
# TẠO MÃ PHÒNG
# =========================================================

def generate_room_code():

    while True:

        code = "".join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=6
            )
        )

        if code not in rooms:
            return code


# =========================================================
# LẤY DANH SÁCH NGƯỜI CHƠI
# =========================================================

def shuffle_question(question):
    options = list(enumerate(question["options"]))

    random.shuffle(options)

    new_options = []
    new_answer = 0

    for new_index, (old_index, option) in enumerate(options):
        new_options.append(option)

        if old_index == question["answer"]:
            new_answer = new_index

    return {
        "question": question["question"],
        "options": new_options,
        "answer": new_answer
    }
def get_players(room):
    players = []

    for sid, player in room["players"].items():

        players.append({
            "name": player["name"],
            "score": player["score"],
            "host": sid == room["host_sid"]
        })

    players.sort(
        key=lambda player: player["score"],
        reverse=True
    )

    return players


# =========================================================
# GỬI THÔNG TIN PHÒNG
# =========================================================

def update_room(room_code):

    if room_code not in rooms:
        return

    room = rooms[room_code]

    socketio.emit(
        "room_update",
        {
            "players": get_players(room),
            "host_sid": room["host_sid"],
            "state": room["state"]
        },
        to=room_code
    )


# =========================================================
# TRANG CHỦ
# =========================================================

@app.route("/")
def index():

    return render_template("index.html")


# =========================================================
# TẠO PHÒNG
# =========================================================

@app.route("/create", methods=["POST"])
def create_room():
    name = request.form.get("name", "").strip()

    if not name:
        return redirect(url_for("index"))

    code = generate_room_code()

    rooms[code] = {
        "host_sid": None,
        "players": {},
        "state": "waiting",
        "question_index": 0,
        "round_id": 0,
        "started_at": 0,

        # Trộn thứ tự câu hỏi cho phòng
        "questions": random.sample(
            QUESTIONS,
            len(QUESTIONS)
        ),

        # Câu hỏi hiện tại sau khi đảo đáp án
        "current_question": None
    }

    return redirect(
        url_for(
            "room",
            code=code,
            name=name
        )
    )
@app.route("/join", methods=["POST"])
def join_room_page():

    name = request.form.get("name", "").strip()

    code = request.form.get("code", "").strip().upper()

    if not name or not code:

        return redirect(url_for("index"))

    if code not in rooms:

        return "Phòng không tồn tại."

    if rooms[code]["state"] != "waiting":

        return "Game đã bắt đầu."

    return redirect(
        url_for(
            "room",
            code=code,
            name=name
        )
    )


# =========================================================
# TRANG PHÒNG
# =========================================================

@app.route("/room/<code>")
def room(code):

    code = code.upper()

    if code not in rooms:

        return "Phòng không tồn tại."

    name = request.args.get("name", "").strip()

    return render_template(
        "room.html",
        code=code,
        player_name=name
    )


# =========================================================
# NGƯỜI CHƠI THAM GIA SOCKET
# =========================================================

@socketio.on("join_room")
def handle_join(data):

    code = data.get("code", "").upper().strip()

    name = data.get("name", "").strip()

    if code not in rooms:

        emit(
            "error_message",
            {
                "message": "Phòng không tồn tại."
            }
        )

        return

    room = rooms[code]

    if room["state"] != "waiting":

        emit(
            "error_message",
            {
                "message": "Game đã bắt đầu."
            }
        )

        return

    # Kiểm tra tên trùng

    for player in room["players"].values():

        if player["name"].lower() == name.lower():

            emit(
                "error_message",
                {
                    "message": "Tên này đã có người sử dụng."
                }
            )

            return

    join_room(code)

    room["players"][request.sid] = {

        "name": name,

        "score": 0,

        "answered": False

    }

    # Người đầu tiên là chủ phòng

    if room["host_sid"] is None:

        room["host_sid"] = request.sid

    update_room(code)


# =========================================================
# BẮT ĐẦU GAME
# =========================================================

@socketio.on("start_game")
def start_game(data):

    code = data.get("code", "").upper()

    if code not in rooms:

        return

    room = rooms[code]

    # Chỉ chủ phòng mới được bắt đầu

    if request.sid != room["host_sid"]:

        emit(
            "error_message",
            {
                "message": "Chỉ chủ phòng mới có thể bắt đầu game."
            }
        )

        return

    if len(room["players"]) == 0:

        return

    room["state"] = "playing"

    room["question_index"] = 0

    room["round_id"] += 1

    for player in room["players"].values():

        player["score"] = 0

        player["answered"] = False

    send_question(code)


# =========================================================
# GỬI CÂU HỎI
# =========================================================

def send_question(code):
    if code not in rooms:
        return

    room = rooms[code]

    question = room["questions"][room["question_index"]]

    shuffled_question = shuffle_question(question)

    room["current_question"] = shuffled_question

    room["started_at"] = time.monotonic()

    for player in room["players"].values():
        player["answered"] = False

    socketio.emit(
        "game_question",
        {
            "question": shuffled_question["question"],
            "options": shuffled_question["options"],
            "time": QUESTION_TIME,
            "question_number": room["question_index"] + 1,
            "total_questions": len(room["questions"]),
            "round_id": room["round_id"]
        },
        to=code
    )

    socketio.start_background_task(
        question_timer,
        code,
        room["round_id"]
    )
@socketio.on("answer")
def answer_question(data):
    code = data.get("code", "").upper()
    answer = data.get("answer")

    if code not in rooms:
        return

    room = rooms[code]

    if room["state"] != "playing":
        return

    if request.sid not in room["players"]:
        return

    player = room["players"][request.sid]

    if player["answered"]:
        return

    try:
        answer = int(answer)
    except:
        return

    question = room["current_question"]

    player["answered"] = True

    elapsed = time.monotonic() - room["started_at"]

    remaining = max(
        0,
        QUESTION_TIME - elapsed
    )

    correct = answer == question["answer"]

    points = 0

    if correct:
        points = 100 + int(
            900 * remaining / QUESTION_TIME
        )

        player["score"] += points

    emit(
        "answer_received",
        {
            "correct": correct,
            "points": points
        }
    )

    all_answered = all(
        player["answered"]
        for player in room["players"].values()
    )

    if all_answered:
        finish_round(code)
def finish_round(code):
    if code not in rooms:
        return

    room = rooms[code]

    if room["state"] != "playing":
        return

    room["state"] = "results"

    question = room["current_question"]

    socketio.emit(
        "round_result",
        {
            "correct": question["answer"],
            "players": get_players(room)
        },
        to=code
    )

    current_round = room["round_id"]

    socketio.start_background_task(
        next_round,
        code,
        current_round
    )
def next_round(code, round_id):

    socketio.sleep(3)

    if code not in rooms:

        return

    room = rooms[code]

    if room["round_id"] != round_id:

        return

    if room["state"] != "results":

        return

    # Hết câu hỏi

    if room["question_index"] + 1 >= len(QUESTIONS):

        room["state"] = "finished"

        socketio.emit(
            "game_over",
            {
                "players": get_players(room)
            },
            to=code
        )

        return

    # Câu tiếp theo

    room["question_index"] += 1

    room["round_id"] += 1

    room["state"] = "playing"

    send_question(code)


# =========================================================
# CHAT
# =========================================================

@socketio.on("chat_message")
def chat_message(data):

    code = data.get("code", "").upper()

    message = data.get("message", "").strip()

    if code not in rooms:

        return

    if not message:

        return

    if request.sid not in rooms[code]["players"]:

        return

    name = rooms[code]["players"][
        request.sid
    ]["name"]

    socketio.emit(
        "chat_message",
        {
            "name": name,
            "message": message
        },
        to=code
    )


# =========================================================
# CHƠI LẠI
# =========================================================

@socketio.on("restart_game")
def restart_game(data):
    code = data.get("code", "").upper()

    if code not in rooms:
        return

    room = rooms[code]

    if request.sid != room["host_sid"]:
        return

    room["state"] = "waiting"

    room["question_index"] = 0

    room["questions"] = random.sample(
        QUESTIONS,
        len(QUESTIONS)
    )

    room["current_question"] = None

    room["round_id"] += 1

    for player in room["players"].values():
        player["score"] = 0
        player["answered"] = False

    update_room(code)
@socketio.on("disconnect")
def disconnect():

    for code, room in list(rooms.items()):

        if request.sid not in room["players"]:

            continue

        was_host = request.sid == room["host_sid"]

        del room["players"][request.sid]

        leave_room(code)

        if len(room["players"]) == 0:

            del rooms[code]

            return

        # Nếu chủ phòng thoát

        if was_host:

            room["host_sid"] = next(
                iter(room["players"])
            )

        update_room(code)

        return


# =========================================================
# CHẠY SERVER
# =========================================================

if __name__ == "__main__":
    socketio.run(app)