import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# local modules
from wordle_gpt5_mini import register as register_gpt5
from wordle_csp import register as register_csp

load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready() -> None:
    # register commands from modules
    register_gpt5(tree)
    register_csp(tree)
    await tree.sync()
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN in environment.")
    bot.run(DISCORD_TOKEN)
