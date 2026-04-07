import socket
import random
import time

# ============================================================
# // CONFIG SECTION - EASY TO CHANGE
# ============================================================

# // TCP is used only for the first handshake / player registration
TCP_HOST = "0.0.0.0"
TCP_PORT = 5000

# // UDP is used for the live quiz gameplay after handshake
UDP_HOST = "0.0.0.0"
UDP_PORT = 5001

# // Maximum number of players allowed in this MVP
MAX_PLAYERS = 4

# // Number of rounds to play
ROUNDS = 5

# // How many seconds a player has to answer each question
ANSWER_TIMEOUT = 30

# // Buffer size for sending and receiving messages
BUFFER_SIZE = 1024


# ============================================================
# // GLOBAL DATA STRUCTURES
# ============================================================

# // TCP socket for reliable join / handshake messages
# // UDP socket for live game traffic
# // Using the same port numbers everywhere keeps setup simple.
tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

tcp_server.bind((TCP_HOST, TCP_PORT))
udp_server.bind((UDP_HOST, UDP_PORT))

tcp_server.listen()

# // Stores player information by player_id
# // Example:
# // players["player_1"] = {
# //     "name": "Adeel",
# //     "tcp_addr": (ip, port),
# //     "udp_addr": (ip, port),
# //     "udp_ready": True,
# //     "score": 0
# // }
players = {}

# // This stores one answer per player for the current question
answers = {}

# // The server operator chooses how many players to wait for
expected_players = 0


# ============================================================
# // QUESTION LOADING
# ============================================================

def load_questions():
    # // Try to load questions from questions.json.
    # // If that file does not exist yet, use fallback questions.
    try:
        import json
        with open("questions.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return [
            {
                "prompt": "What does HTTP stand for?",
                "choices": [
                    "HyperText Transfer Protocol",
                    "High Text Transfer Protocol",
                    "Hyper Tool Transfer Process",
                    "None of the above"
                ],
                "answer": 1
            },
            {
                "prompt": "Which protocol is connectionless?",
                "choices": ["TCP", "UDP", "SMTP", "FTP"],
                "answer": 2
            },
            {
                "prompt": "Which OSI layer handles routing?",
                "choices": ["Transport", "Network", "Session", "Application"],
                "answer": 2
            },
            {
                "prompt": "What is the default port for HTTP?",
                "choices": ["21", "25", "80", "443"],
                "answer": 3
            },
            {
                "prompt": "Which protocol is used to send email?",
                "choices": ["POP3", "SMTP", "ARP", "SSH"],
                "answer": 2
            },
            {
                "prompt": "What does DNS do?",
                "choices": [
                    "Assigns IP addresses",
                    "Translates domain names to IP addresses",
                    "Encrypts data",
                    "Filters traffic"
                ],
                "answer": 2
            },
            {
                "prompt": "What is the loopback IP address?",
                "choices": ["10.0.0.1", "127.0.0.1", "192.168.1.1", "8.8.8.8"],
                "answer": 2
            },
            {
                "prompt": "Which device operates mainly at Layer 2?",
                "choices": ["Router", "Switch", "Modem", "Firewall"],
                "answer": 2
            }
        ]


questions = load_questions()


# ============================================================
# // HELPER FUNCTIONS
# ============================================================

def send_tcp_message(connection, message):
    # // Send a normal text message over TCP
    connection.send(message.encode())


def send_udp_message(udp_addr, message):
    # // Send a normal text message over UDP
    udp_server.sendto(message.encode(), udp_addr)


def broadcast_udp(message):
    # // Send the same UDP message to every player who completed UDP setup
    for player_id, info in players.items():
        if info["udp_ready"] and info["udp_addr"] is not None:
            send_udp_message(info["udp_addr"], message)


def get_player_name(player_id):
    # // Small helper for clean code / readable lookups
    return players[player_id]["name"]


def get_score_message():
    # // Build one SCORE message to send to all clients
    # // Example: SCORE|Adeel:2|Justin:1
    message = "SCORE"
    for player_id, info in players.items():
        message += f"|{info['name']}:{info['score']}"
    return message


def all_udp_ready():
    # // Return True only when every joined player finished the UDP registration step
    if len(players) != expected_players:
        return False

    for info in players.values():
        if not info["udp_ready"]:
            return False

    return True


def get_expected_players():
    # // Let the server operator choose how many players to wait for
    # // This is what lets you start the game with any number of players from 1 to 4
    while True:
        user_input = input(f"How many players should join? (1-{MAX_PLAYERS}): ").strip()
        if user_input.isdigit():
            value = int(user_input)
            if 1 <= value <= MAX_PLAYERS:
                return value
        print(f"Please enter a number from 1 to {MAX_PLAYERS}.")


# ============================================================
# // TCP HANDSHAKE / JOIN PHASE
# ============================================================

