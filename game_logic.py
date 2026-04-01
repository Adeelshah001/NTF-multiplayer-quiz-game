"""
game_logic.py
-------------
Rule engine for the multiplayer quiz game.

Final confirmed rules:
1. UDP only (networking handled elsewhere).
2. Host/server also plays.
3. Each round lasts the full time limit.
4. During the round, answers are only recorded.
5. When time expires, the fastest correct player gets 1 point.
6. All other players get 0.
7. If nobody answers correctly, no point is awarded.
8. If top score is tied after normal rounds, tie-breaker begins.
9. Only tied top players participate in tie-breaker.
10. Tie-breaker uses the same full-timer / fastest-correct rule.
11. There must be exactly one final winner.

This module does NOT:
- create sockets
- send/receive UDP packets
- read/write JSON files

It only handles game rules and game state.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# STATE CONSTANTS
# ============================================================

WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"
READY = "READY"
QUESTION_ACTIVE = "QUESTION_ACTIVE"
ROUND_RESULT_READY = "ROUND_RESULT_READY"
TIEBREAKER_ACTIVE = "TIEBREAKER_ACTIVE"
GAME_OVER = "GAME_OVER"


# ============================================================
# MAIN GAME LOGIC CLASS
# ============================================================

class QuizGameLogic:
    """
    Main rule engine for the quiz game.
    """

    def __init__(self, round_time_limit: int = 30) -> None:
        self.round_time_limit = round_time_limit
        self.reset_all()

    # --------------------------------------------------------
    # RESET / INITIALIZATION
    # --------------------------------------------------------

    def reset_all(self) -> None:
        """
        Reset the entire game state.
        """
        self.players: Dict[str, Dict[str, Any]] = {}
        self.player_order: List[str] = []
        self.status: str = WAITING_FOR_PLAYERS

        self.total_questions: int = 0
        self.current_question_index: int = 0

        self.current_round: Optional[Dict[str, Any]] = None

        self.tiebreaker_mode: bool = False
        self.tied_players: List[str] = []
        self.final_winner: Optional[str] = None

        self.normal_rounds_completed: int = 0
        self.tiebreaker_rounds_completed: int = 0

        self.last_round_result: Optional[Dict[str, Any]] = None

    def initialize_game(self, player_names: List[str], total_questions: int) -> Dict[str, Any]:
        """
        Initialize the game with the given players.

        Args:
            player_names: list of unique player names
            total_questions: number of normal questions to be played

        Returns:
            summary dict of initialized game state
        """
        self.reset_all()

        cleaned_names: List[str] = []
        seen = set()

        for name in player_names:
            if not isinstance(name, str):
                continue
            clean = name.strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            cleaned_names.append(clean)

        if len(cleaned_names) < 2:
            raise ValueError("At least 2 unique players are required to start the game.")

        if total_questions <= 0:
            raise ValueError("total_questions must be greater than 0.")

        self.player_order = cleaned_names
        self.total_questions = total_questions

        for name in cleaned_names:
            self.players[name] = {
                "score": 0,
                "connected": True,
            }

        self.status = READY

        return {
            "status": self.status,
            "players": cleaned_names,
            "total_questions": total_questions,
            "round_time_limit": self.round_time_limit,
        }

    def start_game(self) -> Dict[str, Any]:
        """
        Mark the game as ready to begin normal rounds.
        """
        if self.status not in [READY]:
            raise RuntimeError(f"Cannot start game from status {self.status}")

        return {
            "status": self.status,
            "message": "Game initialized and ready to start rounds."
        }

    # --------------------------------------------------------
    # ROUND SETUP
    # --------------------------------------------------------

    def start_new_round(
        self,
        question_obj: Dict[str, Any],
        eligible_players: Optional[List[str]] = None,
        round_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Start a normal round or a tie-breaker round.

        Args:
            question_obj: question dictionary
            eligible_players: if None, all players are eligible;
                              otherwise only these players may answer
            round_id: optional external round identifier

        Returns:
            round metadata
        """
        if self.final_winner is not None:
            raise RuntimeError("Game is already over. Cannot start a new round.")

        parsed_question = self._parse_question(question_obj)

        if eligible_players is None:
            eligible = list(self.players.keys())
        else:
            eligible = [p for p in eligible_players if p in self.players]
            if not eligible:
                raise ValueError("No valid eligible players provided for this round.")

        is_tiebreaker = self.tiebreaker_mode or parsed_question["type"] == "tiebreaker"

        self.current_round = {
            "round_id": round_id if round_id is not None else (
                f"TB-{self.tiebreaker_rounds_completed + 1}" if is_tiebreaker
                else f"Q-{self.current_question_index + 1}"
            ),
            "question_id": parsed_question["id"],
            "question_text": parsed_question["question"],
            "choices": parsed_question["choices"],
            "correct_index": parsed_question["correct_index"],  # 0..3
            "correct_letter": self._index_to_letter(parsed_question["correct_index"]),
            "type": parsed_question["type"],
            "status": TIEBREAKER_ACTIVE if is_tiebreaker else QUESTION_ACTIVE,
            "start_time": time.time(),
            "time_limit": self.round_time_limit,
            "eligible_players": eligible,
            "answers": {},       # player_name -> answer record
            "winner": None,
            "winner_answer_index": None,
            "winner_timestamp": None,
            "closed_at": None,
        }

        self.status = self.current_round["status"]
        self.last_round_result = None

        return {
            "status": self.status,
            "round_id": self.current_round["round_id"],
            "question_id": self.current_round["question_id"],
            "question_text": self.current_round["question_text"],
            "choices": self.current_round["choices"],
            "eligible_players": eligible,
            "time_limit": self.current_round["time_limit"],
            "type": self.current_round["type"],
        }

    def start_tiebreaker_round(self, question_obj: Dict[str, Any], tied_players: List[str]) -> Dict[str, Any]:
        """
        Convenience wrapper to start a tie-breaker round.
        """
        valid_tied = [p for p in tied_players if p in self.players]
        if len(valid_tied) < 2:
            raise ValueError("Tie-breaker requires at least 2 valid tied players.")

        self.tiebreaker_mode = True
        self.tied_players = valid_tied

        return self.start_new_round(question_obj, eligible_players=valid_tied)

    # --------------------------------------------------------
    # ANSWER HANDLING
    # --------------------------------------------------------

    def submit_answer(
        self,
        player_name: str,
        answer: Any,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Record one submitted answer during the active round.

        IMPORTANT:
        This function only records the answer.
        It does NOT decide the winner immediately.
        Winner is decided only when close_round() is called.

        Args:
            player_name: player's name
            answer: player answer, accepted forms:
                    0..3, 1..4, "0".."3", "1".."4", "A".."D", "a".."d"
            timestamp: submission time. If None, current time is used.

        Returns:
            result dict
        """
        if self.current_round is None:
            return self._reject("No active round.")

        if self.status not in [QUESTION_ACTIVE, TIEBREAKER_ACTIVE]:
            return self._reject(f"Cannot accept answers while status = {self.status}")

        player_name = player_name.strip()

        if player_name not in self.players:
            return self._reject(f"Unknown player: {player_name}")

        if player_name not in self.current_round["eligible_players"]:
            return self._reject(f"Player {player_name} is not eligible for this round.")

        if player_name in self.current_round["answers"]:
            return self._reject(f"Player {player_name} already answered this round.")

        normalized_index = self._normalize_answer_to_index(answer)
        if normalized_index is None:
            return self._reject("Invalid answer format. Must map to choices A-D or 1-4.")

        ts = time.time() if timestamp is None else float(timestamp)

        is_correct = normalized_index == self.current_round["correct_index"]

        self.current_round["answers"][player_name] = {
            "answer_raw": answer,
            "answer_index": normalized_index,
            "answer_letter": self._index_to_letter(normalized_index),
            "is_correct": is_correct,
            "timestamp": ts,
        }

        return {
            "accepted": True,
            "player": player_name,
            "answer_index": normalized_index,
            "answer_letter": self._index_to_letter(normalized_index),
            "is_correct": is_correct,
            "message": "Answer recorded."
        }

    # --------------------------------------------------------
    # ROUND CLOSING / SCORING
    # --------------------------------------------------------

    def close_round(self) -> Dict[str, Any]:
        """
        Close the current round and decide the fastest correct player.

        Rules:
        - round ends only when timer expires (or server explicitly calls this)
        - among all correct answers, earliest timestamp wins
        - winner gets +1 point
        - all others get 0
        - if no correct answers, nobody gets a point
        """
        if self.current_round is None:
            raise RuntimeError("No current round to close.")

        if self.status not in [QUESTION_ACTIVE, TIEBREAKER_ACTIVE]:
            raise RuntimeError(f"Round cannot be closed from status {self.status}")

        answers = self.current_round["answers"]

        correct_answers: List[Tuple[str, Dict[str, Any]]] = [
            (player, info)
            for player, info in answers.items()
            if info["is_correct"]
        ]

        winner: Optional[str] = None
        winner_info: Optional[Dict[str, Any]] = None

        if correct_answers:
            # earliest correct timestamp wins
            winner, winner_info = min(correct_answers, key=lambda item: item[1]["timestamp"])
            self.players[winner]["score"] += 1

            self.current_round["winner"] = winner
            self.current_round["winner_answer_index"] = winner_info["answer_index"]
            self.current_round["winner_timestamp"] = winner_info["timestamp"]

        self.current_round["closed_at"] = time.time()
        self.status = ROUND_RESULT_READY

        if self.current_round["type"] == "tiebreaker" or self.tiebreaker_mode:
            self.tiebreaker_rounds_completed += 1
        else:
            self.normal_rounds_completed += 1
            self.current_question_index += 1

        result = {
            "round_closed": True,
            "round_id": self.current_round["round_id"],
            "question_id": self.current_round["question_id"],
            "question_text": self.current_round["question_text"],
            "winner": winner,
            "awarded_point": winner is not None,
            "correct_index": self.current_round["correct_index"],
            "correct_letter": self.current_round["correct_letter"],
            "correct_text": self.current_round["choices"][self.current_round["correct_index"]],
            "scores": self.get_scoreboard(),
            "rankings": self.get_rankings(),
            "answers_received": {
                player: {
                    "answer_index": info["answer_index"],
                    "answer_letter": info["answer_letter"],
                    "is_correct": info["is_correct"],
                    "timestamp": info["timestamp"],
                }
                for player, info in answers.items()
            },
            "type": self.current_round["type"],
        }

        self.last_round_result = result

        # If this was a tie-breaker round and a winner exists, end the game immediately.
        if self.tiebreaker_mode and winner is not None:
            self.final_winner = winner
            self.status = GAME_OVER

        return result

    # --------------------------------------------------------
    # SCOREBOARD / RANKINGS
    # --------------------------------------------------------

    def get_scoreboard(self) -> Dict[str, int]:
        """
        Return raw scoreboard.
        """
        return {name: self.players[name]["score"] for name in self.player_order}

    def get_rankings(self) -> List[Tuple[str, int]]:
        """
        Return sorted rankings:
        1) score descending
        2) name ascending as stable fallback
        """
        return sorted(
            [(name, info["score"]) for name, info in self.players.items()],
            key=lambda item: (-item[1], item[0].lower())
        )

    # --------------------------------------------------------
    # TIE-BREAKER / GAME END
    # --------------------------------------------------------

    def check_tiebreaker_needed(self) -> Dict[str, Any]:
        """
        Check whether the highest score is tied by multiple players.

        Returns:
            {
                "needed": bool,
                "tied_players": [...],
                "top_score": int
            }
        """
        rankings = self.get_rankings()
        if not rankings:
            return {"needed": False, "tied_players": [], "top_score": 0}

        top_score = rankings[0][1]
        tied_players = [name for name, score in rankings if score == top_score]

        return {
            "needed": len(tied_players) > 1,
            "tied_players": tied_players,
            "top_score": top_score,
        }

    def finalize_normal_game_if_possible(self) -> Dict[str, Any]:
        """
        Call this after all normal rounds are done.

        If top score is unique -> final winner is set.
        If top score is tied -> caller must start tie-breaker.
        """
        tie_info = self.check_tiebreaker_needed()

        if not tie_info["needed"]:
            rankings = self.get_rankings()
            if rankings:
                self.final_winner = rankings[0][0]
                self.status = GAME_OVER
        else:
            self.tiebreaker_mode = True
            self.tied_players = tie_info["tied_players"]

        return {
            "game_over": self.final_winner is not None,
            "final_winner": self.final_winner,
            "tiebreaker_needed": tie_info["needed"],
            "tied_players": tie_info["tied_players"],
            "rankings": self.get_rankings(),
        }

    def is_game_over(self) -> bool:
        return self.final_winner is not None or self.status == GAME_OVER

    def get_final_winner(self) -> Optional[str]:
        return self.final_winner

    # --------------------------------------------------------
    # STATE / STATUS HELPERS
    # --------------------------------------------------------

    def get_game_state(self) -> Dict[str, Any]:
        """
        Return a snapshot of the game state.
        """
        round_snapshot = None
        if self.current_round is not None:
            round_snapshot = {
                "round_id": self.current_round["round_id"],
                "question_id": self.current_round["question_id"],
                "question_text": self.current_round["question_text"],
                "choices": self.current_round["choices"],
                "correct_index": self.current_round["correct_index"],
                "correct_letter": self.current_round["correct_letter"],
                "type": self.current_round["type"],
                "eligible_players": list(self.current_round["eligible_players"]),
                "answer_count": len(self.current_round["answers"]),
                "winner": self.current_round["winner"],
            }

        return {
            "status": self.status,
            "scoreboard": self.get_scoreboard(),
            "rankings": self.get_rankings(),
            "current_question_index": self.current_question_index,
            "total_questions": self.total_questions,
            "normal_rounds_completed": self.normal_rounds_completed,
            "tiebreaker_mode": self.tiebreaker_mode,
            "tied_players": list(self.tied_players),
            "final_winner": self.final_winner,
            "current_round": round_snapshot,
        }

    def get_last_round_result(self) -> Optional[Dict[str, Any]]:
        return self.last_round_result

    def get_time_left(self) -> Optional[float]:
        """
        Return remaining time in current round.
        """
        if self.current_round is None:
            return None

        if self.status not in [QUESTION_ACTIVE, TIEBREAKER_ACTIVE]:
            return 0.0

        elapsed = time.time() - self.current_round["start_time"]
        remaining = self.current_round["time_limit"] - elapsed
        return max(0.0, remaining)

    # --------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------

    def _reject(self, message: str) -> Dict[str, Any]:
        return {
            "accepted": False,
            "message": message
        }

    def _parse_question(self, question_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize supported question formats.

        Supported examples:
        1)
        {
            "prompt": "...",
            "choices": ["a", "b", "c", "d"],
            "answer": 0
        }

        2)
        {
            "id": 1,
            "question": "...",
            "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
            "answer": "B",
            "type": "normal"
        }

        3)
        {
            "question": "...",
            "A": "...", "B": "...", "C": "...", "D": "...",
            "correct": "C"
        }
        """
        if not isinstance(question_obj, dict):
            raise ValueError("Question object must be a dictionary.")

        qid = question_obj.get("id", None)

        # question text
        question_text = (
            question_obj.get("question")
            or question_obj.get("prompt")
            or question_obj.get("text")
        )
        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError("Question object is missing valid question text.")

        question_type = str(question_obj.get("type", "normal")).strip().lower()
        if question_type not in ["normal", "tiebreaker"]:
            question_type = "normal"

        # choices
        choices: Optional[List[str]] = None

        if "choices" in question_obj and isinstance(question_obj["choices"], list):
            if len(question_obj["choices"]) != 4:
                raise ValueError("Question 'choices' list must contain exactly 4 options.")
            choices = [str(c) for c in question_obj["choices"]]

        elif "options" in question_obj and isinstance(question_obj["options"], dict):
            options = question_obj["options"]
            required = ["A", "B", "C", "D"]
            if not all(k in options for k in required):
                raise ValueError("Question 'options' dict must contain A, B, C, D.")
            choices = [str(options["A"]), str(options["B"]), str(options["C"]), str(options["D"])]

        elif all(k in question_obj for k in ["A", "B", "C", "D"]):
            choices = [
                str(question_obj["A"]),
                str(question_obj["B"]),
                str(question_obj["C"]),
                str(question_obj["D"]),
            ]

        if choices is None:
            raise ValueError("Question object must provide 4 choices.")

        # correct answer
        if "answer" in question_obj:
            correct_raw = question_obj["answer"]
        elif "correct" in question_obj:
            correct_raw = question_obj["correct"]
        else:
            raise ValueError("Question object is missing the correct answer.")

        correct_index = self._normalize_correct_to_index(correct_raw)
        if correct_index is None:
            raise ValueError("Question correct answer must map to an index 0..3 or choice A..D / 1..4.")

        return {
            "id": qid,
            "question": question_text.strip(),
            "choices": choices,
            "correct_index": correct_index,
            "type": question_type,
        }

    def _normalize_correct_to_index(self, correct_raw: Any) -> Optional[int]:
        """
        Normalize stored correct answer.
        Accepts:
        - 0..3
        - 1..4
        - "0".."3"
        - "1".."4"
        - "A".."D"
        """
        return self._normalize_answer_to_index(correct_raw)

    def _normalize_answer_to_index(self, answer: Any) -> Optional[int]:
        """
        Normalize incoming answer into index 0..3.

        Accepted inputs:
        - 0,1,2,3
        - 1,2,3,4
        - "0","1","2","3"
        - "1","2","3","4"
        - "A","B","C","D" (case-insensitive)
        """
        if isinstance(answer, int):
            if 0 <= answer <= 3:
                return answer
            if 1 <= answer <= 4:
                return answer - 1
            return None

        if isinstance(answer, str):
            cleaned = answer.strip().upper()

            if cleaned in ["A", "B", "C", "D"]:
                return ord(cleaned) - ord("A")

            if cleaned.isdigit():
                n = int(cleaned)
                if 0 <= n <= 3:
                    return n
                if 1 <= n <= 4:
                    return n - 1

        return None

    def _index_to_letter(self, idx: int) -> str:
        if idx not in [0, 1, 2, 3]:
            return "?"
        return chr(ord("A") + idx)


# ============================================================
# OPTIONAL MODULE-LEVEL SINGLETON
# (Easy to import and use from server.py)
# ============================================================

game = QuizGameLogic()

# Optional convenience wrappers
initialize_game = game.initialize_game
start_game = game.start_game
start_new_round = game.start_new_round
submit_answer = game.submit_answer
close_round = game.close_round
get_scoreboard = game.get_scoreboard
get_rankings = game.get_rankings
check_tiebreaker_needed = game.check_tiebreaker_needed
start_tiebreaker_round = game.start_tiebreaker_round
finalize_normal_game_if_possible = game.finalize_normal_game_if_possible
is_game_over = game.is_game_over
get_final_winner = game.get_final_winner
get_game_state = game.get_game_state
get_last_round_result = game.get_last_round_result
get_time_left = game.get_time_left