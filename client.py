import socket
import sys
import threading

# ============================================================
# // CONFIG SECTION - EASY TO CHANGE
# ============================================================

# // Change this if your server runs on a different computer
SERVER_HOST = "127.0.0.1"

# // TCP is used for the first connection / handshake only
TCP_PORT = 5000

# // UDP is used for the actual live quiz game
UDP_PORT = 5001

# // Buffer size for incoming messages
BUFFER_SIZE = 1024

# // Socket timeout in seconds
SOCKET_TIMEOUT = 100

# // Turn this off later if you do not want debug messages
DEBUG_MODE = False


# ============================================================
# // GLOBAL VARIABLES
# ============================================================

player_name = ""
player_id = ""
server_udp_address = None
client_running = True


# ============================================================
# // HELPER FUNCTIONS
# ============================================================

def debug_print(message):
    # // Show debug messages only when DEBUG_MODE is True
    if DEBUG_MODE:
        print(f"[DEBUG] {message}")


def safe_input(prompt_text):
    # // Read keyboard input safely and exit cleanly on Ctrl + C
    try:
        return input(prompt_text).strip()
    except KeyboardInterrupt:
        print("\nClient closed by user.")
        sys.exit(0)


def parse_message(message):
    # // Split messages using the | separator agreed on by the group
    return message.strip().split("|")


# ============================================================
# // TCP HANDSHAKE FUNCTIONS
# ============================================================

def connect_tcp():
    # // Create a TCP socket and connect to the server
    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.settimeout(SOCKET_TIMEOUT)
        tcp_socket.connect((SERVER_HOST, TCP_PORT))
        print("Connected to server using TCP.")
        return tcp_socket
    except Exception as error:
        print(f"Could not connect to TCP server: {error}")
        return None


def perform_tcp_handshake(tcp_socket, name):
    # // Send JOIN over TCP
    # // The server should reply with: WELCOME|player_name|player_id|udp_port
    global player_id, server_udp_address

    try:
        join_message = f"JOIN|{name}"
        tcp_socket.send(join_message.encode())
        debug_print(f"Sent TCP join message: {join_message}")

        response = tcp_socket.recv(BUFFER_SIZE).decode()
        debug_print(f"Received TCP response: {response}")

        parts = parse_message(response)

        if len(parts) == 4 and parts[0] == "WELCOME":
            confirmed_name = parts[1]
            player_id = parts[2]
            udp_port_from_server = int(parts[3])
            server_udp_address = (SERVER_HOST, udp_port_from_server)

            print(f"Welcome, {confirmed_name}!")
            print(f"Your player ID is: {player_id}")
            print(f"Use UDP port: {udp_port_from_server}")
            return True

        elif len(parts) >= 2 and parts[0] == "ERROR":
            print(f"Server error: {parts[1]}")
            return False

        else:
            print("Handshake failed: invalid server response.")
            return False

    except Exception as error:
        print(f"TCP handshake failed: {error}")
        return False


# ============================================================
# // UDP SETUP FUNCTIONS
# ============================================================

def setup_udp_socket():
    # // Create a UDP socket for live game traffic
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(SOCKET_TIMEOUT)

        # // Bind to any available local UDP port
        # // This lets the OS choose a free port automatically
        udp_socket.bind(("", 0))

        local_ip, local_port = udp_socket.getsockname()
        debug_print(f"UDP socket ready on local port {local_port}")
        return udp_socket

    except Exception as error:
        print(f"Could not create UDP socket: {error}")
        return None


def register_udp(udp_socket):
    # // Tell the server which UDP address this client will use
    # // Server should reply with: UDP_OK|player_id
    try:
        ready_message = f"UDP_READY|{player_id}|{player_name}"
        udp_socket.sendto(ready_message.encode(), server_udp_address)
        debug_print(f"Sent UDP ready message: {ready_message}")

        response, _ = udp_socket.recvfrom(BUFFER_SIZE)
        response = response.decode()
        debug_print(f"Received UDP response: {response}")

        parts = parse_message(response)

        if len(parts) == 2 and parts[0] == "UDP_OK":
            print("UDP connection confirmed. Waiting for the game to start...")
            return True
        else:
            print("UDP registration failed.")
            return False

    except socket.timeout:
        print("UDP registration timed out.")
        return False
    except Exception as error:
        print(f"UDP registration error: {error}")
        return False


# ============================================================
# // DISPLAY FUNCTIONS
# ============================================================

def display_question(parts):
    # // Expected format:
    # // QUESTION|question_id|question_text|choice1|choice2|choice3|choice4
    if len(parts) < 7:
        print("Received invalid question format.")
        return None

    question_id = parts[1]
    question_text = parts[2]
    choices = parts[3:7]

    print("\n" + "=" * 50)
    print(f"Question {question_id}")
    print(question_text)
    print("-" * 50)

    for index, choice in enumerate(choices, start=1):
        print(f"{index}. {choice}")

    print("=" * 50)
    return question_id


def display_scoreboard(parts):
    # // Example: SCORE|Adeel:2|Justin:1
    print("\nCurrent Scores")
    print("-" * 30)
    for item in parts[1:]:
        print(item)
    print("-" * 30)

def display_leaderboard(parts):
    # // Example: LEADERBOARD|Adeel:5|Jasmeet:3
    print("\nCUMULATIVE LEADERBOARD")
    print("-" * 30)

    for item in parts[1:]:
        print(item)

    print("-" * 30)

