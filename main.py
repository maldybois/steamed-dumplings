import discord
from discord.ext import commands
from discord import app_commands
import datetime
import requests
import openai
import os

# Setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Set your OpenAI API key and Discord token from environment
openai.api_key = os.environ.get("OPENAI_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# Get today's Wordle answer from NYT endpoint
def get_today_wordle_solution():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    url = f"https://www.nytimes.com/svc/wordle/v2/{today}.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get("solution")
    return None

# Simulate ChatGPT playing Wordle
def simulate_chatgpt_play(solution_word):
    guess_history = []
    system_prompt = (
        "You are playing Wordle. The game gives feedback as follows: \n"
        "🟩 = correct letter and position, 🟨 = correct letter wrong position, ⬛ = letter not in word.\n"
        "Guess 5-letter words until you find the hidden solution. I will give you feedback after each guess."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Start by guessing a 5-letter word."}
    ]

    for attempt in range(1, 7):
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )

        guess = response.choices[0].message.content.strip().lower()
        guess = guess.split("\n")[0].split()[0]  # Just in case GPT adds commentary
        guess = ''.join(filter(str.isalpha, guess))[:5]

        if len(guess) != 5:
            guess = "slate"  # fallback

        # Generate feedback
        feedback = []
        used = [False] * 5
        for i, c in enumerate(guess):
            if solution_word[i] == c:
                feedback.append("🟩")
                used[i] = True
            else:
                feedback.append(None)

        for i, c in enumerate(guess):
            if feedback[i] is None:
                if c in solution_word and any(solution_word[j] == c and not used[j] for j in range(5)):
                    feedback[i] = "🟨"
                else:
                    feedback[i] = "⬛"

        guess_history.append((guess, ''.join(feedback)))

        if guess == solution_word:
            return attempt, guess_history

        messages.append({"role": "assistant", "content": guess})
        messages.append({"role": "user", "content": f"Feedback: {''.join(feedback)}\nGuess again."})

    return 6, guess_history  # fail-safe fallback

# Slash command version
@tree.command(name="wordle", description="Get today's Wordle par score (ChatGPT's estimated guess count)")
async def wordle_command(interaction: discord.Interaction):
    await interaction.response.defer()
    solution = get_today_wordle_solution()
    if not solution:
        await interaction.followup.send("Could not fetch today's Wordle.")
        return

    guess_count, _ = simulate_chatgpt_play(solution)

    embed = discord.Embed(
        title="📊 Wordle Par Score",
        description=f"ChatGPT took **{guess_count}** guesses to solve today's Wordle.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Estimated by AI, actual Wordle answer hidden.")
    await interaction.followup.send(embed=embed)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

# Run the bot
bot.run(DISCORD_TOKEN)
