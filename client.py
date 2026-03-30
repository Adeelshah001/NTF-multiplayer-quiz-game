import socket
import threading
import sys

# ============================================================
# // CONFIG SECTION - EASY TO CHANGE
# ============================================================

# // Change this if your server runs on a different machine
SERVER_HOST = "127.0.0.1"

# // Change this TCP port if your server uses a different one
TCP_PORT = 5000

# // Change this UDP port if your server uses a different one
UDP_PORT = 5001

# // Buffer size for receiving messages
BUFFER_SIZE = 1024

# // How long TCP/UDP sockets should wait before timing out
SOCKET_TIMEOUT = 30

# // Set to True if you want extra debug prints while testing
DEBUG_MODE = True


# ============================================================
# // GLOBAL VARIABLES
# ============================================================

# // These will be shared across functions
player_name = ""
player_id = ""
server_udp_address = None

# // This controls whether the client should keep running
client_running = True


# ============================================================
# // HELPER FUNCTIONS
# ============================================================

def debug_print(message):
    # // Print debug messages only if DEBUG_MODE is turned on
    if DEBUG_MODE:
        print(f"[DEBUG] {message}")


def safe_input(prompt_text):
    # // Read user input safely
    try:
        return input(prompt_text).strip()
    except KeyboardInterrupt:
        print("\nClient closed by user.")
        sys.exit(0)


def parse_message(message):
    # // Split incoming messages using | as the separator
    # // Example: WELCOME|Adeel|player_1|5001
    return message.strip().split("|")


# ============================================================
# // TCP HANDSHAKE FUNCTIONS
# ============================================================

def connect_tcp():
    # // Create a TCP socket and connect to the server
    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.settimeout(SOCKET_TIMEOUT)

        debug_print(f"Connecting to TCP server at {SERVER_HOST}:{TCP_PORT} ...")
        tcp_socket.connect((SERVER_HOST, TCP_PORT))

        print("Connected to server using TCP.")
        return tcp_socket

    except Exception as e:
        print(f"Could not connect to TCP server: {e}")
        return None


def perform_tcp_handshake(tcp_socket, name):
    # // Send player join request to the server
    # // The server should reply with player info and the UDP port
    global player_id, server_udp_address

    try:
        join_message = f"JOIN|{name}"
        tcp_socket.send(join_message.encode())

        debug_print(f"Sent TCP join message: {join_message}")

        response = tcp_socket.recv(BUFFER_SIZE).decode()
        debug_print(f"Received TCP response: {response}")

        parts = parse_message(response)

        # // Expected format:
        # // WELCOME|player_name|player_id|udp_port
        if len(parts) == 4 and parts[0] == "WELCOME":
            confirmed_name = parts[1]
            player_id = parts[2]
            udp_port_from_server = int(parts[3])

            server_udp_address = (SERVER_HOST, udp_port_from_server)

            print(f"Welcome, {confirmed_name}!")
            print(f"Your player ID is: {player_id}")
            print(f"Game UDP port is: {udp_port_from_server}")

            return True
        else:
            print("Handshake failed: invalid server response.")
            return False

    except Exception as e:
        print(f"TCP handshake failed: {e}")
        return False


# ============================================================
# // UDP SETUP FUNCTIONS
# ============================================================

def setup_udp_socket():
    # // Create a UDP socket for the live game messages
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(SOCKET_TIMEOUT)

        # // Bind to any available local UDP port
        udp_socket.bind(("", 0))

        local_ip, local_port = udp_socket.getsockname()
        debug_print(f"UDP socket ready on local port {local_port}")

        return udp_socket

    except Exception as e:
        print(f"Could not create UDP socket: {e}")
        return None


def register_udp(udp_socket):
    # // Send one UDP message so the server knows this client's UDP address
    # // This is the simple TCP -> UDP handoff
    try:
        ready_message = f"UDP_READY|{player_id}|{player_name}"
        udp_socket.sendto(ready_message.encode(), server_udp_address)

        debug_print(f"Sent UDP ready message: {ready_message}")

        response, _ = udp_socket.recvfrom(BUFFER_SIZE)
        response = response.decode()

        debug_print(f"Received UDP response: {response}")

        parts = parse_message(response)

        # // Expected format:
        # // UDP_OK|player_id
        if len(parts) == 2 and parts[0] == "UDP_OK":
            print("UDP connection confirmed. Waiting for the game to start...")
            return True
        else:
            print("UDP registration failed.")
            return False

    except socket.timeout:
        print("UDP registration timed out.")
        return False
    except Exception as e:
        print(f"UDP registration error: {e}")
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

    for i, choice in enumerate(choices, start=1):
        print(f"{i}. {choice}")

    print("=" * 50)

    return question_id


def display_scoreboard(parts):
    # // Example:
    # // SCORE|Adeel:2|Justin:1|Yue:0
    print("\nCurrent Scores:")
    print("-" * 30)

    for item in parts[1:]:
        print(item)

    print("-" * 30)


def display_game_over(parts):
    # // Example:
    # // GAMEOVER|Adeel:3|Justin:2|Yue:1
    print("\n" + "=" * 50)
    print("GAME OVER")
    print("=" * 50)

    for item in parts[1:]:
        print(item)

    print("=" * 50)


