import os, json, sqlite3, asyncio, random, pytz, logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("sisters")

ARIA_TOKEN = os.getenv("ARIA_TOKEN")
SELENE_TOKEN = os.getenv("SELENE_TOKEN")
CASS_TOKEN = os.getenv("CASS_TOKEN")
IVY_TOKEN = os.getenv("IVY_TOKEN")
FAMILY_CHANNEL_ID = int(os.getenv("FAMILY_CHANNEL_ID", "0") or "0")
PRIMARY_USER_ID = os.getenv("PRIMARY_USER_ID") or None
TZ = pytz.timezone(os.getenv("TZ", "Australia/Melbourne"))
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = Path(os.getenv("DATABASE_FILE", "sisters.db"))
SCHEMA_PATH = Path("db/schema.sql")
    init_db()
  File "/app/main.py", line 74, in init_db
    seed_if_empty()
  File "/app/main.py", line 93, in seed_if_empty
    c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: sisters
ERROR:    Application startup failed. Exiting.
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 694, in lifespan
    async with self.lifespan_context(app) as maybe_state:
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 571, in __aenter__
    await self._router.startup()
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 671, in startup
    await handler()
  File "/app/main.py", line 227, in startup
    init_db()
  File "/app/main.py", line 74, in init_db
    seed_if_empty()
  File "/app/main.py", line 93, in seed_if_empty
    c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: sisters
ERROR:    Application startup failed. Exiting.
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 694, in lifespan
    async with self.lifespan_context(app) as maybe_state:
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 571, in __aenter__
    await self._router.startup()
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 671, in startup
    await handler()
  File "/app/main.py", line 227, in startup
    init_db()
  File "/app/main.py", line 74, in init_db
    seed_if_empty()
  File "/app/main.py", line 93, in seed_if_empty
    c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: sisters
ERROR:    Application startup failed. Exiting.
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 694, in lifespan
    async with self.lifespan_context(app) as maybe_state:
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 571, in __aenter__
    await self._router.startup()
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 671, in startup
    await handler()
  File "/app/main.py", line 227, in startup
    init_db()
  File "/app/main.py", line 74, in init_db
    seed_if_empty()
  File "/app/main.py", line 93, in seed_if_empty
    c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: sisters
ERROR:    Application startup failed. Exiting.
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 694, in lifespan
    async with self.lifespan_context(app) as maybe_state:
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 571, in __aenter__
    await self._router.startup()
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 671, in startup
    await handler()
  File "/app/main.py", line 227, in startup
    init_db()
  File "/app/main.py", line 74, in init_db
    seed_if_empty()
  File "/app/main.py", line 93, in seed_if_empty
    c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: sisters
ERROR:    Application startup failed. Exiting.
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 694, in lifespan
    async with self.lifespan_context(app) as maybe_state:
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 571, in __aenter__
    await self._router.startup()
  File "/opt/venv/lib/python3.12/site-packages/starlette/routing.py", line 671, in startup
    await handler()
  File "/app/main.py", line 227, in startup
    init_db()
  File "/app/main.py", line 74, in init_db
    seed_if_empty()
  File "/app/main.py", line 93, in seed_if_empty
    c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: sisters
ERROR:    Application startup failed. Exiting.
SISTER_ORDER = ["Aria", "Selene", "Cassandra", "Ivy"]
TOKENS = {"Aria": ARIA_TOKEN, "Selene": SELENE_TOKEN, "Cassandra": CASS_TOKEN, "Ivy": IVY_TOKEN}

intents = discord.Intents.default()
intents.message_content = True
bots: Dict[str, commands.Bot] = {}

def make_bot(name: str) -> commands.Bot:
    b = commands.Bot(command_prefix="!", intents=intents)
    @b.event
    async def on_ready():
        try:
            await b.tree.sync()
        except Exception as e:
            logger.warning("Slash sync failed for %s: %s", name, e)
        logger.info("%s logged in as %s", name, b.user)
    @b.tree.command(name=f"ping_{name.lower()}", description=f"Ping {name}")
    async def ping_cmd(interaction: discord.Interaction):
        await interaction.response.send_message(f"{name} here â steady and listening.", ephemeral=True)
    return b

async def sister_send(name: str, channel_id: int, msg: str):
    b = bots.get(name)
    if not b:
        logger.warning("Bot %s not running; skipping send.", name)
        return
    try:
        ch = b.get_channel(channel_id) or await b.fetch_channel(channel_id)
        await ch.send(msg)
    except Exception as e:
        logger.error("Send failed for %s: %s", name, e)

