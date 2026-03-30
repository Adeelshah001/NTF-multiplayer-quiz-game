import socket
import json
import random
import threading
import time

HOST = "0.0.0.0"
PORT = 5000
MAX_PLAYERS = 4
ROUNDS = 2
ANSWER_TIMEOUT = 30  # seconds

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind((HOST, PORT))

print(f"Server started on {HOST}:{PORT}")

clients = {}  # addr -> name
scores = {}   # name -> score


# -----------------------------
# Load Questions
# -----------------------------
def load_questions():
    try:
        with open("questions.json", "r") as f:
            return json.load(f)
    except:
        # fallback questions
        return [
            {
                "prompt": "What does HTTP stand for?",
                "choices": [
                    "HyperText Transfer Protocol",
                    "High Text Transfer Protocol",
                    "Hyper Tool Transfer Process",
                    "None"
                ],
                "answer": 0
            },

            {
                "prompt": "Which OSI layer is responsible for IP addressing and routing?",
                "choices": ["Transport", "Network", "Data Link", "Session"],
                "answer": 1
            },

            {
                "prompt": "What protocol is used to assign IP addresses automatically?",
                "choices": ["DNS", "HTTP", "DHCP", "FTP"],
                "answer": 2
            },

            {
                "prompt": "Which device operates at Layer 2 of the OSI model?",
                "choices": ["Router", "Switch", "Firewall", "Modem"],
                "answer": 1
            },

            {
                "prompt": "What does DNS do?",
                "choices": [
                "Assigns IP addresses",
                "Translates domain names to IP addresses",
                "Encrypts data",
                "Routes packets"
                ],
                "answer": 1
            },

            {
                "prompt": "Which protocol is used to send email?",
                "choices": ["SMTP", "SNMP", "FTP", "ARP"],
                "answer": 0
            },

            {
                "prompt": "What is the default port for HTTP?",
                "choices": ["21", "80", "443", "25"],
                "answer": 1
            },

            {
                "prompt": "Which layer of the OSI model handles encryption?",
                "choices": ["Presentation", "Session", "Transport", "Application"],
                "answer": 0
            },

            {
                "prompt": "What does TCP provide?",
                "choices": [
                "Fast but unreliable transmission",
                "Reliable and ordered delivery",
                "IP addressing",
                "Routing"
                ],
                "answer": 1
            },

            {
                "prompt": "Which protocol is connectionless?",
                "choices": ["TCP", "UDP", "FTP", "SMTP"],
                "answer": 1

            },

            {
                "prompt": "What is the purpose of ARP?",
                "choices": [
                "Translate IP to MAC address",
                "Translate MAC to IP address",
                "Assign IP addresses",
                "Encrypt data"
                ],
                "answer": 0
            },

            {
                "prompt": "Which port does HTTPS use?",
                "choices": ["80", "443", "21", "110"],
                "answer": 1
            },

            {
                "prompt": "What device connects different networks together?",
                "choices": ["Switch", "Router", "Hub", "Bridge"],
                "answer": 1
            },

            {
                "prompt": "Which protocol is used for secure remote login?",
                "choices": ["Telnet", "SSH", "FTP", "HTTP"],
                "answer": 1
            },

            {
                "prompt": "What does a subnet mask do?",
                "choices": [
                "Encrypts traffic",
                "Identifies network and host portions",
                "Assigns IP addresses",
                "Routes packets"
                ],
                "answer": 1
            },

            {
                "prompt": "Which layer is responsible for error detection?",
                "choices": ["Physical", "Data Link", "Application", "Session"],
                "answer": 1
            },

            {
                "prompt": "What is the binary equivalent of decimal 255?",
                "choices": ["11111111", "00000000", "10101010", "11001100"],
                "answer": 0
            },

            {
                "prompt": "Which IP address class has the range 192-223?",
                "choices": ["Class A", "Class B", "Class C", "Class D"],
                "answer": 2
            },

            {
                "prompt": "What is the loopback IP address?",
                "choices": ["192.168.1.1", "127.0.0.1", "10.0.0.1", "8.8.8.8"],
                "answer": 1
            },

            {
                "prompt": "Which protocol is used to retrieve email?",
                "choices": ["SMTP", "POP3", "DNS", "ARP"],
                "answer": 1
            },

            {
                "prompt": "What does a firewall do?",
                "choices": [
                "Routes traffic",
                "Filters traffic based on rules",
                "Assigns IP addresses",
                "Translates domain names"
                ],
                "answer": 1
            },

            {
                "prompt": "What is 2 + 2?",
                "choices": ["3", "4", "5", "6"],
                "answer": 1
            },
            
            {
                "prompt": "Which language is used for sockets in this project?",
                "choices": ["Java", "Python", "C++", "Go"],
                "answer": 1
            }
        ]


questions = load_questions()


# -----------------------------
# Send message helper
# -----------------------------
def send(addr, message):
    server.sendto(message.encode(), addr)


def broadcast(message):
    for addr in clients:
        send(addr, message)


# -----------------------------
# Player Join Phase
# -----------------------------
def wait_for_players():
    print("Waiting for players to join...")

    while len(clients) < MAX_PLAYERS:
        data, addr = server.recvfrom(1024)
        msg = data.decode()

        if msg.startswith("JOIN"):
            name = msg.split("|")[1]

            if addr not in clients:
                clients[addr] = name
                scores[name] = 0

                print(f"{name} joined from {addr}")
                send(addr, "WELCOME")

                broadcast(f"MESSAGE|{name} joined the game")

        if len(clients) >= 2:
            break  # minimum players to start

    print("Starting game...")


# -----------------------------
# Receive answers
# -----------------------------
answers = {}
lock = threading.Lock()


def listen_for_answers():
    global answers

    while True:
        data, addr = server.recvfrom(1024)
        msg = data.decode()

        if msg.startswith("ANSWER"):
            parts = msg.split("|")
            name = parts[1]
            answer = int(parts[2])

            with lock:
                if name not in answers:
                    answers[name] = answer


# -----------------------------
# Game Logic
# -----------------------------
def run_game():
    global answers

    listener = threading.Thread(target=listen_for_answers, daemon=True)
    listener.start()

    for round_num in range(ROUNDS):
        print(f"Round {round_num + 1}")

        for q in random.sample(questions, len(clients)):
            answers = {}

            # Send question
            question_msg = f"QUESTION|{q['prompt']}"
            for choice in q["choices"]:
                question_msg += f"|{choice}"

            broadcast(question_msg)

            # Wait for answers
            start_time = time.time()

            while time.time() - start_time < ANSWER_TIMEOUT:
                with lock:
                    if len(answers) >= len(clients):
                        break
                time.sleep(0.5)

            # Evaluate answers
            correct_index = q["answer"]
            winner = None

            for name, ans in answers.items():
                if ans == correct_index:
                    winner = name
                    scores[name] += 1
                    break  # first correct wins

            if winner:
                broadcast(f"RESULT|{winner}|correct")
            else:
                correct_text = q["choices"][correct_index]
                broadcast(f"RESULT|None|Correct answer: {correct_text}")

            # Send score update
            score_msg = "SCORE"
            for name, score in scores.items():
                score_msg += f"|{name}:{score}"

            broadcast(score_msg)

            time.sleep(2)

    # Game Over
    final_msg = "GAMEOVER"
    for name, score in scores.items():
        final_msg += f"|{name}:{score}"

    broadcast(final_msg)
    print("Game finished!")


# -----------------------------
# Main
# -----------------------------
wait_for_players()
run_game()
