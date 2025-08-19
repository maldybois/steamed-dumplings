import discord
from discord.ext import commands
from discord import app_commands
from zoneinfo import ZoneInfo
import datetime
import requests
import os
import json
from typing import List, Tuple, Optional, Dict, Any

from dotenv import load_dotenv
load_dotenv()

# --------------------
# Discord setup
# --------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# OpenAI client (uses OPENAI_API_KEY from env)
try:
    from openai import OpenAI
    oa_client = OpenAI()
except Exception:
    oa_client = None

# --------------------
# Wordle utilities
# --------------------
def is_valid_five_letter_word(word: str) -> bool:
    return isinstance(word, str) and len(word) == 5 and word.isalpha()

def normalize_word(word: str) -> str:
    return word.strip().lower()

def compute_wordle_feedback(guess: str, target: str) -> str:
    """
    Wordle feedback with duplicate handling:
    G = correct letter, correct position
    Y = correct letter, wrong position
    B = not present
    """
    guess = normalize_word(guess)
    target = normalize_word(target)
    if not (is_valid_five_letter_word(guess) and is_valid_five_letter_word(target)):
        raise ValueError("Both guess and target must be 5-letter alphabetic words.")

    feedback: List[str] = ["B"] * 5
    target_chars: List[Optional[str]] = list(target)

    # Pass 1: greens
    for i, ch in enumerate(guess):
        if ch == target_chars[i]:
            feedback[i] = "G"
            target_chars[i] = None  # consume

    # Pass 2: yellows from remaining pool
    for i, ch in enumerate(guess):
        if feedback[i] == "G":
            continue
        if ch in target_chars:
            feedback[i] = "Y"
            target_chars[target_chars.index(ch)] = None

    return "".join(feedback)

def parse_guess_from_json(content: str) -> Tuple[bool, str]:
    """
    Expect: {"guess": "abcde"}
    Returns (ok, guess_or_error_message)
    """
    try:
        data: Dict[str, Any] = json.loads(content or "")
        guess = normalize_word(str(data.get("guess", "")))
        if not is_valid_five_letter_word(guess):
            return False, "Model did not return a valid 5-letter 'guess'."
        return True, guess
    except Exception:
        return False, "Model did not return valid JSON with a 'guess' field."

def build_system_prompt() -> str:
    return (
        "You are an expert Wordle assistant.\n"
        "- The secret is a valid English 5-letter word.\n"
        "- After each guess, you receive feedback per position using characters:\n"
        "  G (correct position), Y (wrong position), B (absent).\n"
        "- Use feedback to narrow possibilities and select the next optimal guess.\n"
        "- Do not reveal reasoning. Do not add commentary.\n"
        '- Output ONLY JSON with the exact shape {\"guess\":\"abcde\"} in lowercase.\n'
        "- Never repeat a previous guess. If told a guess was invalid or repeated, immediately propose a new one."
    )

def pattern_to_emojis(pattern: str) -> str:
    mapping = {"G": "🟩", "Y": "🟨", "B": "⬛"}
    return "".join(mapping.get(ch, "⬛") for ch in pattern)

# --------------------
# Fetch today's Wordle answer
# --------------------
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

