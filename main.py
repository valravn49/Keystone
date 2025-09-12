import os
import discord
import random
import time
import asyncio
import openai
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

# --------------------------
# Setup
# --------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# Tokens
DISCORD_TOKENS = {
    "Aria": os.getenv("ARIA_TOKEN"),
    "Selene": os.getenv("SELENE_TOKEN"),
    "Cassandra": os.getenv("CASSANDRA_TOKEN"),
    "Ivy": os.getenv("IVY_TOKEN"),
}

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_KEY

# Create a client per sister
bots = {}

# --------------------------
# Personality Prompts
# --------------------------
PERSONALITIES = {
    "Aria": "You are Aria, calm, orderly, supportive, and maternal.",
    "Selene": "You are Selene, nurturing, gentle, and thoughtful.",
    "Cassandra": "You are Cassandra, strict, commanding, and proud.",
    "Ivy": "You are Ivy, playful, teasing, mischievous, and bratty.",
}

STYLES = {
    "Aria": "Soft, structured, kind, with long nurturing replies.",
    "Selene": "Warm, comforting, thoughtful, empathetic.",
    "Cassandra": "Confident, strict, concise, authoritative.",
    "Ivy": "Flirty, chaotic, bratty, short playful bursts.",
}

# --------------------------
# Groupchat Memory
# --------------------------
CHAT_MEMORY = {}
MEMORY_LIMIT = 20

def update_memory(channel_id, author, content):
    if channel_id not in CHAT_MEMORY:
        CHAT_MEMORY[channel_id] = []
    CHAT_MEMORY[channel_id].append(f"{author}: {content}")
    if len(CHAT_MEMORY[channel_id]) > MEMORY_LIMIT:
        CHAT_MEMORY[channel_id].pop(0)

def get_memory(channel_id):
    return "\n".join(CHAT_MEMORY.get(channel_id, []))

# --------------------------
# Reply Settings
# --------------------------
SISTER_RULES = {
    "Aria": {"prob": 0.4, "cooldown": 120},
    "Selene": {"prob": 0.4, "cooldown": 120},
    "Cassandra": {"prob": 0.3, "cooldown": 180},
    "Ivy": {"prob": 0.5, "cooldown": 90},
}

last_reply_time = {sister: 0 for sister in SISTER_RULES.keys()}

# --------------------------
# LLM Call
# --------------------------
async def ask_llm(sister_name: str, message: str, channel_id: int) -> str:
    personality = PERSONALITIES[sister_name]
    style = STYLES[sister_name]

    memory_context = ""
    if random.random() < 0.5:
        memory_context = f"\nHere is the recent groupchat log:\n{get_memory(channel_id)}"

    if random.random() < 0.3:
        tag = random.choice([s for s in PERSONALITIES.keys() if s != sister_name])
        message = f"(Consider addressing {tag} in your reply) " + message

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": personality},
                {"role": "system", "content": f"Always write in this style: {style}"},
                {"role": "system", "content": memory_context},
                {"role": "user", "content": message},
            ],
            max_tokens=180,
            temperature=0.9,
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        return f"(error generating reply: {e})"

# --------------------------
# Bot Factory
# --------------------------
def create_bot(sister_name):
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"{sister_name} is online as {client.user}")

    @client.event
    async def on_message(message):
        if message.author.bot:
            return

        update_memory(message.channel.id, message.author.name, message.content)

        now = time.time()
        rules = SISTER_RULES[sister_name]

        if now - last_reply_time[sister_name] < rules["cooldown"]:
            return

        if random.random() < rules["prob"]:
            await asyncio.sleep(random.randint(2, 5))
            reply = await ask_llm(sister_name, message.content, message.channel.id)
            await message.channel.send(f"**{sister_name}**: {reply}")
            last_reply_time[sister_name] = time.time()
            update_memory(message.channel.id, sister_name, reply)

    return client

# --------------------------
# FastAPI
# --------------------------
app = FastAPI()

class Msg(BaseModel):
    content: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/send")
async def send_message(msg: Msg):
    for client in bots.values():
        for channel in client.get_all_channels():
            if channel.name == "general":
                await channel.send(msg.content)
    return {"status": "sent"}

# --------------------------
# Run all bots
# --------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    for sister, token in DISCORD_TOKENS.items():
        if token:
            bot = create_bot(sister)
            bots[sister] = bot
            loop.create_task(bot.start(token))

    uvicorn.run(app, host="0.0.0.0", port=8080)
