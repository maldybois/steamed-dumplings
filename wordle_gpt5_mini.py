from typing import List, Any, Optional, Dict
import os
import discord
from discord import app_commands

from wordle_utils import (
    compute_wordle_feedback,
    pattern_to_emojis,
    parse_guess_from_json,
    get_today_wordle_solution,
)

# Import OpenAI SDK, but do not create a client at import time
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


def get_client() -> Any:
    """
    Create the OpenAI client so .env has already been loaded by main.py.
    Raises a clear error if the key or SDK is missing.
    """
    if OpenAI is None:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not found in environment.")
    return OpenAI()


def build_system_prompt() -> str:
    return (
        "You are an expert Wordle assistant.\n"
        "- The secret is a valid English 5-letter word.\n"
        "- After each guess, you receive feedback per position using characters:\n"
        "  G (correct position), Y (wrong position), B (absent).\n"
        "- Use feedback to narrow possibilities and select the next optimal guess.\n"
        "- Do not reveal reasoning. Do not add commentary.\n"
        '- Output ONLY JSON with the exact shape {"guess":"abcde"} in lowercase.\n'
        "- Never repeat a previous guess. If told a guess was invalid or repeated, immediately propose a new one."
    )


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(
        name="wordle_gpt5_mini",
        description="Solve today's Wordle using GPT-5 Mini (streams emoji feedback)."
    )
    async def wordle_gpt5_mini(interaction: discord.Interaction) -> None:
        # --- log start ---
        print(f"[Slash Command] /wordle_gpt5_mini invoked by {interaction.user} (id={interaction.user.id})")

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

        # Create client lazily so env is loaded by main.py
        try:
            oa_client = get_client()
        except Exception as e:
            embed.title = "OpenAI error"
            embed.description = str(e)
            embed.color = discord.Color.red()
            await msg.edit(embed=embed)
            return

        system_prompt = build_system_prompt()
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": 'New game. Respond ONLY with JSON {"guess":"abcde"}. Provide your first guess.'},
        ]

        guessed_words: List[str] = []
        feedback_rows: List[str] = []
        guess_count: Optional[int] = None

        for attempt in range(1, 7):
            # Model call with JSON-only response. Do not set temperature for gpt-5-mini.
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
                # Ask the model to fix format without burning the attempt
                messages.append({
                    "role": "user",
                    "content": (
                        f"Invalid response. {guess_or_err} "
                        'Output exactly: {"guess":"abcde"} with a single 5-letter lowercase word.'
                    ),
                })
                # Quick retry
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
                    embed.title = "ChatGPT result"
                    embed.description = "\n".join(feedback_rows + ["ChatGPT failed to produce a valid guess."])
                    embed.color = discord.Color.red()
                    await msg.edit(embed=embed)
                    return

            guess: str = guess_or_err

            # Prevent repeats without burning attempt
            if guess in guessed_words:
                messages.append({
                    "role": "user",
                    "content": (
                        f"The guess '{guess}' was already tried. Do not repeat guesses. "
                        'Return a new JSON guess now.'
                    ),
                })
                # Ask again on the same attempt index
                continue

            guessed_words.append(guess)
            pattern = compute_wordle_feedback(guess, solution)

            # Console logging with full detail for debugging
            print(
                f"[GPT5 Attempt {attempt}] Guess: {guess.upper()} | "
                f"Feedback: {pattern} | Correct: {'✅' if guess == solution else '❌'}"
            )

            # Discord feedback as emoji only
            feedback_rows.append(pattern_to_emojis(pattern))
            embed.description = "\n".join(feedback_rows)
            await msg.edit(embed=embed)

            if pattern == "GGGGG":
                guess_count = attempt
                break

            # Provide structured feedback back to the model
            messages.append({
                "role": "user",
                "content": (
                    f"Feedback for guess '{guess}': {pattern}. "
                    "Legend: G=correct place, Y=wrong place, B=absent. "
                    'Respond ONLY with JSON {"guess":"abcde"}.'
                ),
            })

        # Finalize
        if guess_count is None:
            footer_line = "ChatGPT failed to solve today's Wordle in 6 guesses."
            embed.color = discord.Color.red()
        else:
            footer_line = f"Solved in {guess_count} guesses."
            embed.color = discord.Color.blue()

        embed.title = "ChatGPT result"
        embed.description = "\n".join(feedback_rows + ["", footer_line]) if feedback_rows else footer_line
        await msg.edit(embed=embed)
