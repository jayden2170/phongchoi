const socket = io();


const body = document.body;


const code = body.dataset.code;

const playerName = body.dataset.player;



// =====================================================
// CÁC ELEMENT
// =====================================================

const connection =
    document.getElementById("connection");

const players =
    document.getElementById("players");

const startButton =
    document.getElementById("startButton");

const lobby =
    document.getElementById("lobby");

const game =
    document.getElementById("game");

const question =
    document.getElementById("question");

const options =
    document.getElementById("options");

const timer =
    document.getElementById("timer");

const timerBar =
    document.getElementById("timerBar");

const questionNumber =
    document.getElementById("questionNumber");

const answerStatus =
    document.getElementById("answerStatus");

const roundResult =
    document.getElementById("roundResult");

const correctAnswer =
    document.getElementById("correctAnswer");

const roundLeaderboard =
    document.getElementById("roundLeaderboard");

const gameOver =
    document.getElementById("gameOver");

const finalLeaderboard =
    document.getElementById("finalLeaderboard");

const restartButton =
    document.getElementById("restartButton");

const chatForm =
    document.getElementById("chatForm");

const chatInput =
    document.getElementById("chatInput");

const messages =
    document.getElementById("messages");



let currentQuestion = null;

let timerInterval = null;



// =====================================================
// KẾT NỐI SERVER
// =====================================================

socket.on("connect", () => {

    connection.innerText =
        "🟢 Đã kết nối";

    socket.emit(
        "join_room",
        {
            code: code,
            name: playerName
        }
    );

});



socket.on("disconnect", () => {

    connection.innerText =
        "🔴 Mất kết nối";

});



// =====================================================
// CẬP NHẬT PHÒNG
// =====================================================

socket.on(
    "room_update",
    (data) => {

        players.innerHTML = "";


        data.players.forEach(
            (player, index) => {

                const div =
                    document.createElement("div");

                div.className =
                    "player";


                let hostText = "";

                if (player.host) {

                    hostText =
                        " 👑 Chủ phòng";

                }


                div.innerHTML = `

                    <span>

                        ${index + 1}.
                        ${escapeHtml(player.name)}

                        <span class="host">
                            ${hostText}
                        </span>

                    </span>

                    <strong>
                        ${player.score}
                    </strong>

                `;


                players.appendChild(div);

            }
        );


        // Hiện nút bắt đầu cho chủ phòng

        if (
            socket.id === data.host_sid &&
            data.state === "waiting"
        ) {

            startButton.style.display =
                "block";

        }
        else {

            startButton.style.display =
                "none";

        }


        // Hiện nút chơi lại

        if (
            socket.id === data.host_sid &&
            data.state === "finished"
        ) {

            restartButton.style.display =
                "block";

        }

    }
);



// =====================================================
// BẮT ĐẦU GAME
// =====================================================

startButton.addEventListener(
    "click",
    () => {

        socket.emit(
            "start_game",
            {
                code: code
            }
        );

    }
);



// =====================================================
// NHẬN CÂU HỎI
// =====================================================

socket.on(
    "game_question",
    (data) => {

        lobby.style.display =
            "none";

        roundResult.style.display =
            "none";

        gameOver.style.display =
            "none";

        game.style.display =
            "block";


        currentQuestion = data;


        questionNumber.innerText =
            `Câu ${data.question_number}/${data.total_questions}`;


        question.innerText =
            data.question;


        answerStatus.innerText = "";


        options.innerHTML = "";


        data.options.forEach(
            (option, index) => {

                const button =
                    document.createElement("button");

                button.className =
                    "option";


                button.innerText =
                    `${String.fromCharCode(65 + index)}. ${option}`;


                button.addEventListener(
                    "click",
                    () => {

                        sendAnswer(index);

                    }
                );


                options.appendChild(button);

            }
        );


        startTimer(data.time);

    }
);



// =====================================================
// TRẢ LỜI
// =====================================================

