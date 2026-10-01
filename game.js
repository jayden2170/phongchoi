const socket = io();

const body = document.body;

const code = body.dataset.code;

const playerName = body.dataset.player;


// =====================================================
// ELEMENT
// =====================================================

const connection =
    document.getElementById("connection");

const players =
    document.getElementById("players");

const playerCount =
    document.getElementById("playerCount");

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

const roundAnswerBox =
    document.getElementById("roundAnswerBox");

const roundLeaderboard =
    document.getElementById(
        "roundLeaderboard"
    );

const gameOver =
    document.getElementById("gameOver");

const finalLeaderboard =
    document.getElementById(
        "finalLeaderboard"
    );

const restartButton =
    document.getElementById(
        "restartButton"
    );

const chatForm =
    document.getElementById("chatForm");

const chatInput =
    document.getElementById("chatInput");

const messages =
    document.getElementById("messages");


let timerInterval = null;

let hasAnswered = false;


// =====================================================
// KẾT NỐI
// =====================================================

socket.on(
    "connect",
    () => {

        connection.innerText =
            "🟢 Đã kết nối";

        socket.emit(
            "join_room",
            {
                code: code,
                name: playerName
            }
        );

    }
);


socket.on(
    "disconnect",
    () => {

        connection.innerText =
            "🔴 Mất kết nối";

    }
);


// =====================================================
// PHÒNG
// =====================================================

socket.on(
    "room_update",
    (data) => {

        players.innerHTML = "";


        playerCount.innerText =
            `${data.players.length}/${data.max_players}`;


        data.players.forEach(
            (player, index) => {

                const div =
                    document.createElement(
                        "div"
                    );

                div.className =
                    "player";


                const left =
                    document.createElement(
                        "div"
                    );

                left.className =
                    "player-left";


                const name =
                    document.createElement(
                        "span"
                    );

                name.innerText =
                    `${index + 1}. ${player.name}`;


                if (player.host) {

                    const host =
                        document.createElement(
                            "span"
                        );

                    host.className =
                        "host";

                    host.innerText =
                        " 👑 Chủ phòng";

                    name.appendChild(
                        host
                    );

                }


                left.appendChild(
                    name
                );


                const score =
                    document.createElement(
                        "strong"
                    );

                score.innerText =
                    `${player.score} điểm`;


                div.appendChild(
                    left
                );

                div.appendChild(
                    score
                );


                players.appendChild(
                    div
                );

            }
        );


        // Chủ phòng được bắt đầu.
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


        // Chủ phòng được chơi lại.
        if (
            socket.id === data.host_sid &&
            data.state === "finished"
        ) {

            restartButton.style.display =
                "block";

        }
        else {

            restartButton.style.display =
                "none";

        }

    }
);


// =====================================================
// BẮT ĐẦU
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

        clearInterval(
            timerInterval
        );


        hasAnswered = false;


        lobby.style.display =
            "none";

        roundResult.style.display =
            "none";

        gameOver.style.display =
            "none";

        game.style.display =
            "block";


        questionNumber.innerText =
            `Câu ${data.question_number}/${data.total_questions}`;


        question.innerText =
            data.question;


        answerStatus.innerText =
            "";


        options.innerHTML =
            "";


        data.options.forEach(
            (option, index) => {

                const button =
                    document.createElement(
                        "button"
                    );

                button.className =
                    "option";

                button.type =
                    "button";

                button.innerText =
                    `${String.fromCharCode(
                        65 + index
                    )}. ${option}`;


                button.addEventListener(
                    "click",
                    () => {

                        sendAnswer(
                            index
                        );

                    }
                );


                options.appendChild(
                    button
                );

            }
        );


        startTimer(
            data.time
        );

    }
);


// =====================================================
// TRẢ LỜI
// =====================================================

function sendAnswer(answer) {

    if (hasAnswered) {
        return;
    }


    hasAnswered = true;


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


// =====================================================
// KẾT QUẢ TRẢ LỜI
// =====================================================

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

    clearInterval(
        timerInterval
    );


    let remaining = seconds;


    timer.innerText =
        Math.ceil(remaining);


    timerBar.style.width =
        "100%";


    const start =
        Date.now();


    timerInterval =
        setInterval(
            () => {

                const elapsed =
                    (
                        Date.now()
                        - start
                    ) / 1000;


                remaining =
                    Math.max(
                        0,
                        seconds - elapsed
                    );


                timer.innerText =
                    Math.ceil(
                        remaining
                    );


                timerBar.style.width =
                    `${(
                        remaining / seconds
                    ) * 100}%`;


                if (
                    remaining <= 0
                ) {

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


        roundAnswerBox.innerHTML =
            `
            <div>
                <strong>Câu hỏi:</strong>
                ${escapeHtml(data.question)}
            </div>

            <br>

            <div class="correct-answer">
                ✅ Đáp án đúng:
                ${letters[data.correct]}.
                ${escapeHtml(
                    data.options[data.correct]
                )}
            </div>
            `;


        showLeaderboard(
            roundLeaderboard,
            data.players
        );

    }
);


// =====================================================
// GAME OVER
// =====================================================

socket.on(
    "game_over",
    (data) => {

        clearInterval(
            timerInterval
        );


        game.style.display =
            "none";

        roundResult.style.display =
            "none";

        lobby.style.display =
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

    element.innerHTML =
        "";


    playerList.forEach(
        (player, index) => {

            const div =
                document.createElement(
                    "div"
                );

            div.className =
                "rank";


            const rank =
                document.createElement(
                    "strong"
                );

            rank.innerText =
                `#${index + 1}`;


            const info =
                document.createElement(
                    "div"
                );

            const name =
                document.createElement(
                    "div"
                );

            name.innerText =
                player.name;


            const stats =
                document.createElement(
                    "div"
                );

            stats.className =
                "rank-stats";


            stats.innerText =
                `✅ ${player.correct} đúng  |  ` +
                `❌ ${player.wrong} sai  |  ` +
                `⏱️ ${player.unanswered} chưa trả lời`;


            info.appendChild(
                name
            );

            info.appendChild(
                stats
            );


            const score =
                document.createElement(
                    "div"
                );

            score.className =
                "rank-score";

            score.innerHTML =
                `<strong>${player.score} điểm</strong>`;


            div.appendChild(
                rank
            );

            div.appendChild(
                info
            );

            div.appendChild(
                score
            );


            element.appendChild(
                div
            );

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


        chatInput.value =
            "";

    }
);


socket.on(
    "chat_message",
    (data) => {

        const div =
            document.createElement(
                "div"
            );

        div.className =
            "message";


        const name =
            document.createElement(
                "span"
            );

        name.className =
            "message-name";

        name.innerText =
            `${data.name}: `;


        const message =
            document.createElement(
                "span"
            );

        message.innerText =
            data.message;


        div.appendChild(
            name
        );

        div.appendChild(
            message
        );


        messages.appendChild(
            div
        );


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

        alert(
            data.message
        );

    }
);


// =====================================================
// CHỐNG HTML
// =====================================================

function escapeHtml(text) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        text;

    return div.innerHTML;

}