from typing import List, Tuple, Optional, Set, Dict
import os
import discord
from discord import app_commands

from wordle_utils import (
    compute_wordle_feedback,
    pattern_to_emojis,
    get_today_wordle_solution,
    normalize_word,
    is_valid_five_letter_word,
)

WORDS_PATH = os.environ.get("WORDLE_WORDS_PATH", "./data/valid_wordle_words.txt")

def load_word_list() -> List[str]:
    words: List[str] = []
    try:
        with open(WORDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                w = normalize_word(line)
                if is_valid_five_letter_word(w):
                    words.append(w)
    except FileNotFoundError:
        raise RuntimeError(f"Word list not found at {WORDS_PATH}. Set WORDLE_WORDS_PATH.")

    # Deduplicate and ensure everything is clean
    clean = sorted({w for w in words if is_valid_five_letter_word(w)})
    if not clean:
        raise RuntimeError("Word list was empty or invalid after cleaning.")
    return clean

def build_letter_freq(remaining: List[str]) -> Dict[str, int]:
    """Count how many candidate words contain each letter at least once."""
    freq: Dict[str, int] = {}
    for w in remaining:
        if not isinstance(w, str) or not is_valid_five_letter_word(w):
            # Skip anything unexpected
            continue
        for ch in set(w):  # unique letters per word
            freq[ch] = freq.get(ch, 0) + 1
    return freq

def score_word(word: str, freq: Dict[str, int]) -> int:
    """Sum of letter frequencies for UNIQUE letters in the word."""
    # word is guaranteed to be clean by callers
    return sum(freq.get(ch, 0) for ch in set(word))

def best_next_guess(remaining: List[str], tried: Set[str]) -> str:
    """Pick the highest scoring (unique-letters) word among remaining."""
    # Always recompute freq from current remaining set
    freq = build_letter_freq(remaining)

    candidates = [w for w in remaining if w not in tried and is_valid_five_letter_word(w)]
    if not candidates:
        # Fallback if everything got tried somehow
        candidates = [w for w in remaining if is_valid_five_letter_word(w)]
        if not candidates:
            # Should never happen, but guard anyway
            raise RuntimeError("No valid candidates available.")

    # Prefer words with higher score, then more unique letters, then lexicographic for stability
    return max(
        candidates,
        key=lambda w: (score_word(w, freq), len(set(w)), w),
    )

def register(tree: app_commands.CommandTree) -> None:
    @tree.command(
        name="wordle_csp",
        description="Solve today's Wordle using a fast constraint solver (no LLM)."
    )
    async def wordle_csp(interaction: discord.Interaction) -> None:
        # -- log start --
        print(f"[Slash Command] /wordle_csp invoked by {interaction.user} (id={interaction.user.id})")

        embed = discord.Embed(
            title="Solver is thinking...",
            description="",
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        solution = get_today_wordle_solution()
        if not solution:
            embed.title = "Wordle error"
            embed.description = "Could not fetch today's Wordle."
            embed.color = discord.Color.red()
            await msg.edit(embed=embed)
            return

        try:
            word_list = load_word_list()
        except Exception as e:
            embed.title = "Word list error"
            embed.description = str(e)
            embed.color = discord.Color.red()
            await msg.edit(embed=embed)
            return

        remaining: List[str] = word_list.copy()
        tried: Set[str] = set()
        feedback_rows: List[str] = []
        guess_count: Optional[int] = None

        for attempt in range(1, 7):
            try:
                guess = best_next_guess(remaining, tried)
            except Exception as e:
                embed.title = "Solver error"
                embed.description = f"Failed to choose next guess.\n{e}"
                embed.color = discord.Color.red()
                await msg.edit(embed=embed)
                return

            tried.add(guess)
            pattern = compute_wordle_feedback(guess, solution)

            # Console
            print(
                f"[CSP Attempt {attempt}] Guess: {guess.upper()} | "
                f"Feedback: {pattern} | Correct: {'✅' if guess == solution else '❌'}"
            )

            # Discord
            feedback_rows.append(pattern_to_emojis(pattern))
            embed.description = "\n".join(feedback_rows)
            await msg.edit(embed=embed)

            if pattern == "GGGGG":
                guess_count = attempt
                break

            # filter: keep only words consistent with observed pattern
            new_remaining = [c for c in remaining if compute_wordle_feedback(guess, c) == pattern]
            remaining = new_remaining if new_remaining else remaining  # conservative fallback

        # finalize
        if guess_count is None:
            footer_line = "Solver failed to solve today's Wordle in 6 guesses."
            embed.color = discord.Color.red()
        else:
            footer_line = f"Solved in {guess_count} guesses."
            embed.color = discord.Color.blue()

        embed.title = "Solver result"
        embed.description = "\n".join(feedback_rows + ["", footer_line]) if feedback_rows else footer_line
        await msg.edit(embed=embed)
