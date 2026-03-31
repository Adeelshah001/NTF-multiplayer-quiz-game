# Justin L. Section

import json # Allow JSON files and functions
path from pathlib # Check if the database file already exists

# File paths 
QUESTIONS_FILE = path("questions.json") 
LEADERBOARD_FILE = path("leaderboard.json")
HISTORY_FILE = path("game_history.json")

# --- JSON helpers ---

# Loading the JSON files
def load_json(path, default):

  # If the path doesnt exist create with default data
  if not path.exists():
    save_json(path, default)
    return default

  # Load JSON file if the path exist
  with open(path, "r", encoding="utf-8) as f:
    return json.load(f)

# Save JSON data to file 
def save_json(path,data):
  with open(path, "w", encoding="utf-8) as f:

# --- Question Management ---

# Reciving questions form the questions.json file
def get_questions():
  return load_json(QUESTIONS_FILE, default=[])

# Showing qestions to client
def add_question(question, a, b, c, d, correct):
  questions = get_questions()

  # ADding the choices of the questions
  queustions.append({
    "question": question, 
    "A": a,
    "B": b,
    "C": c,
    "D": d,
    "correct": correct
  })


  
            


