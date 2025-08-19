# Discord Bot for Wordle
---

This bot plays Wordle automatically and posts results in Discord.

### Features
- Fetches today’s Wordle solution from the NY Times public API.
- Two solver modes:
  - **GPT-5 Mini Solver** – Uses OpenAI’s GPT-5 Mini model to play step by step.
  - **CSP Solver** – A fast, rule-based constraint solver using a word list file.
- Streams feedback for each guess in Discord using 🟩🟨⬛ emojis (no spoilers).
- Logs full guess details to the console for debugging.
- Tracks how many attempts were used to solve (or fail within 6 tries).

### Commands
- `/wordle_gpt5_mini` – Run the GPT-5 Mini solver.
- `/wordle_csp` – Run the constraint-based solver (no LLM required).

