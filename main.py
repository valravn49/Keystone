import os
import random
import asyncio
import time
import discord
from discord.ext import commands
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import openai

# --------------------------
# FastAPI server (healthcheck for Railway)
# --------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

# --------------------------
# OpenAI setup
# --------------------------
openai.api_key = os.getenv("OPENAI_API_KEY")

async def ask_llm(sister_name: str, message: str) -> str:
    """Send user message + sister persona to OpenAI and return a reply."""
    personality = PERSONALITIES[sister_name]
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": personality},
                {"role": "user", "content": message},
            ],
            max_tokens=120,
            temperature=0.8,
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        return f"(error generating reply: {e})"

# --------------------------
# Sister personalities & cooldowns
# --------------------------
PERSONALITIES = {
    "Aria": "Aria is calm, orderly, and nurturing. She tracks logs and brings structure, speaking softly but firmly.",
    "Selene": "Selene is warm, maternal, and comforting. She uses gentle encouragement and affectionate words.",
    "Cassandra": "Cassandra is strict, commanding, and values discipline. She speaks firmly, with an air of authority.",
    "Ivy": "Ivy is playful, bratty, and teasing. She flirts, provokes, and uses cheeky humor to keep things fun.",
}

SISTER_RULES = {
    "Aria": {"prob": 0.6, "cooldown": 45},      # replies sometimes, moderate cooldown
    "Selene": {"prob": 0.7, "cooldown": 40},    # replies often, comforting
    "Cassandra": {"prob": 0.4, "cooldown": 90}, # rare, strict voice
    "Ivy": {"prob": 0.8, "cooldown": 20},       # bratty, replies a lot
}

# Track last reply times
last_reply_time = {s: 0 for s in SISTER_RULES.keys()}

# --------------------------
# Discord setup
# --------------------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} is now online!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = time.time()
    sisters_to_reply = []

    for sister, rules in SISTER_RULES.items():
        # respect cooldown
        if now - last_reply_time[sister] < rules["cooldown"]:
            continue
        # decide if she replies
        if random.random() < rules["prob"]:
            sisters_to_reply.append(sister)

    delay = 0
    for sister in sisters_to_reply:
        asyncio.create_task(delayed_reply(sister, message, delay))
        delay += random.randint(2, 4)  # stagger replies naturally

async def delayed_reply(sister_name, message, delay):
    global last_reply_time
    await asyncio.sleep(delay)
    reply = await ask_llm(sister_name, message.content)
    await message.channel.send(f"**{sister_name}:** {reply}")
    last_reply_time[sister_name] = time.time()

# --------------------------
# Run both Discord and FastAPI
# --------------------------
async def main():
    discord_task = asyncio.create_task(bot.start(os.getenv("DISCORD_TOKEN")))
    api_task = asyncio.create_task(
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
    )
    await asyncio.gather(discord_task, api_task)

if __name__ == "__main__":
    asyncio.run(main())