function sendAnswer(answer) {

    socket.emit(
        "answer",
        {
            code: code,
            answer: answer
        }
    );


    const buttons =
        document.querySelectorAll(
            ".option"
        );


    buttons.forEach(
        button => {

            button.classList.add(
                "disabled"
            );

        }
    );

}



socket.on(
    "answer_received",
    (data) => {

        if (data.correct) {

            answerStatus.innerText =
                `✅ Chính xác! +${data.points} điểm`;

        }
        else {

            answerStatus.innerText =
                "❌ Sai rồi!";

        }

    }
);



// =====================================================
// TIMER
// =====================================================

function startTimer(seconds) {

    clearInterval(timerInterval);


    let remaining =
        seconds;


    timer.innerText =
        remaining;


    timerBar.style.width =
        "100%";


    const start =
        Date.now();


    timerInterval =
        setInterval(
            () => {

                const elapsed =
                    (Date.now() - start)
                    / 1000;


                remaining =
                    Math.max(
                        0,
                        seconds - elapsed
                    );


                timer.innerText =
                    Math.ceil(remaining);


                timerBar.style.width =
                    `${remaining / seconds * 100}%`;


                if (remaining <= 0) {

                    clearInterval(
                        timerInterval
                    );

                }

            },
            100
        );

}



// =====================================================
// KẾT QUẢ VÒNG
// =====================================================

socket.on(
    "round_result",
    (data) => {

        clearInterval(
            timerInterval
        );


        game.style.display =
            "none";

        roundResult.style.display =
            "block";


        const letters =
            ["A", "B", "C", "D"];


        correctAnswer.innerText =
            `Đáp án đúng: ${letters[data.correct]}`;


        showLeaderboard(
            roundLeaderboard,
            data.players
        );

    }
);



// =====================================================
// KẾT THÚC GAME
// =====================================================

socket.on(
    "game_over",
    (data) => {

        game.style.display =
            "none";

        roundResult.style.display =
            "none";

        gameOver.style.display =
            "block";


        showLeaderboard(
            finalLeaderboard,
            data.players
        );

    }
);



// =====================================================
// LEADERBOARD
// =====================================================

function showLeaderboard(
    element,
    playerList
) {

    element.innerHTML = "";


    playerList.forEach(
        (player, index) => {

            const div =
                document.createElement("div");

            div.className =
                "rank";


            div.innerHTML = `

                <span>
                    #${index + 1}
                    ${escapeHtml(player.name)}
                </span>

                <strong>
                    ${player.score} điểm
                </strong>

            `;


            element.appendChild(div);

        }
    );

}



// =====================================================
// CHAT
// =====================================================

chatForm.addEventListener(
    "submit",
    (event) => {

        event.preventDefault();


        const message =
            chatInput.value.trim();


        if (!message) {

            return;

        }


        socket.emit(
            "chat_message",
            {
                code: code,
                message: message
            }
        );


        chatInput.value = "";

    }
);



socket.on(
    "chat_message",
    (data) => {

        const div =
            document.createElement("div");

        div.className =
            "message";


        div.innerHTML = `

            <span class="message-name">
                ${escapeHtml(data.name)}:
            </span>

            ${escapeHtml(data.message)}

        `;


        messages.appendChild(div);


        messages.scrollTop =
            messages.scrollHeight;

    }
);



// =====================================================
// CHƠI LẠI
// =====================================================

restartButton.addEventListener(
    "click",
    () => {

        socket.emit(
            "restart_game",
            {
                code: code
            }
        );

        gameOver.style.display =
            "none";

        lobby.style.display =
            "block";

    }
);



// =====================================================
// ERROR
// =====================================================

socket.on(
    "error_message",
    (data) => {

        alert(data.message);

    }
);



// =====================================================
// CHỐNG HTML ĐỘC
// =====================================================

function escapeHtml(text) {

    const div =
        document.createElement("div");

    div.textContent =
        text;

    return div.innerHTML;

}