def display_game_over(parts):
    # // Example: GAMEOVER|Adeel:3|Justin:2
    print("\n" + "=" * 50)
    print("GAME OVER")
    print("=" * 50)
    for item in parts[1:]:
        print(item)
    print("=" * 50)


# ============================================================
# // ANSWER FUNCTIONS
# ============================================================
def timed_input(prompt_text, timeout_seconds):
    # // This function gives the user only a limited time to type an answer
    # // If time runs out, it returns None

    user_input = {"value": None}

    def read_input():
        try:
            user_input["value"] = input(prompt_text).strip()
        except EOFError:
            user_input["value"] = None

    input_thread = threading.Thread(target=read_input, daemon=True)
    input_thread.start()
    input_thread.join(timeout_seconds)

    if input_thread.is_alive():
        return None

    return user_input["value"]

def get_player_answer():
    # // Give the player 30 seconds to answer
    # // Change this number if you want the client-side wait time to match a different server timer
    answer_timeout = 30

    print(f"You have {answer_timeout} seconds to answer.")

    while True:
        answer = timed_input("Enter your answer (1-4): ", answer_timeout)

        # // If time ran out, return None so the client skips sending an answer
        if answer is None:
            print("\nTime is up. No answer was submitted.")
            return None

        if answer in ["1", "2", "3", "4"]:
            return answer

        print("Invalid input. Please enter 1, 2, 3, or 4.")
        
def send_answer(udp_socket, question_id, answer):
    # // Send the chosen answer back to the server using UDP
    try:
        answer_message = f"ANSWER|{player_id}|{player_name}|{question_id}|{answer}"
        udp_socket.sendto(answer_message.encode(), server_udp_address)
        debug_print(f"Sent UDP answer: {answer_message}")
    except Exception as error:
        print(f"Failed to send answer: {error}")


# ============================================================
# // MAIN GAME LOOP
# ============================================================

def handle_game_loop(udp_socket):
    # // Keep listening for messages until the game ends
    global client_running

    while client_running:
        try:
            data, _ = udp_socket.recvfrom(BUFFER_SIZE)
            message = data.decode()
            debug_print(f"Received UDP message: {message}")

            parts = parse_message(message)
            message_type = parts[0]

            if message_type == "START":
                if len(parts) > 1:
                    print(f"\n{parts[1]}")
                else:
                    print("\nThe game is starting now!")

            elif message_type == "QUESTION":
                question_id = display_question(parts)
                if question_id is not None:
                    answer = get_player_answer()

                    # // Only send an answer if the player answered before time ran out
                    if answer is not None:
                        send_answer(udp_socket, question_id, answer)

            elif message_type == "RESULT":
                if len(parts) > 1:
                    print(f"\nResult: {parts[1]}")

            elif message_type == "INFO":
                if len(parts) > 1:
                    print(parts[1])

            elif message_type == "SCORE":
                display_scoreboard(parts)

            elif message_type == "LEADERBOARD":
                display_leaderboard(parts)

            elif message_type == "TIEBREAKER":
                if len(parts) > 1:
                    print(f"\n{parts[1]}")
                else:
                    print("\nTiebreaker round starting!")

            elif message_type == "GAMEOVER":
                display_game_over(parts)

    # // Do not close immediately because leaderboard may arrive right after
            elif message_type == "EXIT":
                if len(parts) > 1:
                    print(parts[1])
                else:
                    print("Server closed the session.")
                client_running = False
            else:
                print(f"Unknown message from server: {message}")

        except socket.timeout:
            print("No message received from server. Still waiting...")
        except Exception as error:
            print(f"Game loop error: {error}")
            client_running = False


# ============================================================
# // MAIN PROGRAM
# ============================================================

def main():
    global player_name, SERVER_HOST, TCP_PORT, UDP_PORT

    print("=" * 60)
    print("WELCOME TO THE MULTIPLAYER QUIZ GAME CLIENT")
    print("=" * 60)

    # // Press Enter to keep the default values
    host_input = safe_input(f"Enter server IP/host [{SERVER_HOST}]: ")
    if host_input:
        SERVER_HOST = host_input

    tcp_input = safe_input(f"Enter TCP port [{TCP_PORT}]: ")
    if tcp_input:
        TCP_PORT = int(tcp_input)

    udp_input = safe_input(f"Enter default UDP port [{UDP_PORT}] (optional): ")
    if udp_input:
        UDP_PORT = int(udp_input)

    player_name = safe_input("Enter your player name: ")

    # // Step 1: connect over TCP
    tcp_socket = connect_tcp()
    if tcp_socket is None:
        return

    # // Step 2: do the TCP handshake
    handshake_ok = perform_tcp_handshake(tcp_socket, player_name)
    if not handshake_ok:
        tcp_socket.close()
        return

    # // Step 3: prepare UDP
    udp_socket = setup_udp_socket()
    if udp_socket is None:
        tcp_socket.close()
        return

    # // Step 4: register this client for UDP gameplay
    udp_ok = register_udp(udp_socket)
    if not udp_ok:
        udp_socket.close()
        tcp_socket.close()
        return

    # // TCP is finished after the handshake for this version of the game
    tcp_socket.close()

    # // Step 5: wait for gameplay messages
    handle_game_loop(udp_socket)

    # // Step 6: close cleanly
    udp_socket.close()
    print("Client closed.")


if __name__ == "__main__":
    main()