app = FastAPI()
scheduler = AsyncIOScheduler(timezone=str(TZ))

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SCHEMA_PATH.exists():
        with db() as conn, open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescripts(f.read()) if hasattr(conn, "executescripts") else conn.executescript(f.read())
    seed_if_empty()

def seed_if_empty():
    today = datetime.now(TZ).date()
    week_monday = today - timedelta(days=today.weekday())
    next7 = [today + timedelta(days=i) for i in range(7)]
    with db() as conn:
        cur = conn.execute("SELECT COUNT(*) c FROM themes")
        if cur.fetchone()["c"] == 0:
            conn.execute("INSERT INTO themes (week_start, theme) VALUES (?,?)", (week_monday.isoformat(), "bratty"))
        for i, d in enumerate(next7):
            c = conn.execute("SELECT 1 FROM rotations WHERE date=?", (d.isoformat(),)).fetchone()
            if not c:
                lead = SISTER_ORDER[(i + 2) % 4]
                rest = SISTER_ORDER[(SISTER_ORDER.index(lead) + 1) % 4]
                supports = [s for s in SISTER_ORDER if s not in (lead, rest)]
                conn.execute("INSERT INTO rotations (date, lead, rest, supports_json) VALUES (?,?,?,?)",
                             (d.isoformat(), lead, rest, json.dumps(supports)))
        for name in SISTER_ORDER:
            c = conn.execute("SELECT 1 FROM sisters WHERE name=?", (name,)).fetchone()
            if not c:
                conn.execute("INSERT INTO sisters (name, token, channel_id) VALUES (?,?,?)",
                             (name, "", str(FAMILY_CHANNEL_ID)))
        defaults = {
            "Aria": {"warmth":0.7,"strictness":0.4,"playfulness":0.2,"formality":0.6,"risk_tolerance":0.2},
            "Selene":{"warmth":0.85,"strictness":0.25,"playfulness":0.3,"formality":0.5,"risk_tolerance":0.15},
            "Cassandra":{"warmth":0.55,"strictness":0.6,"playfulness":0.15,"formality":0.8,"risk_tolerance":0.1},
            "Ivy":{"warmth":0.6,"strictness":0.35,"playfulness":0.75,"formality":0.35,"risk_tolerance":0.35}
        }
        bounds = {"warmth":{"min":0.4,"max":0.95},"strictness":{"min":0.2,"max":0.8},
                  "playfulness":{"min":0.1,"max":0.9},"formality":{"min":0.2,"max":0.9},
                  "risk_tolerance":{"min":0.05,"max":0.6}}
        for name, traits in defaults.items():
            c = conn.execute("SELECT 1 FROM persona WHERE name=?", (name,)).fetchone()
            if not c:
                conn.execute("INSERT INTO persona (name, traits_json, bounds_json, last_update) VALUES (?,?,?,?)",
                             (name, json.dumps(traits), json.dumps(bounds), datetime.now(TZ).isoformat()))

def get_today_rotation():
    today = datetime.now(TZ).date().isoformat()
    with db() as conn:
        row = conn.execute("SELECT * FROM rotations WHERE date=?", (today,)).fetchone()
        if not row:
            return {"date": today, "lead": "Cassandra", "rest": "Selene", "supports": ["Aria", "Ivy"]}
        return {"date": row["date"], "lead": row["lead"], "rest": row["rest"], "supports": json.loads(row["supports_json"])}

def get_current_theme():
    today = datetime.now(TZ).date()
    with db() as conn:
        rows = conn.execute("SELECT week_start, theme FROM themes").fetchall()
    chosen, latest = "bratty", None
    for r in rows:
        ws = datetime.fromisoformat(r["week_start"]).date()
        if ws <= today and (latest is None or ws > latest):
            latest = ws; chosen = r["theme"]
    return chosen

def load_traits(name: str):
    with db() as conn:
        row = conn.execute("SELECT traits_json FROM persona WHERE name=?", (name,)).fetchone()
    return json.loads(row["traits_json"]) if row else {}

def save_traits(name: str, traits: dict):
    with db() as conn:
        conn.execute("UPDATE persona SET traits_json=?, last_update=? WHERE name=?",
                     (json.dumps(traits), datetime.now(TZ).isoformat(), name))

def load_bounds(name: str):
    with db() as conn:
        row = conn.execute("SELECT bounds_json FROM persona WHERE name=?", (name,)).fetchone()
    return json.loads(row["bounds_json"]) if row else {}

def log_event(kind: str, payload: dict):
    with db() as conn:
        conn.execute("INSERT INTO events (ts, kind, payload) VALUES (?,?,?)",
                     (datetime.now(TZ).isoformat(), kind, json.dumps(payload)))