# ============================================================
# // INPUT FUNCTIONS
# ============================================================

def get_player_answer():
    # // Let the player enter 1, 2, 3, or 4
    # // Keeps asking until valid input is entered
    while True:
        answer = safe_input("Enter your answer (1-4): ")

        if answer in ["1", "2", "3", "4"]:
            return answer

        print("Invalid input. Please enter 1, 2, 3, or 4.")


def send_answer(udp_socket, question_id, answer):
    # // Send the player's answer back to the server using UDP
    try:
        answer_message = f"ANSWER|{player_id}|{player_name}|{question_id}|{answer}"
        udp_socket.sendto(answer_message.encode(), server_udp_address)

        debug_print(f"Sent UDP answer: {answer_message}")

    except Exception as e:
        print(f"Failed to send answer: {e}")


# ============================================================
# // MAIN GAME LOOP
# ============================================================

def handle_game_loop(udp_socket):
    # // Listen for UDP messages from the server during the game
    # // The server is the authority and tells the client what happens next
    global client_running

    while client_running:
        try:
            data, _ = udp_socket.recvfrom(BUFFER_SIZE)
            message = data.decode()
            debug_print(f"Received UDP message: {message}")

            parts = parse_message(message)
            message_type = parts[0]

            if message_type == "WAITING":
                # // Example: WAITING|Waiting for more players...
                if len(parts) > 1:
                    print(parts[1])

            elif message_type == "START":
                # // Example: START|The game is starting now!
                if len(parts) > 1:
                    print(f"\n{parts[1]}")
                else:
                    print("\nThe game is starting now!")

            elif message_type == "QUESTION":
                question_id = display_question(parts)

                if question_id is not None:
                    answer = get_player_answer()
                    send_answer(udp_socket, question_id, answer)

            elif message_type == "RESULT":
                # // Example:
                # // RESULT|Correct
                # // RESULT|Incorrect
                # // RESULT|Too late
                if len(parts) > 1:
                    print(f"\nResult: {parts[1]}")

            elif message_type == "INFO":
                # // Generic server message
                if len(parts) > 1:
                    print(parts[1])

            elif message_type == "TIMEUP":
                # // Example: TIMEUP|No more answers accepted
                if len(parts) > 1:
                    print(parts[1])
                else:
                    print("Time is up.")

            elif message_type == "SCORE":
                display_scoreboard(parts)

            elif message_type == "TIEBREAKER":
                # // Example: TIEBREAKER|A tie was detected. Final question coming up.
                if len(parts) > 1:
                    print(f"\n{parts[1]}")
                else:
                    print("\nTiebreaker round starting!")

            elif message_type == "GAMEOVER":
                display_game_over(parts)
                client_running = False

            elif message_type == "EXIT":
                # // Server tells the client to close
                if len(parts) > 1:
                    print(parts[1])
                else:
                    print("Server closed the session.")
                client_running = False

            else:
                print(f"Unknown message from server: {message}")

        except socket.timeout:
            print("No message received from server. Still waiting...")
        except Exception as e:
            print(f"Game loop error: {e}")
            client_running = False


# ============================================================
# // MAIN PROGRAM
# ============================================================

def main():
    global player_name, SERVER_HOST, TCP_PORT, UDP_PORT

    print("=" * 60)
    print("WELCOME TO THE MULTIPLAYER QUIZ GAME CLIENT")
    print("=" * 60)

    # // Ask the user for connection details
    # // Press Enter to use the default values above
    host_input = safe_input(f"Enter server IP/host [{SERVER_HOST}]: ")
    if host_input:
        SERVER_HOST = host_input

    tcp_input = safe_input(f"Enter TCP port [{TCP_PORT}]: ")
    if tcp_input:
        TCP_PORT = int(tcp_input)

    # // This line is here in case your group wants to manually keep UDP configurable too
    udp_input = safe_input(f"Enter default UDP port [{UDP_PORT}] (optional): ")
    if udp_input:
        UDP_PORT = int(udp_input)

    player_name = safe_input("Enter your player name: ")

    # // Step 1: connect with TCP
    tcp_socket = connect_tcp()
    if tcp_socket is None:
        return

    # // Step 2: do the handshake
    handshake_ok = perform_tcp_handshake(tcp_socket, player_name)
    if not handshake_ok:
        tcp_socket.close()
        return

    # // Step 3: set up UDP
    udp_socket = setup_udp_socket()
    if udp_socket is None:
        tcp_socket.close()
        return

    # // If your server does not send the UDP port during TCP handshake
    # // and instead you want to force the UDP_PORT above,
    # // uncomment the next line:
    #
    # // server_udp_address = (SERVER_HOST, UDP_PORT)

    # // Step 4: register this UDP client with the server
    udp_ok = register_udp(udp_socket)
    if not udp_ok:
        udp_socket.close()
        tcp_socket.close()
        return

    # // TCP handshake is done, so TCP can be closed if your group wants only UDP after setup
    # // If your group wants to keep TCP open for lobby/control messages, comment this out
    tcp_socket.close()

    # // Step 5: enter the gameplay loop
    handle_game_loop(udp_socket)

    # // Step 6: clean shutdown
    udp_socket.close()
    print("Client closed.")


if __name__ == "__main__":
    main()