def accept_tcp_players():
    # // Wait for exactly the number of players chosen by the server operator
    # // Each player gets a player_id and the UDP port to use next
    print("Waiting for players to connect using TCP...")

    while len(players) < expected_players:
        connection, address = tcp_server.accept()
        message = connection.recv(BUFFER_SIZE).decode().strip()

        if not message.startswith("JOIN|"):
            send_tcp_message(connection, "ERROR|Invalid join format")
            connection.close()
            continue

        name = message.split("|", 1)[1].strip()

        if not name:
            send_tcp_message(connection, "ERROR|Player name cannot be blank")
            connection.close()
            continue

        # // Prevent duplicate player names to keep scores clear
        duplicate_name = False
        for info in players.values():
            if info["name"].lower() == name.lower():
                duplicate_name = True
                break

        if duplicate_name:
            send_tcp_message(connection, "ERROR|That player name is already taken")
            connection.close()
            continue

        player_id = f"player_{len(players) + 1}"

        players[player_id] = {
            "name": name,
            "tcp_addr": address,
            "udp_addr": None,
            "udp_ready": False,
            "score": 0
        }

        # // Tell the client its ID and which UDP port to use for gameplay
        welcome_message = f"WELCOME|{name}|{player_id}|{UDP_PORT}"
        send_tcp_message(connection, welcome_message)
        connection.close()

        print(f"{name} joined successfully as {player_id} from {address}")

    print("All expected players finished the TCP handshake.")


# ============================================================
# // UDP REGISTRATION PHASE
# ============================================================

def wait_for_udp_registration():
    # // After TCP handshake, each client sends UDP_READY so the server learns
    # // the real UDP address for that player.
    print("Waiting for players to confirm UDP setup...")

    while not all_udp_ready():
        data, address = udp_server.recvfrom(BUFFER_SIZE)
        message = data.decode().strip()
        parts = message.split("|")

        if len(parts) >= 3 and parts[0] == "UDP_READY":
            player_id = parts[1]
            player_name = parts[2]

            if player_id in players and players[player_id]["name"] == player_name:
                players[player_id]["udp_addr"] = address
                players[player_id]["udp_ready"] = True
                send_udp_message(address, f"UDP_OK|{player_id}")
                print(f"UDP confirmed for {player_name} at {address}")

    print("All players are ready. Starting game...")


# ============================================================
# // GAMEPLAY FUNCTIONS
# ============================================================

def collect_answers_for_question(question_id):
    # // Read incoming ANSWER packets until everyone answered or time runs out
    # // Only the first answer from each player is kept
    global answers
    answers = {}

    start_time = time.time()

    while time.time() - start_time < ANSWER_TIMEOUT:
        udp_server.settimeout(0.5)

        try:
            data, address = udp_server.recvfrom(BUFFER_SIZE)
            message = data.decode().strip()
            parts = message.split("|")

            # // Expected format from client:
            # // ANSWER|player_id|player_name|question_id|answer_number
            if len(parts) == 5 and parts[0] == "ANSWER":
                player_id = parts[1]
                player_name = parts[2]
                incoming_question_id = parts[3]
                answer_text = parts[4]

                # // Ignore answers for old / wrong questions
                if incoming_question_id != question_id:
                    continue

                # // Ignore unknown players
                if player_id not in players:
                    continue

                # // Ignore name mismatch
                if players[player_id]["name"] != player_name:
                    continue

                # // Ignore duplicate answers from the same player
                if player_id in answers:
                    continue

                if answer_text in ["1", "2", "3", "4"]:
                    answers[player_id] = int(answer_text)
                    print(f"Received answer from {player_name}: {answer_text}")

                # // Stop waiting early if everyone answered
                if len(answers) == expected_players:
                    break

        except socket.timeout:
            pass

    udp_server.settimeout(None)


def run_game():
    # // Main game loop
    # // The server controls all rules, scores, and final results
    selected_questions = random.sample(questions, min(len(questions), ROUNDS))

    broadcast_udp("START|The game is starting now!")
    time.sleep(1)

    for round_index, question in enumerate(selected_questions, start=1):
        question_id = f"Q{round_index}"

        # // QUESTION format expected by client.py
        question_message = (
            f"QUESTION|{question_id}|{question['prompt']}|"
            f"{question['choices'][0]}|{question['choices'][1]}|"
            f"{question['choices'][2]}|{question['choices'][3]}"
        )

        broadcast_udp(question_message)
        print(f"Sent {question_id}: {question['prompt']}")

        collect_answers_for_question(question_id)

        correct_answer_number = question["answer"]
        correct_answer_text = question["choices"][correct_answer_number - 1]

        # // Find the first correct player in the order answers were received
        winner_id = None
        for player_id, answer_number in answers.items():
            if answer_number == correct_answer_number:
                winner_id = player_id
                break

        if winner_id is not None:
            players[winner_id]["score"] += 1
            winner_name = get_player_name(winner_id)
            broadcast_udp(f"RESULT|{winner_name} answered first and correctly.")
            broadcast_udp(f"INFO|Correct answer: {correct_answer_number}. {correct_answer_text}")
        else:
            broadcast_udp("RESULT|No player answered correctly in time.")
            broadcast_udp(f"INFO|Correct answer: {correct_answer_number}. {correct_answer_text}")

        broadcast_udp(get_score_message())
        time.sleep(2)

    send_game_over()


def send_game_over():
    # // Send the final scoreboard to all clients
    final_message = "GAMEOVER"
    for player_id, info in players.items():
        final_message += f"|{info['name']}:{info['score']}"

    broadcast_udp(final_message)
    print("Game finished.")


# ============================================================
# // MAIN PROGRAM
# ============================================================

def main():
    global expected_players

    print("=" * 60)
    print("MULTIPLAYER QUIZ GAME SERVER")
    print("=" * 60)
    print(f"TCP handshake server running on {TCP_HOST}:{TCP_PORT}")
    print(f"UDP game server running on {UDP_HOST}:{UDP_PORT}")

    expected_players = get_expected_players()

    accept_tcp_players()
    wait_for_udp_registration()
    run_game()

    tcp_server.close()
    udp_server.close()


if __name__ == "__main__":
    main()