def add_memory(name: str, kind: str, content: str):
    with db() as conn:
        conn.execute("INSERT INTO memories (sister, ts, kind, content) VALUES (?,?,?,?)",
                     (name, datetime.now(TZ).isoformat(), kind, content))

def style_from_traits(t: dict):
    return {
        "emoji_level": "low" if t.get("formality", 0.5) > 0.6 else "medium",
        "use_petnames": t.get("warmth", 0.5) > 0.6,
        "short_commands": t.get("strictness", 0.5) > 0.6,
        "tease_line": t.get("playfulness", 0.4) > 0.5
    }

def pick_focuses(k=2):
    options = ["plug training", "depth & sustainment", "anal masturbation/denial", "oral obedience", "corrections"]
    import random as _r
    return _r.sample(options, k=k)

def compose_morning_for(sister: str):
    rot = get_today_rotation()
    theme = get_current_theme()
    focuses = ", ".join(pick_focuses(2))
    anchors = "Chastity log, skincare AM/PM, evening journal"
    t = style_from_traits(load_traits(sister))
    pet = "love" if t["use_petnames"] else ""
    tease = " (behave ð)" if t["tease_line"] else ""
    header = "ð **Good morning**"
    line = (f"{header}\n"
            f"Lead: **{rot['lead']}** | Rest: {rot['rest']} | Support: {', '.join(rot['supports'])}\n"
            f"Theme: *{theme}*\n"
            f"Anchors: {anchors}\n"
            f"Focuses today: {focuses}\n"
            f"Reminders: only formal outfits & training gear are logged; underwear/loungewear stay private. "
            f"Get out of bed promptly and log the time. Overnight plug check-in if planned.")
    if pet or tease:
        line += f"\n{pet}{tease}"
    return line

def compose_evening_for(sister: str):
    rot = get_today_rotation()
    theme = get_current_theme()
    t = style_from_traits(load_traits(sister))
    pet = "sweetheart" if t["use_petnames"] else ""
    header = "ð **Good night**"
    line = (f"{header}\n"
            f"Thanks to supporters ({', '.join(rot['supports'])}); rest well to {rot['rest']}. "
            f"One short reflection, please.\n"
            f"Theme reminder: *{theme}*. Did you rise promptly at 6:00? Mark success/slip.")
    if pet:
        line += f"\nSleep well, {pet}."
    return line

async def post_morning():
    rot = get_today_rotation()
    lead = rot['lead']
    msg = compose_morning_for(lead)
    if not DISABLE_DISCORD and FAMILY_CHANNEL_ID:
        await sister_send(lead, FAMILY_CHANNEL_ID, msg)
    log_event("morning_msg", {"by": lead, "message": msg})
    for s in rot["supports"]:
        await asyncio.sleep(2)
        reply = compose_evening_for(s) if False else f"{s} standing by. Theme: *{get_current_theme()}*."
        if not DISABLE_DISCORD and FAMILY_CHANNEL_ID:
            await sister_send(s, FAMILY_CHANNEL_ID, reply)
        add_memory(s, "message", reply)

async def post_evening():
    rot = get_today_rotation()
    lead = rot['lead']
    msg = compose_evening_for(lead)
    if not DISABLE_DISCORD and FAMILY_CHANNEL_ID:
        await sister_send(lead, FAMILY_CHANNEL_ID, msg)
    log_event("evening_msg", {"by": lead, "message": msg})

@app.on_event("startup")
async def startup():
    init_db()
    if not DISABLE_DISCORD:
        for name, token in TOKENS.items():
            if not token:
                logger.warning("No token for %s; bot not started.", name)
                continue
            try:
                b = make_bot(name)
                bots[name] = b
                asyncio.create_task(b.start(token))
            except Exception as e:
                logger.error("Failed to start bot %s: %s", name, e)
    scheduler.add_job(lambda: asyncio.create_task(post_morning()), CronTrigger(hour=6, minute=0, timezone=TZ), id="morning")
    scheduler.add_job(lambda: asyncio.create_task(post_evening()), CronTrigger(hour=22, minute=0, timezone=TZ), id="evening")
    scheduler.start()
    logger.info("Startup complete. HTTP on port %s", PORT)

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")}

@app.get("/debug")
def debug():
    return {
        "discord_disabled": DISABLE_DISCORD,
        "family_channel_id": FAMILY_CHANNEL_ID,
        "bots_started": [name for name, token in TOKENS.items() if token],
        "db_path": str(DB_PATH),
        "tz": str(TZ)
    }

@app.post("/trigger/morning")
async def trigger_morning():
    await post_morning()
    return {"status": "posted"}

@app.post("/trigger/evening")
async def trigger_evening():
    await post_evening()
    return {"status": "posted"}
