from typing import List, Optional, Tuple, Dict, Any
from zoneinfo import ZoneInfo
import datetime
import requests
import json

# ---------- core wordle helpers ----------

def is_valid_five_letter_word(word: str) -> bool:
    return isinstance(word, str) and len(word) == 5 and word.isalpha()

def normalize_word(word: str) -> str:
    return word.strip().lower()

def compute_wordle_feedback(guess: str, target: str) -> str:
    """
    G = green (correct letter & position)
    Y = yellow (in word, wrong position)
    B = black/absent
    """
    guess = normalize_word(guess)
    target = normalize_word(target)
    if not (is_valid_five_letter_word(guess) and is_valid_five_letter_word(target)):
        raise ValueError("Both guess and target must be 5-letter alphabetic words.")

    feedback: List[str] = ["B"] * 5
    target_chars: List[Optional[str]] = list(target)

    # 1) greens
    for i, ch in enumerate(guess):
        if ch == target_chars[i]:
            feedback[i] = "G"
            target_chars[i] = None

    # 2) yellows
    for i, ch in enumerate(guess):
        if feedback[i] == "G":
            continue
        if ch in target_chars:
            feedback[i] = "Y"
            target_chars[target_chars.index(ch)] = None

    return "".join(feedback)

def pattern_to_emojis(pattern: str) -> str:
    mapping = {"G": "🟩", "Y": "🟨", "B": "⬛"}
    return "".join(mapping.get(ch, "⬛") for ch in pattern)

def parse_guess_from_json(content: str) -> Tuple[bool, str]:
    """
    Expect: {"guess": "abcde"}; returns (ok, guess_or_error)
    """
    try:
        data: Dict[str, Any] = json.loads(content or "")
        guess = normalize_word(str(data.get("guess", "")))
        if not is_valid_five_letter_word(guess):
            return False, "Model did not return a valid 5-letter 'guess'."
        return True, guess
    except Exception:
        return False, "Model did not return valid JSON with a 'guess' field."

def get_today_wordle_solution() -> Optional[str]:
    pst = ZoneInfo("America/Los_Angeles")
    today = datetime.datetime.now(pst).strftime("%Y-%m-%d")
    url = f"https://www.nytimes.com/svc/wordle/v2/{today}.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            sol = r.json().get("solution")
            if sol and is_valid_five_letter_word(sol):
                return normalize_word(sol)
    except Exception:
        pass
    return None