# --------------------
# Discord command with live updates
# --------------------
@tree.command(name="wordle", description="Run ChatGPT on today's Wordle and stream the feedback rows")
async def wordle_command(interaction: discord.Interaction) -> None:
    # Send immediate message
    embed = discord.Embed(
        title="ChatGPT is thinking...",
        description="",
        color=discord.Color.yellow(),
    )
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    # Resolve today's answer
    solution = get_today_wordle_solution()
    if not solution:
        embed.title = "Wordle error"
        embed.description = "Could not fetch today's Wordle."
        embed.color = discord.Color.red()
        await msg.edit(embed=embed)
        return

    # Prepare the conversation for the model
    if oa_client is None:
        embed.title = "OpenAI error"
        embed.description = "OpenAI client is not available on this bot."
        embed.color = discord.Color.red()
        await msg.edit(embed=embed)
        return

    system_prompt = build_system_prompt()
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": 'New game. Respond ONLY with JSON {"guess":"abcde"}. Provide your first guess.'},
    ]

    guessed_words: List[str] = []
    feedback_lines: List[str] = []

    # Solve loop with per-guess updates
    guess_count: Optional[int] = None
    for attempt in range(1, 7):
        # Model call (temperature not set because the chosen model enforces default)
        try:
            resp = oa_client.chat.completions.create(
                model="gpt-5-mini",
                response_format={"type": "json_object"},
                messages=messages,
            )
            content: str = resp.choices[0].message.content or ""
        except Exception as e:
            embed.title = "OpenAI API error"
            embed.description = f"API call failed.\n\n{e}"
            embed.color = discord.Color.red()
            await msg.edit(embed=embed)
            return

        ok, guess_or_err = parse_guess_from_json(content)
        if not ok:
            # ask model to fix format without consuming this attempt
            messages.append({
                "role": "user",
                "content": (
                    f"Invalid response. {guess_or_err} "
                    'Output exactly: {"guess":"abcde"} with a single 5-letter lowercase word.'
                ),
            })
            # retry once
            try:
                resp = oa_client.chat.completions.create(
                    model="gpt-5-mini",
                    response_format={"type": "json_object"},
                    messages=messages,
                )
                content = resp.choices[0].message.content or ""
            except Exception as e:
                embed.title = "OpenAI API error"
                embed.description = f"API call failed.\n\n{e}"
                embed.color = discord.Color.red()
                await msg.edit(embed=embed)
                return

            ok, guess_or_err = parse_guess_from_json(content)
            if not ok:
                # do not add a line, just fail out
                embed.title = "ChatGPT result"
                embed.description = "\n".join(feedback_lines + ["ChatGPT failed to produce a valid guess."])
                embed.color = discord.Color.red()
                await msg.edit(embed=embed)
                return

        guess: str = guess_or_err

        # prevent repeats without burning attempt
        if guess in guessed_words:
            messages.append({
                "role": "user",
                "content": (
                    f"The guess '{guess}' was already tried. Do not repeat guesses. "
                    'Return a new JSON guess now.'
                ),
            })
            # continue to next loop iteration to request again on same attempt index
            continue

        guessed_words.append(guess)
        pattern: str = compute_wordle_feedback(guess, solution)

        # --- Console logging (full detail) ---
        print(
            f"[Attempt {attempt}] Guess: {guess.upper()} | "
            f"Feedback: {pattern} | Correct: {'✅' if guess == solution else '❌'}"
        )
        
        feedback_lines.append(pattern_to_emojis(pattern))

        # Update the embed after this guess
        embed.description = "\n".join(feedback_lines)
        await msg.edit(embed=embed)

        if pattern == "GGGGG":
            guess_count = attempt
            break

        # Give the model the feedback for the next turn
        messages.append({
            "role": "user",
            "content": (
                f"Feedback for guess '{guess}': {pattern}. "
                "Legend: G=correct place, Y=wrong place, B=absent. "
                'Respond ONLY with JSON {"guess":"abcde"}.'
            ),
        })

    # Finalize the message
    if guess_count is None:
        footer_line = "ChatGPT failed to solve today's Wordle in 6 guesses."
        embed.color = discord.Color.red()
        embed.title = "ChatGPT result"
    else:
        footer_line = f"Solved in {guess_count} guesses."
        embed.color = discord.Color.blue()
        embed.title = "ChatGPT result"

    # Keep prior rows and append summary
    if feedback_lines:
        embed.description = "\n".join(feedback_lines + ["", footer_line])
    else:
        embed.description = footer_line

    await msg.edit(embed=embed)

@bot.event
async def on_ready() -> None:
    await tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
