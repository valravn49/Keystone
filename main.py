import os
import discord
import asyncio
import datetime
from fastapi import FastAPI
import uvicorn

# Discord intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

# Sister tokens from env
SISTERS = {
    "Aria": {
        "token": os.getenv("ARIA_TOKEN"),
        "dob": "1999-03-20",
    },
    "Selene": {
        "token": os.getenv("SELENE_TOKEN"),
        "dob": "2001-07-13",
    },
    "Cassandra": {
        "token": os.getenv("CASSANDRA_TOKEN"),
        "dob": "2003-01-01",
    },
    "Ivy": {
        "token": os.getenv("IVY_TOKEN"),
        "dob": "2006-10-31",
    },
}

# Role cycle order
ROLE_ORDER = ["Lead", "Rest", "Support"]

# Store client objects
clients = {}

# Create FastAPI app
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/debug/status")
async def debug_status():
    today = datetime.date.today()
    # Pick which sister is Lead based on day of year
    names = list(SISTERS.keys())
    lead_index = today.toordinal() % len(names)  # cycles through sisters
    roles = {}

    for i, name in enumerate(names):
        # Distance from the lead sister
        dist = (i - lead_index) % len(names)
        role = ROLE_ORDER[dist % len(ROLE_ORDER)]
        client = clients.get(name)
        roles[name] = {
            "dob": SISTERS[name]["dob"],
            "role": role,
            "connection": "online" if client and client.is_ready() else "offline"
        }

    return roles

# Function to create a bot for each sister
def create_bot(name, token):
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"[{datetime.datetime.now()}] {name} is online as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):  # only respond if mentioned
        reply = await ask_llm(name, message.content)
        await message.channel.send(reply)
    return client, token

# Background startup
async def start_bots():
    for name, info in SISTERS.items():
        token = info["token"]
        if token:
            client, tkn = create_bot(name, token)
            clients[name] = client
            print(f"[{datetime.datetime.now()}] Logging in {name}…")
            asyncio.create_task(client.start(tkn))
        else:
            print(f"[{datetime.datetime.now()}] No token found for {name}, skipping.")

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_bots())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
