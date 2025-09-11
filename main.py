import os, json, sqlite3, asyncio, random, pytz
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, Body
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()
TOKENS = {k.split("_")[0].title(): os.getenv(k) for k in ["ARIA_TOKEN","SELENE_TOKEN","CASS_TOKEN","IVY_TOKEN"]}
FAMILY_CHANNEL_ID = int(os.getenv("FAMILY_CHANNEL_ID", "0"))
TZ = pytz.timezone(os.getenv("TZ", "Australia/Melbourne"))
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./sisters.db")
DB_PATH = Path(DB_URL.replace("sqlite:///", "")) if DB_URL.startswith("sqlite:///") else Path("sisters.db")
SISTER_ORDER = ["Aria","Selene","Cassandra","Ivy"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rotations (date TEXT PRIMARY KEY, lead TEXT, rest TEXT, supports_json TEXT);
CREATE TABLE IF NOT EXISTS themes (week_start TEXT PRIMARY KEY, theme TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS sisters (name TEXT PRIMARY KEY, token TEXT, channel_id TEXT);
CREATE TABLE IF NOT EXISTS persona (name TEXT PRIMARY KEY, traits_json TEXT, bounds_json TEXT, last_update TEXT);
CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, sister TEXT, ts TEXT, kind TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, sister TEXT, signal TEXT, weight REAL DEFAULT 1.0);
"""

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def init_db():
    with db() as conn: conn.executescript(SCHEMA_SQL)
    seed_if_empty()

def seed_if_empty():
    today = datetime.now(TZ).date()
    week_monday = today - timedelta(days=today.weekday())
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO themes (week_start, theme) VALUES (?,?)",(week_monday.isoformat(),"bratty"))
        for i in range(7):
            d = (today + timedelta(days=i)).isoformat()
            row = conn.execute("SELECT 1 FROM rotations WHERE date=?", (d,)).fetchone()
            if not row:
                lead = SISTER_ORDER[(i+2)%4]; rest = SISTER_ORDER[(SISTER_ORDER.index(lead)+1)%4]
                supports = [s for s in SISTER_ORDER if s not in (lead,rest)]
                conn.execute("INSERT INTO rotations (date,lead,rest,supports_json) VALUES (?,?,?,?)",(d,lead,rest,json.dumps(supports)))
        for s in SISTER_ORDER:
            conn.execute("INSERT OR IGNORE INTO sisters (name, token, channel_id) VALUES (?,?,?)",(s,"",str(FAMILY_CHANNEL_ID)))
            if not conn.execute("SELECT 1 FROM persona WHERE name=?", (s,)).fetchone():
                traits={"warmth":0.7,"strictness":0.4,"playfulness":0.3,"formality":0.6,"risk_tolerance":0.2}
                bounds={"warmth":{"min":0.4,"max":0.95},"strictness":{"min":0.2,"max":0.8},"playfulness":{"min":0.1,"max":0.9},"formality":{"min":0.2,"max":0.9},"risk_tolerance":{"min":0.05,"max":0.6}}
                conn.execute("INSERT INTO persona (name,traits_json,bounds_json,last_update) VALUES (?,?,?,?)",(s,json.dumps(traits),json.dumps(bounds),datetime.now(TZ).isoformat()))

def get_today_rotation():
    today = datetime.now(TZ).date().isoformat()
    with db() as conn:
        r = conn.execute("SELECT * FROM rotations WHERE date=?", (today,)).fetchone()
    if not r: return {"date":today,"lead":"Cassandra","rest":"Selene","supports":["Aria","Ivy"]}
    return {"date":r["date"],"lead":r["lead"],"rest":r["rest"],"supports":json.loads(r["supports_json"])}

def get_current_theme():
    today = datetime.now(TZ).date(); chosen, latest="bratty", None
    with db() as conn: rows = conn.execute("SELECT * FROM themes").fetchall()
    for r in rows:
        ws = datetime.fromisoformat(r["week_start"]).date()
        if ws<=today and (latest is None or ws>latest): latest=ws; chosen=r["theme"]
    return chosen

def pick_focuses(k=2):
    import random; options=["plug training","depth & sustainment","anal masturbation/denial","oral obedience","corrections"]
    return ", ".join(random.sample(options,k=k))

def compose_morning(sister):
    rot, theme = get_today_rotation(), get_current_theme()
    anchors="Chastity log, skincare AM/PM, evening journal"
    return (f"ð **Good morning â {sister}**\n"
            f"Lead: **{rot['lead']}** | Rest: {rot['rest']} | Support: {', '.join(rot['supports'])}\n"
            f"Theme: *{theme}*\nAnchors: {anchors}\nFocuses today: {pick_focuses(2)}\n"
            f"Reminders: only formal outfits & training gear are logged; underwear/loungewear stay private. "
            f"Get out of bed promptly and log the time.")

def compose_evening(sister):
    rot, theme = get_today_rotation(), get_current_theme()
    return (f"ð **Good night â {sister}**\nThanks to supporters ({', '.join(rot['supports'])}); rest well to {rot['rest']}. "
            f"One short reflection, please.\nTheme reminder: *{theme}*. Did you rise promptly at 6:00? Mark success/slip.")

intents = discord.Intents.default(); intents.message_content=True
bots: Dict[str, commands.Bot] = {}
def make_bot(name):
    b = commands.Bot(command_prefix="!", intents=intents)
    @b.event
    async def on_ready():
        try: await b.tree.sync()
        except Exception as e: print(f"{name} slash sync error: {e}")
        print(f"{name} logged in as {b.user}")
    @b.tree.command(name=f"ping_{name.lower()}")
    async def ping(interaction: discord.Interaction): await interaction.response.send_message(f"{name} here â steady.", ephemeral=True)
    @b.tree.command(name=f"say_{name.lower()}")
    async def say(interaction: discord.Interaction, message: str):
        ch = b.get_channel(FAMILY_CHANNEL_ID) or await b.fetch_channel(FAMILY_CHANNEL_ID); await ch.send(f"{name}: {message}")
        await interaction.response.send_message("Sent.", ephemeral=True)
    @b.tree.command(name=f"status_{name.lower()}")
    async def status(interaction: discord.Interaction):
        r, t = get_today_rotation(), get_current_theme()
        await interaction.response.send_message(f"ð {r['date']} â Lead: **{r['lead']}** | Rest: {r['rest']} | Support: {', '.join(r['supports'])} â¢ Theme: *{t}*", ephemeral=True)
    @b.tree.command(name=f"wake_{name.lower()}")
    async def wake(interaction: discord.Interaction, hhmm: str):
        ok, note = log_wake_time(hhmm); await interaction.response.send_message(note, ephemeral=True)
    return b

async def sister_send(name, channel_id, msg):
    b = bots.get(name); 
    if not b: return
    ch = b.get_channel(channel_id) or await b.fetch_channel(channel_id); await ch.send(msg)

scheduler = AsyncIOScheduler(timezone=str(TZ))
app = FastAPI()

def log_wake_time(hhmm:str):
    try: h,m = map(int, hhmm.split(":")); wake=dtime(hour=h, minute=m)
    except: return False, "Format must be HH:MM"
    six=dtime(6,0); success = wake<=six
    with db() as conn: conn.execute("INSERT INTO events (ts, kind, payload) VALUES (?,?,?)",(datetime.now(TZ).isoformat(),"wake",json.dumps({"time":hhmm,"success":success})))
    return True, f"Wake time logged: {hhmm} â {'success' if success else 'slip'}."

async def post_morning():
    r = get_today_rotation(); msg = compose_morning(r['lead']); await sister_send(r['lead'], FAMILY_CHANNEL_ID, msg)
    for s in r["supports"]:
        await asyncio.sleep(1); await sister_send(s, FAMILY_CHANNEL_ID, f"{s}: Theme is *{get_current_theme()}*. Holding you up.")

async def post_evening():
    r = get_today_rotation(); msg = compose_evening(r['lead']); await sister_send(r['lead'], FAMILY_CHANNEL_ID, msg)

@app.on_event("startup")
async def startup():
    init_db()
    for name, token in TOKENS.items():
        if token:
            bots[name]=make_bot(name); asyncio.create_task(bots[name].start(token))
        else:
            print(f"Warning: no token for {name}")
    scheduler.add_job(lambda: asyncio.create_task(post_morning()), CronTrigger(hour=6, minute=0, timezone=TZ), id="morning", replace_existing=True)
    scheduler.add_job(lambda: asyncio.create_task(post_evening()), CronTrigger(hour=22, minute=0, timezone=TZ), id="evening", replace_existing=True)
    scheduler.add_job(lambda: set_next_monday_theme(), CronTrigger(day_of_week="mon", hour=0, minute=5, timezone=TZ), id="theme_rotate", replace_existing=True)
    scheduler.start()

@app.get("/health")
def health(): return {"ok": True}

@app.post("/trigger/morning")
async def trigger_morning(): await post_morning(); return {"status":"posted"}
@app.post("/trigger/evening")
async def trigger_evening(): await post_evening(); return {"status":"posted"}

def set_next_monday_theme():
    today=datetime.now(TZ).date(); next_mon=today - timedelta(days=today.weekday()) + timedelta(days=7)
    cycle=["bratty","soft","crossdressing","skincare"]; cur=get_current_theme(); nxt=cycle[(cycle.index(cur)+1)%len(cycle)] if cur in cycle else cycle[0]
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO themes (week_start, theme) VALUES (?,?)",(next_mon.isoformat(),nxt))
        conn.execute("INSERT INTO events (ts, kind, payload) VALUES (?,?,?)",(datetime.now(TZ).isoformat(),"theme_rotation",json.dumps({"week_start":next_mon.isoformat(),"theme":nxt})))
