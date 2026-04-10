import json
from pathlib import Path
from datetime import datetime

# ============================================================
# // FILE PATHS
# ============================================================

QUESTIONS_FILE = Path("questions.json")
LEADERBOARD_FILE = Path("leaderboard.json")
HISTORY_FILE = Path("games_history.json")


# ============================================================
# // JSON HELPERS
# ============================================================

def load_json(path, default):
    # // If the file does not exist yet, create it with default data
    if not path.exists():
        save_json(path, default)
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        # // If the file is empty or broken, reset it to default
        save_json(path, default)
        return default


def save_json(path, data):
    # // Save Python data into a JSON file
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


# ============================================================
# // QUESTION MANAGEMENT
# ============================================================

def get_questions():
    # // Load all questions from the questions database
    return load_json(QUESTIONS_FILE, default=[])


# ============================================================
# // LEADERBOARD MANAGEMENT
# ============================================================

def get_leaderboard():
    # // leaderboard.json format:
    # // {
    # //   "Adeel": {"games_played": 2, "cumulative_score": 5},
    # //   "Jasmeet": {"games_played": 2, "cumulative_score": 3}
    # // }
    return load_json(LEADERBOARD_FILE, default={})


def update_leaderboard(player_name, score):
    # // Update one player's cumulative leaderboard entry
    leaderboard = get_leaderboard()

    if player_name not in leaderboard:
        leaderboard[player_name] = {
            "games_played": 0,
            "cumulative_score": 0
        }

    leaderboard[player_name]["games_played"] += 1
    leaderboard[player_name]["cumulative_score"] += score

    save_json(LEADERBOARD_FILE, leaderboard)


def get_sorted_leaderboard():
    # // Return leaderboard sorted by cumulative score from high to low
    leaderboard = get_leaderboard()

    sorted_items = sorted(
        leaderboard.items(),
        key=lambda item: item[1]["cumulative_score"],
        reverse=True
    )

    return sorted_items


# ============================================================
# // GAME HISTORY MANAGEMENT
# ============================================================

def add_game_history(final_scores):
    # // Save one completed game into games_history.json
    # // final_scores should look like:
    # // {"Adeel": 3, "Jasmeet": 2}
    history = load_json(HISTORY_FILE, default=[])

    game_record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": final_scores
    }

    history.append(game_record)
    save_json(HISTORY_FILE, history)


def get_game_history():
    # // Return all saved games
    return load_json(HISTORY_FILE, default=[])