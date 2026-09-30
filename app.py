import csv
import io
import random
import string
import time

import requests

from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room


# =========================================================
# CẤU HÌNH
# =========================================================

GOOGLE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTtkFsbrWhZ1JdrwE5x3PzSBk6XLQYKVgQMyb42Rxtg44WeOooq8aQaKU_hA67P-YPFdWbv8Ys6947t/"
    "pub?output=tsv"
)

QUESTION_TIME = 15
# Điểm theo tốc độ:
# - Trả lời gần như ngay lập tức: ~100 điểm
# - Trả lời ở giây thứ 5: ~70 điểm
# - Trả lời ở giây thứ 10: ~40 điểm
# - Trả lời ở giây thứ 15: ~10 điểm
MAX_SPEED_POINTS = 100
MIN_SPEED_POINTS = 10
POINTS_LOSS_PER_SECOND = 6

app = Flask(__name__)
app.config["SECRET_KEY"] = "phong-choi-secret"

socketio = SocketIO(
    app,
    cors_allowed_origins="*"
)


# =========================================================
# CÂU HỎI MẶC ĐỊNH
# Nếu Google Sheets lỗi, game vẫn dùng được 5 câu này.
# =========================================================

DEFAULT_QUESTIONS = [
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
# TRỘN ĐÁP ÁN
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


# =========================================================
# LẤY DANH SÁCH NGƯỜI CHƠI
# =========================================================

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
# ĐỌC CÂU HỎI TỪ GOOGLE SHEETS
# =========================================================

def load_questions_from_google():
    try:
        response = requests.get(
            GOOGLE_SHEET_URL,
            timeout=10
        )
        response.raise_for_status()

        text = response.content.decode("utf-8-sig")

        if not text.strip():
            raise ValueError("Google Sheets trả về dữ liệu rỗng.")

        first_line = text.splitlines()[0]

        if "\t" in first_line:
            delimiter = "\t"
        else:
            delimiter = ","

        print(
            "Ký tự phân cách được phát hiện:",
            repr(delimiter)
        )

        reader = csv.DictReader(
            io.StringIO(text),
            delimiter=delimiter
        )

        print("Tên các cột:", reader.fieldnames)

        required_columns = {
            "question",
            "A",
            "B",
            "C",
            "D",
            "answer"
        }

        if not reader.fieldnames:
            raise ValueError("Không tìm thấy hàng tiêu đề.")

        missing_columns = required_columns - set(reader.fieldnames)

        if missing_columns:
            raise ValueError(
                "Thiếu cột: "
                + ", ".join(sorted(missing_columns))
            )

        answer_map = {
            "A": 0,
            "B": 1,
            "C": 2,
            "D": 3
        }

        questions = []

        for row_number, row in enumerate(reader, start=2):
            question_text = (row.get("question") or "").strip()

            options = [
                (row.get("A") or "").strip(),
                (row.get("B") or "").strip(),
                (row.get("C") or "").strip(),
                (row.get("D") or "").strip()
            ]

            answer_text = (
                (row.get("answer") or "")
                .strip()
                .upper()
            )

            if not question_text:
                print(
                    f"Bỏ qua dòng {row_number}: "
                    "câu hỏi trống."
                )
                continue

            if any(not option for option in options):
                print(
                    f"Bỏ qua dòng {row_number}: "
                    "có đáp án trống."
                )
                continue

            if answer_text not in answer_map:
                print(
                    f"Bỏ qua dòng {row_number}: "
                    f"đáp án '{answer_text}' không hợp lệ."
                )
                continue

            questions.append({
                "question": question_text,
                "options": options,
                "answer": answer_map[answer_text]
            })

        if not questions:
            raise ValueError(
                "Không đọc được câu hỏi hợp lệ từ Google Sheets."
            )

        print(
            f"Đã tải thành công {len(questions)} "
            "câu hỏi từ Google Sheets."
        )

        return questions

    except Exception as e:
        print("Lỗi đọc Google Sheets:", e)
        print(
            f"Sử dụng {len(DEFAULT_QUESTIONS)} "
            "câu hỏi mặc định."
        )
        return DEFAULT_QUESTIONS.copy()


QUESTIONS = load_questions_from_google()


# =========================================================
# GỬI CÂU HỎI
# =========================================================

def send_question(code):
    if code not in rooms:
        return

    room = rooms[code]

    if room["state"] != "playing":
        return

    questions = room["questions"]

    if not questions:
        room["state"] = "finished"

        socketio.emit(
            "game_over",
            {
                "players": get_players(room)
            },
            to=code
        )

        return

    index = room["question_index"]

    if index < 0 or index >= len(questions):
        room["state"] = "finished"

        socketio.emit(
            "game_over",
            {
                "players": get_players(room)
            },
            to=code
        )

        return

    question = shuffle_question(questions[index])

    room["current_question"] = question

    for player in room["players"].values():
        player["answered"] = False

    # Dùng đồng hồ đơn điệu để tính thời gian trả lời chính xác,
    # không phụ thuộc vào việc đồng hồ hệ thống bị chỉnh.
    room["started_at"] = time.monotonic()

    socketio.emit(
        "game_question",
        {
            "question_number": index + 1,
            "total_questions": len(questions),
            "question": question["question"],
            "options": question["options"],
            "time": QUESTION_TIME
        },
        to=code
    )

    current_round = room["round_id"]

    socketio.start_background_task(
        question_timeout,
        code,
        current_round
    )


# =========================================================
# HẾT THỜI GIAN
# =========================================================

def question_timeout(code, round_id):
    socketio.sleep(QUESTION_TIME)

    if code not in rooms:
        return

    room = rooms[code]

    if room["round_id"] != round_id:
        return

    if room["state"] != "playing":
        return

    finish_round(code)


# =========================================================
# NGƯỜI CHƠI TRẢ LỜI
# =========================================================

@socketio.on("answer")
def answer_question(data):
    code = str(
        data.get("code", "")
    ).strip().upper()

    if code not in rooms:
        emit(
            "error_message",
            {
                "message": "Phòng không tồn tại."
            }
        )
        return

    room = rooms[code]

    if request.sid not in room["players"]:
        emit(
            "error_message",
            {
                "message": "Bạn không ở trong phòng này."
            }
        )
        return

    if room["state"] != "playing":
        emit(
            "error_message",
            {
                "message": "Hiện tại không nhận câu trả lời."
            }
        )
        return

    player = room["players"][request.sid]

    if player["answered"]:
        emit(
            "error_message",
            {
                "message": "Bạn đã trả lời câu này rồi."
            }
        )
        return

    try:
        answer = int(data.get("answer"))
    except (TypeError, ValueError):
        emit(
            "error_message",
            {
                "message": "Đáp án không hợp lệ."
            }
        )
        return

    if answer not in range(4):
        emit(
            "error_message",
            {
                "message": "Đáp án không hợp lệ."
            }
        )
        return

    question = room.get("current_question")

    if not question:
        emit(
            "error_message",
            {
                "message": "Chưa có câu hỏi hiện tại."
            }
        )
        return

    # Tính thời gian từ lúc server phát câu hỏi đến lúc nhận đáp án.
    # Clamp về 0..QUESTION_TIME để tránh sai số nhỏ do hệ thống.
    elapsed = time.monotonic() - room.get("started_at", time.monotonic())
    elapsed = max(0.0, min(elapsed, QUESTION_TIME))

    # Nếu đáp án đến sau thời gian quy định thì không tính điểm.
    if elapsed >= QUESTION_TIME:
        player["answered"] = True

        emit(
            "answer_received",
            {
                "correct": False,
                "points": 0,
                "timeout": True
            }
        )

        finish_round(code)
        return

    player["answered"] = True

    is_correct = answer == question["answer"]

    # Đúng càng nhanh -> điểm càng cao.
    # 0 giây  ≈ 100 điểm
    # 5 giây  ≈ 70 điểm
    # 10 giây ≈ 40 điểm
    # 15 giây ≈ 10 điểm
    if is_correct:
        points = max(
            MIN_SPEED_POINTS,
            round(
                MAX_SPEED_POINTS
                - elapsed * POINTS_LOSS_PER_SECOND
            )
        )
        player["score"] += points
    else:
        points = 0

    emit(
        "answer_received",
        {
            "correct": is_correct,
            "points": points,
            "time": round(elapsed, 2)
        }
    )

    update_room(code)

    if room["players"] and all(
        p["answered"]
        for p in room["players"].values()
    ):
        finish_round(code)


# =========================================================
# KẾT THÚC VÒNG
# =========================================================

def finish_round(code):
    if code not in rooms:
        return

    room = rooms[code]

    if room["state"] != "playing":
        return

    question = room.get("current_question")

    if not question:
        return

    room["state"] = "results"

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


# =========================================================
# CHUYỂN SANG CÂU TIẾP THEO
# =========================================================

def next_round(code, round_id):
    socketio.sleep(3)

    if code not in rooms:
        return

    room = rooms[code]

    if room["round_id"] != round_id:
        return

    if room["state"] != "results":
        return

    total_questions = len(room["questions"])

    if room["question_index"] + 1 >= total_questions:
        room["state"] = "finished"

        socketio.emit(
            "game_over",
            {
                "players": get_players(room)
            },
            to=code
        )

        update_room(code)
        return

    room["question_index"] += 1
    room["round_id"] += 1
    room["state"] = "playing"

    send_question(code)


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
    name = request.form.get(
        "name",
        ""
    ).strip()

    if not name:
        return redirect(url_for("index"))

    if not QUESTIONS:
        return "Không có câu hỏi để chơi."

    code = generate_room_code()

    rooms[code] = {
        "host_sid": None,
        "players": {},
        "state": "waiting",
        "question_index": 0,
        "round_id": 0,
        "started_at": 0,
        "questions": random.sample(
            QUESTIONS,
            len(QUESTIONS)
        ),
        "current_question": None
    }

    return redirect(
        url_for(
            "room",
            code=code,
            name=name
        )
    )


# =========================================================
# VÀO PHÒNG
# =========================================================

@app.route("/join", methods=["POST"])
def join_room_page():
    name = request.form.get(
        "name",
        ""
    ).strip()

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

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

    name = request.args.get(
        "name",
        ""
    ).strip()

    if not name:
        return redirect(url_for("index"))

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
    code = str(
        data.get("code", "")
    ).strip().upper()

    name = str(
        data.get("name", "")
    ).strip()

    if code not in rooms:
        emit(
            "error_message",
            {
                "message": "Phòng không tồn tại."
            }
        )
        return

    if not name:
        emit(
            "error_message",
            {
                "message": "Vui lòng nhập tên."
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

    if request.sid in room["players"]:
        update_room(code)
        return

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

    if room["host_sid"] is None:
        room["host_sid"] = request.sid

    update_room(code)


# =========================================================
# BẮT ĐẦU GAME
# =========================================================

@socketio.on("start_game")
def start_game(data):
    code = str(
        data.get("code", "")
    ).strip().upper()

    if code not in rooms:
        return

    room = rooms[code]

    if request.sid != room["host_sid"]:
        emit(
            "error_message",
            {
                "message": "Chỉ chủ phòng mới có thể bắt đầu game."
            }
        )
        return

    if not room["players"]:
        emit(
            "error_message",
            {
                "message": "Chưa có người chơi."
            }
        )
        return

    if not room["questions"]:
        emit(
            "error_message",
            {
                "message": "Không có câu hỏi để chơi."
            }
        )
        return

    room["state"] = "playing"
    room["question_index"] = 0
    room["round_id"] += 1
    room["current_question"] = None

    for player in room["players"].values():
        player["score"] = 0
        player["answered"] = False

    update_room(code)
    send_question(code)


# =========================================================
# CHAT
# =========================================================

@socketio.on("chat_message")
def chat_message(data):
    code = str(
        data.get("code", "")
    ).strip().upper()

    message = str(
        data.get("message", "")
    ).strip()

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
    code = str(
        data.get("code", "")
    ).strip().upper()

    if code not in rooms:
        return

    room = rooms[code]

    if request.sid != room["host_sid"]:
        emit(
            "error_message",
            {
                "message": "Chỉ chủ phòng mới có thể chơi lại."
            }
        )
        return

    if not room["players"]:
        return

    room["state"] = "waiting"
    room["question_index"] = 0
    room["questions"] = random.sample(
        QUESTIONS,
        len(QUESTIONS)
    )
    room["current_question"] = None
    room["round_id"] += 1
    room["started_at"] = 0

    for player in room["players"].values():
        player["score"] = 0
        player["answered"] = False

    update_room(code)


# =========================================================
# NGẮT KẾT NỐI
# =========================================================

@socketio.on("disconnect")
def disconnect():
    for code, room in list(rooms.items()):
        if request.sid not in room["players"]:
            continue

        was_host = request.sid == room["host_sid"]

        del room["players"][request.sid]

        try:
            leave_room(code)
        except Exception:
            pass

        if not room["players"]:
            del rooms[code]
            return

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
    print("=" * 50)
    print("PHÒNG CHƠI - QUIZ BATTLE")
    print("Server đang chạy tại: http://127.0.0.1:5000")
    print("=" * 50)

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )
