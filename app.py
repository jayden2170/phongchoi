import csv
import io
import random
import re
import string
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)

from flask_socketio import (
    SocketIO,
    emit,
    join_room,
    leave_room
)


# =========================================================
# CẤU HÌNH GOOGLE SHEETS
# =========================================================
APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbwOdNwOPF4b1kJ7wFlB4fWkrdm89rk8WObZXXCgmlfR8qYCP1pf5koA0l_qxvYtPdeD/exec"
)
GOOGLE_SHEET_ID = (
    "1PCxIxAT9d-7TxsFcu2ObC8gM3w_PcTVzhi5WL_mljN8"
)

# Link xuất bản hiện tại của bạn.
GOOGLE_PUBLISHED_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1VtTkFsbrWhZ1JdrwE5x3PzSBk6XLQYKVgQMyb42Rxtg44WeOooq8aQaKU_hA67P-YPFdWbv8Ys6947t/pubhtml"
)

# Bản xuất Excel của toàn bộ bảng tính đã Publish to web.
# Endpoint này chứa tất cả các tab nên không cần biết trước tên tab.
GOOGLE_PUBLISHED_XLSX_URL = GOOGLE_PUBLISHED_URL.replace(
    "/pubhtml",
    "/pub?output=xlsx"
)


# =========================================================
# GIỚI HẠN HỆ THỐNG
# =========================================================

DEFAULT_QUESTION_TIME = 15

MIN_QUESTION_TIME = 5
MAX_QUESTION_TIME = 120

DEFAULT_MAX_PLAYERS = 20
MIN_PLAYERS = 1
MAX_PLAYERS = 100

DEFAULT_QUESTION_COUNT = 20

MAX_SPEED_POINTS = 100
MIN_SPEED_POINTS = 10


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = "phong-choi-secret-key"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)


# =========================================================
# CÂU HỎI MẶC ĐỊNH
# Chỉ dùng khi Google Sheets không tải được.
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
# DỮ LIỆU TRONG RAM
# =========================================================

rooms = {}

QUESTION_BANK = {}

AVAILABLE_SUBJECTS = []


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
# LÀM SẠCH TÊN
# =========================================================

def clean_name(name):

    name = str(name or "").strip()

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name[:20]


# =========================================================
# TRỘN CÂU HỎI
# =========================================================

def shuffle_question(question):

    options = list(
        enumerate(question["options"])
    )

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
# ĐỌC TSV/CSV
# =========================================================

def parse_question_text(text):

    if not text or not text.strip():
        return []

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    first_line = text.splitlines()[0]

    delimiter = "\t" if "\t" in first_line else ","

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter
    )

    if not reader.fieldnames:
        return []

    # Chuẩn hóa tên cột
    field_map = {}

    for field in reader.fieldnames:

        if field is None:
            continue

        clean = field.strip()

        field_map[clean.lower()] = clean

    required = [
        "question",
        "a",
        "b",
        "c",
        "d",
        "answer"
    ]

    for required_name in required:

        if required_name not in field_map:
            return []

    questions = []

    answer_map = {
        "A": 0,
        "B": 1,
        "C": 2,
        "D": 3
    }

    for row_number, row in enumerate(
        reader,
        start=2
    ):

        def get_value(column):

            real_column = field_map.get(
                column.lower()
            )

            if not real_column:
                return ""

            return str(
                row.get(real_column) or ""
            ).strip()

        question_text = get_value("question")

        options = [
            get_value("a"),
            get_value("b"),
            get_value("c"),
            get_value("d")
        ]

        answer_text = get_value(
            "answer"
        ).upper()

        if not question_text:
            continue

        if any(
            not option
            for option in options
        ):
            print(
                f"Bỏ qua dòng {row_number}: "
                "thiếu đáp án."
            )
            continue

        if answer_text not in answer_map:

            print(
                f"Bỏ qua dòng {row_number}: "
                f"đáp án {answer_text} không hợp lệ."
            )

            continue

        questions.append({
            "question": question_text,
            "options": options,
            "answer": answer_map[
                answer_text
            ]
        })

    return questions


# =========================================================
# TẢI MỘT TAB GOOGLE SHEETS
# =========================================================

def load_subject_sheet(sheet_name):

    try:

        url = (
            "https://docs.google.com/spreadsheets/d/"
            f"{GOOGLE_SHEET_ID}/gviz/tq"
        )

        response = requests.get(
            url,
            params={
                "tqx": "out:csv",
                "sheet": sheet_name
            },
            timeout=10
        )

        response.raise_for_status()

        text = response.content.decode(
            "utf-8-sig"
        )

        questions = parse_question_text(
            text
        )

        print(
            f"[Google Sheets] "
            f"{sheet_name}: "
            f"{len(questions)} câu"
        )

        return questions

    except Exception as error:

        print(
            f"Lỗi đọc tab '{sheet_name}':",
            error
        )

        return []


# =========================================================
# LẤY DANH SÁCH TAB
#
# Google Sheets không cung cấp danh sách worksheet qua endpoint
# feeds cũ nữa. Với chế độ Publish to web, ta đọc danh sách tab
# ngay từ trang /pubhtml. Vì vậy khi thêm tab mới vào Google Sheet,
# app.py không cần sửa.
# =========================================================

def _xlsx_column_index(cell_reference):

    letters = "".join(
        char for char in cell_reference
        if char.isalpha()
    ).upper()

    index = 0

    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)

    return max(index - 1, 0)


def _xlsx_text(element, namespace):

    if element is None:
        return ""

    parts = []

    for text_node in element.iter(
        f"{{{namespace['main']}}}t"
    ):
        if text_node.text:
            parts.append(text_node.text)

    return "".join(parts)


def _read_published_xlsx(content):
    """
    Đọc XLSX bằng thư viện chuẩn của Python, không cần cài thêm package.
    Trả về {tên_tab: TSV_text}.
    """

    namespace = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }

    with zipfile.ZipFile(io.BytesIO(content)) as archive:

        shared_strings = []

        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(
                archive.read("xl/sharedStrings.xml")
            )

            for item in root.findall(
                "main:si",
                namespace
            ):
                shared_strings.append(
                    _xlsx_text(item, namespace)
                )

        workbook_root = ET.fromstring(
            archive.read("xl/workbook.xml")
        )

        relationships_root = ET.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )

        relationships = {}

        for relationship in relationships_root:

            rel_id = relationship.attrib.get("Id")
            target = relationship.attrib.get("Target")

            if rel_id and target:
                target = target.lstrip("/")

                if not target.startswith("xl/"):
                    target = "xl/" + target

                relationships[rel_id] = target

        sheets = {}

        for sheet in workbook_root.findall(
            "main:sheets/main:sheet",
            namespace
        ):

            name = sheet.attrib.get("name", "").strip()
            rel_id = sheet.attrib.get(
                f"{{{namespace['rel']}}}id"
            )

            target = relationships.get(rel_id)

            if name and target:
                sheets[name] = target

        result = {}

        for sheet_name, sheet_path in sheets.items():

            if sheet_path not in archive.namelist():
                continue

            root = ET.fromstring(
                archive.read(sheet_path)
            )

            rows = []

            for row_element in root.findall(
                ".//main:sheetData/main:row",
                namespace
            ):

                row_values = {}

                for cell in row_element.findall(
                    "main:c",
                    namespace
                ):

                    reference = cell.attrib.get("r", "A1")
                    column_index = _xlsx_column_index(reference)
                    cell_type = cell.attrib.get("t", "")
                    value_element = cell.find(
                        "main:v",
                        namespace
                    )

                    if cell_type == "inlineStr":
                        value = _xlsx_text(
                            cell.find("main:is", namespace),
                            namespace
                        )

                    elif value_element is None:
                        value = ""

                    else:
                        raw_value = value_element.text or ""

                        if cell_type == "s":
                            try:
                                value = shared_strings[
                                    int(raw_value)
                                ]
                            except (ValueError, IndexError):
                                value = raw_value

                        elif cell_type == "b":
                            value = "TRUE" if raw_value == "1" else "FALSE"

                        else:
                            value = raw_value

                    row_values[column_index] = value

                if row_values:
                    max_index = max(row_values)
                    row = [
                        row_values.get(index, "")
                        for index in range(max_index + 1)
                    ]
                    rows.append(row)

            if not rows:
                result[sheet_name] = ""
                continue

            width = max(len(row) for row in rows)
            lines = []

            for row in rows:

                row = row + [""] * (width - len(row))

                safe_values = [
                    str(value).replace("\t", " ").replace("\n", " ")
                    for value in row
                ]

                lines.append("\t".join(safe_values))

            result[sheet_name] = "\n".join(lines)

        return result


def discover_sheet_names():

    try:

        response = requests.get(
            GOOGLE_PUBLISHED_XLSX_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            },
            timeout=30
        )

        response.raise_for_status()

        sheets = _read_published_xlsx(
            response.content
        )

        names = list(sheets.keys())

        if names:
            print(
                "[Google Sheets] Các tab từ Publish to web:",
                names
            )

        return names

    except requests.HTTPError as error:

        status = getattr(
            error.response,
            "status_code",
            None
        )

        print(
            "[Google Sheets] Không tải được dữ liệu Publish to web "
            f"(HTTP {status}): {error}"
        )
        return []

    except Exception as error:

        print(
            "[Google Sheets] Không thể đọc danh sách tab từ "
            "Publish to web:",
            error
        )

        return []



def load_all_published_sheets():
    """
    Lấy danh sách tab từ Apps Script API,
    sau đó tải câu hỏi của từng tab qua Google Sheets gviz.
    Tự nhận diện các tab mới mà không cần sửa app.py.
    """

    try:
        response = requests.get(
            APPS_SCRIPT_URL,
            timeout=15
        )
        response.raise_for_status()

        data = response.json()
        sheets = data.get("sheets", [])

        if not isinstance(sheets, list):
            raise ValueError(
                "API không trả về danh sách tab hợp lệ."
            )

        all_questions = {}

        for sheet in sheets:
            if not isinstance(sheet, dict):
                continue

            sheet_name = sheet.get("name")

            if not isinstance(sheet_name, str):
                continue

            sheet_name = sheet_name.strip()

            if not sheet_name:
                continue

            questions = load_subject_sheet(sheet_name)

            if questions:
                all_questions[sheet_name] = questions

        return all_questions

    except Exception as error:
        print(
            "[Google Sheets] Lỗi khi lấy danh sách tab "
            "hoặc tải dữ liệu:",
            error
        )
        return {}

def load_question_bank():

    global QUESTION_BANK
    global AVAILABLE_SUBJECTS

    QUESTION_BANK = {}

    # Tải toàn bộ workbook một lần. Nhờ đó mọi tab hiện có và các
    # tab được thêm về sau đều tự động được nhận diện, không cần sửa app.py.
    published_questions = load_all_published_sheets()

    if published_questions:
        QUESTION_BANK.update(
            published_questions
        )

    AVAILABLE_SUBJECTS = sorted(
        QUESTION_BANK.keys(),
        key=lambda x: x.lower()
    )

    # Nếu không có dữ liệu Google Sheets,
    # giữ nguyên cơ chế dự phòng cũ của app.
    if not QUESTION_BANK:

        fallback_subjects = [
            "Toán",
            "Lịch sử"
        ]

        for subject in fallback_subjects:

            questions = load_subject_sheet(
                subject
            )

            if questions:
                QUESTION_BANK[subject] = questions

        AVAILABLE_SUBJECTS = sorted(
            QUESTION_BANK.keys(),
            key=lambda x: x.lower()
        )

    # Nếu không có dữ liệu Google Sheets,
    # tạo môn mặc định.
    if not QUESTION_BANK:

        QUESTION_BANK["Mặc định"] = (
            DEFAULT_QUESTIONS.copy()
        )

        AVAILABLE_SUBJECTS = [
            "Mặc định"
        ]

    print("=" * 60)
    print("Các môn đã tải:", AVAILABLE_SUBJECTS)

    for subject in AVAILABLE_SUBJECTS:
        print(
            f" - {subject}: "
            f"{len(QUESTION_BANK[subject])} câu"
        )

    print("=" * 60)


# =========================================================
# TẢI LẠI NGÂN HÀNG
# =========================================================

def refresh_question_bank():

    load_question_bank()


# =========================================================
# LẤY NGƯỜI CHƠI
# =========================================================

def get_players(room):

    players = []

    for sid, player in room["players"].items():

        players.append({

            "name": player["name"],

            "score": player["score"],

            "correct": player["correct"],

            "wrong": player["wrong"],

            "unanswered": player["unanswered"],

            "host": (
                sid == room["host_sid"]
            )

        })

    players.sort(
        key=lambda player: (
            player["score"],
            player["correct"]
        ),
        reverse=True
    )

    return players


# =========================================================
# CẬP NHẬT PHÒNG
# =========================================================

def update_room(code):

    if code not in rooms:
        return

    room = rooms[code]

    socketio.emit(
        "room_update",
        {
            "players": get_players(room),

            "host_sid":
                room["host_sid"],

            "state":
                room["state"],

            "subject":
                room["subject"],

            "question_count":
                len(room["questions"]),

            "question_time":
                room["question_time"],

            "max_players":
                room["max_players"]
        },
        to=code
    )


# =========================================================
# TÍNH ĐIỂM THEO TỐC ĐỘ
# =========================================================

def calculate_speed_points(
    elapsed,
    question_time
):

    if elapsed <= 0:
        return MAX_SPEED_POINTS

    if elapsed >= question_time:
        return 0

    ratio = elapsed / question_time

    # Hàm bình phương tạo khoảng cách lớn
    # giữa người trả lời rất nhanh và người trả lời chậm.
    #
    # 0% thời gian  -> 100 điểm
    # 25%           -> khoảng 60 điểm
    # 50%           -> khoảng 33 điểm
    # 75%           -> khoảng 15 điểm
    # 100%          -> 10 điểm

    points = (
        MIN_SPEED_POINTS
        + (
            MAX_SPEED_POINTS
            - MIN_SPEED_POINTS
        ) * ((1 - ratio) ** 2)
    )

    return max(
        MIN_SPEED_POINTS,
        round(points)
    )


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

    index = room["question_index"]

    if (
        not questions
        or index >= len(questions)
    ):

        finish_game(code)

        return

    question = shuffle_question(
        questions[index]
    )

    room["current_question"] = question

    for player in room["players"].values():

        player["answered"] = False

    room["started_at"] = time.monotonic()

    room["question_started"] = True

    socketio.emit(
        "game_question",
        {

            "question_number":
                index + 1,

            "total_questions":
                len(questions),

            "question":
                question["question"],

            "options":
                question["options"],

            "time":
                room["question_time"]

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
# TIMEOUT
# =========================================================

def question_timeout(
    code,
    round_id
):

    if code not in rooms:
        return

    room = rooms[code]

    socketio.sleep(
        room["question_time"]
    )

    if code not in rooms:
        return

    room = rooms[code]

    if room["round_id"] != round_id:
        return

    if room["state"] != "playing":
        return

    # Những người chưa trả lời được tính là chưa trả lời.
    for player in room["players"].values():

        if not player["answered"]:

            player["answered"] = True
            player["unanswered"] += 1

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
                "message":
                    "Phòng không tồn tại."
            }
        )

        return

    room = rooms[code]

    sid = request.sid

    if sid not in room["players"]:

        emit(
            "error_message",
            {
                "message":
                    "Bạn không ở trong phòng."
            }
        )

        return

    if room["state"] != "playing":

        emit(
            "error_message",
            {
                "message":
                    "Game hiện không nhận câu trả lời."
            }
        )

        return

    player = room["players"][sid]

    if player["answered"]:

        emit(
            "error_message",
            {
                "message":
                    "Bạn đã trả lời câu này."
            }
        )

        return

    try:

        answer = int(
            data.get("answer")
        )

    except (
        TypeError,
        ValueError
    ):

        emit(
            "error_message",
            {
                "message":
                    "Đáp án không hợp lệ."
            }
        )

        return

    question = room.get(
        "current_question"
    )

    if not question:

        emit(
            "error_message",
            {
                "message":
                    "Chưa có câu hỏi."
            }
        )

        return

    if answer not in range(4):

        emit(
            "error_message",
            {
                "message":
                    "Đáp án không hợp lệ."
            }
        )

        return

    elapsed = (
        time.monotonic()
        - room["started_at"]
    )

    elapsed = max(
        0,
        min(
            elapsed,
            room["question_time"]
        )
    )

    player["answered"] = True

    is_correct = (
        answer == question["answer"]
    )

    if is_correct:

        points = calculate_speed_points(
            elapsed,
            room["question_time"]
        )

        player["score"] += points
        player["correct"] += 1

    else:

        points = 0
        player["wrong"] += 1

    emit(
        "answer_received",
        {

            "correct":
                is_correct,

            "points":
                points,

            "time":
                round(elapsed, 2),

            "selected":
                answer,

            "correct_answer":
                question["answer"],

            "question":
                question["question"],

            "options":
                question["options"]

        }
    )

    update_room(code)

    # Tất cả đã trả lời
    if room["players"]:

        if all(
            player["answered"]
            for player in room["players"].values()
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

    question = room.get(
        "current_question"
    )

    if not question:
        return

    room["state"] = "results"

    # Gửi kết quả vòng.
    socketio.emit(
        "round_result",
        {

            "question":
                question["question"],

            "options":
                question["options"],

            "correct":
                question["answer"],

            "players":
                get_players(room)

        },
        to=code
    )

    update_room(code)

    current_round = room["round_id"]

    socketio.start_background_task(
        next_round,
        code,
        current_round
    )


# =========================================================
# CÂU TIẾP THEO
# =========================================================

def next_round(
    code,
    round_id
):

    socketio.sleep(3)

    if code not in rooms:
        return

    room = rooms[code]

    if room["round_id"] != round_id:
        return

    if room["state"] != "results":
        return

    if (
        room["question_index"] + 1
        >= len(room["questions"])
    ):

        finish_game(code)

        return

    room["question_index"] += 1

    room["round_id"] += 1

    room["state"] = "playing"

    send_question(code)


# =========================================================
# KẾT THÚC GAME
# =========================================================

def finish_game(code):

    if code not in rooms:
        return

    room = rooms[code]

    room["state"] = "finished"

    socketio.emit(
        "game_over",
        {
            "players":
                get_players(room)
        },
        to=code
    )

    update_room(code)


# =========================================================
# TRANG CHỦ
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# FORM CÀI ĐẶT SAU KHI BẤM TẠO PHÒNG
# =========================================================

@app.route(
    "/create",
    methods=["POST"]
)
def create_room_settings():

    name = clean_name(
        request.form.get(
            "name",
            ""
        )
    )

    if not name:

        return redirect(
            url_for("index")
        )

    refresh_question_bank()

    return render_template(
        "create_room.html",
        player_name=name,
        subjects=AVAILABLE_SUBJECTS
    )


# =========================================================
# TẠO PHÒNG THẬT SỰ
# =========================================================

@app.route(
    "/create-room",
    methods=["POST"]
)
def create_room():

    name = clean_name(
        request.form.get(
            "name",
            ""
        )
    )

    subject = str(
        request.form.get(
            "subject",
            ""
        )
    ).strip()

    try:

        question_count = int(
            request.form.get(
                "question_count",
                DEFAULT_QUESTION_COUNT
            )
        )

    except ValueError:

        question_count = (
            DEFAULT_QUESTION_COUNT
        )

    try:

        question_time = int(
            request.form.get(
                "question_time",
                DEFAULT_QUESTION_TIME
            )
        )

    except ValueError:

        question_time = (
            DEFAULT_QUESTION_TIME
        )

    try:

        max_players = int(
            request.form.get(
                "max_players",
                DEFAULT_MAX_PLAYERS
            )
        )

    except ValueError:

        max_players = DEFAULT_MAX_PLAYERS

    question_time = max(
        MIN_QUESTION_TIME,
        min(
            question_time,
            MAX_QUESTION_TIME
        )
    )

    max_players = max(
        MIN_PLAYERS,
        min(
            max_players,
            MAX_PLAYERS
        )
    )

    if subject not in QUESTION_BANK:

        return (
            "Môn học không tồn tại."
        )

    available_questions = (
        QUESTION_BANK[subject]
    )

    if not available_questions:

        return (
            "Môn này chưa có câu hỏi."
        )

    question_count = max(
        1,
        min(
            question_count,
            len(available_questions)
        )
    )

    selected_questions = random.sample(
        available_questions,
        question_count
    )

    code = generate_room_code()

    rooms[code] = {

        "host_sid":
            None,

        "players":
            {},

        "state":
            "waiting",

        "subject":
            subject,

        "max_players":
            max_players,

        "question_time":
            question_time,

        "question_index":
            0,

        "round_id":
            0,

        "started_at":
            0,

        "question_started":
            False,

        "questions":
            selected_questions,

        "current_question":
            None

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

@app.route(
    "/join",
    methods=["POST"]
)
def join_room_page():

    name = clean_name(
        request.form.get(
            "name",
            ""
        )
    )

    code = str(
        request.form.get(
            "code",
            ""
        )
    ).strip().upper()

    if not name or not code:

        return redirect(
            url_for("index")
        )

    if code not in rooms:

        return (
            "Phòng không tồn tại."
        )

    room = rooms[code]

    if room["state"] != "waiting":

        return (
            "Game đã bắt đầu."
        )

    if len(room["players"]) >= room["max_players"]:

        return (
            "Phòng đã đủ người."
        )

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

        return (
            "Phòng không tồn tại."
        )

    name = clean_name(
        request.args.get(
            "name",
            ""
        )
    )

    if not name:

        return redirect(
            url_for("index")
        )

    room_data = rooms[code]

    return render_template(
        "room.html",
        code=code,
        player_name=name,
        subject=room_data["subject"],
        question_count=len(
            room_data["questions"]
        ),
        question_time=room_data[
            "question_time"
        ],
        max_players=room_data[
            "max_players"
        ]
    )


# =========================================================
# SOCKET: THAM GIA PHÒNG
# =========================================================

@socketio.on("join_room")
def handle_join(data):

    code = str(
        data.get("code", "")
    ).strip().upper()

    name = clean_name(
        data.get("name", "")
    )

    if code not in rooms:

        emit(
            "error_message",
            {
                "message":
                    "Phòng không tồn tại."
            }
        )

        return

    room = rooms[code]

    if not name:

        emit(
            "error_message",
            {
                "message":
                    "Vui lòng nhập tên."
            }
        )

        return

    if room["state"] != "waiting":

        emit(
            "error_message",
            {
                "message":
                    "Game đã bắt đầu."
            }
        )

        return

    if (
        request.sid
        in room["players"]
    ):

        update_room(code)

        return

    if (
        len(room["players"])
        >= room["max_players"]
    ):

        emit(
            "error_message",
            {
                "message":
                    "Phòng đã đủ người."
            }
        )

        return

    for player in room["players"].values():

        if (
            player["name"].lower()
            == name.lower()
        ):

            emit(
                "error_message",
                {
                    "message":
                        "Tên này đã được sử dụng."
                }
            )

            return

    join_room(code)

    room["players"][
        request.sid
    ] = {

        "name":
            name,

        "score":
            0,

        "correct":
            0,

        "wrong":
            0,

        "unanswered":
            0,

        "answered":
            False
    }

    if room["host_sid"] is None:

        room["host_sid"] = (
            request.sid
        )

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
                "message":
                    "Chỉ chủ phòng mới có thể bắt đầu."
            }
        )

        return

    if not room["players"]:

        emit(
            "error_message",
            {
                "message":
                    "Chưa có người chơi."
            }
        )

        return

    room["state"] = "playing"

    room["question_index"] = 0

    room["round_id"] += 1

    for player in room["players"].values():

        player["score"] = 0
        player["correct"] = 0
        player["wrong"] = 0
        player["unanswered"] = 0
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

    message = message[:200]

    if code not in rooms:
        return

    room = rooms[code]

    if request.sid not in room["players"]:
        return

    if not message:
        return

    name = room["players"][
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
                "message":
                    "Chỉ chủ phòng mới có thể chơi lại."
            }
        )

        return

    questions = QUESTION_BANK.get(
        room["subject"],
        []
    )

    if not questions:

        emit(
            "error_message",
            {
                "message":
                    "Không còn câu hỏi cho môn này."
            }
        )

        return

    question_count = min(
        len(questions),
        len(room["questions"])
    )

    room["questions"] = random.sample(
        questions,
        question_count
    )

    room["state"] = "waiting"

    room["question_index"] = 0

    room["current_question"] = None

    room["round_id"] += 1

    room["started_at"] = 0

    for player in room["players"].values():

        player["score"] = 0
        player["correct"] = 0
        player["wrong"] = 0
        player["unanswered"] = 0
        player["answered"] = False

    update_room(code)


# =========================================================
# NGẮT KẾT NỐI
# =========================================================

@socketio.on("disconnect")
def disconnect():

    for code, room in list(
        rooms.items()
    ):

        if request.sid not in room["players"]:
            continue

        was_host = (
            request.sid
            == room["host_sid"]
        )

        del room["players"][
            request.sid
        ]

        try:

            leave_room(code)

        except Exception:

            pass

        # Không còn ai -> xóa phòng.
        if not room["players"]:

            del rooms[code]

            return

        # Chủ phòng rời -> chuyển quyền.
        if was_host:

            room["host_sid"] = next(
                iter(room["players"])
            )

        update_room(code)

        return


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "rooms": len(rooms),
        "subjects": AVAILABLE_SUBJECTS
    }


# =========================================================
# CHẠY SERVER
# =========================================================

if __name__ == "__main__":

    print("=" * 60)

    print(
        "QUIZ BATTLE SERVER"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print("=" * 60)

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )