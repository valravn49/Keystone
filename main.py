import os
import json
import asyncio
import random
from datetime import datetime
import pytz
from fastapi import FastAPI
from logger import log_event

# Sibling behavior imports
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message, load_aria_memory, save_aria_memory
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message, load_selene_memory, save_selene_memory
from Autonomy.behaviors.cassandra_behavior import ensure_cass_systems, cass_handle_message, load_cass_memory, save_cass_memory
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message, load_ivy_memory, save_ivy_memory
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message, load_will_memory, save_will_memory

try:
    from image_utils import generate_and_post_daily_outfits
    IMAGE_FEATURES = True
except Exception:
    IMAGE_FEATURES = False
    log_event("[WARN] image_utils not loaded; outfits disabled.")

# ---------------------------------------------------------------------------
# Global setup
# ---------------------------------------------------------------------------

AEDT = pytz.timezone("Australia/Sydney")
CONFIG_PATH = "/app/config.json"
STATE_PATH = "/app/state.json"

def _load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

config = _load_json(CONFIG_PATH, {})
state = _load_json(STATE_PATH, {
    "morning_done_today": False,
    "midday_done_today": False,
    "evening_done_today": False,
    "night_done_today": False,
})

def save_state():
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        log_event("[STATE] Saved successfully.")
    except Exception as e:
        log_event(f"[STATE][ERROR] {e}")

# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

MEMORY_FUNCS = {
    "Aria": (load_aria_memory, save_aria_memory),
    "Selene": (load_selene_memory, save_selene_memory),
    "Cassandra": (load_cass_memory, save_cass_memory),
    "Ivy": (load_ivy_memory, save_ivy_memory),
    "Will": (load_will_memory, save_will_memory),
}

def get_seasonal_memory(name: str, event: str) -> list[str]:
    load_fn, _ = MEMORY_FUNCS[name]
    mem = load_fn()
    return mem.get("seasonal_memory", {}).get(event, [])

def add_seasonal_memory(name: str, event: str, note: str):
    load_fn, save_fn = MEMORY_FUNCS[name]
    mem = load_fn()
    sm = mem.setdefault("seasonal_memory", {})
    sm.setdefault(event, []).append(note)
    save_fn(mem)
    log_event(f"[MEMORY] Added for {name} → {event}: {note}")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI()

BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

ENSURE_FUNCS = [
    ensure_aria_systems,
    ensure_selene_systems,
    ensure_cass_systems,
    ensure_ivy_systems,
    ensure_will_systems,
]

# ---------------------------------------------------------------------------
# Holiday / Seasonal recognition
# ---------------------------------------------------------------------------

def get_current_holiday():
    now = datetime.now(AEDT)
    m, d = now.month, now.day

    if m == 10 and d == 31:
        return "Halloween"
    if m == 12 and d in [24, 25, 26]:
        return "Christmas"
    if (m == 12 and d == 31) or (m == 1 and d == 1):
        return "New Year"
    if m == 2 and d == 14:
        return "Valentine's Day"

    if "birthdays" in config:
        for name, date_str in config["birthdays"].items():
            mm, dd = map(int, date_str.split("-"))
            if m == mm and d == dd:
                return f"{name}'s Birthday"

    return None

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

async def _family_post(sisters, author_name, text):
    for bot in sisters:
        if bot.sister_info["name"] == author_name and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(text)
                log_event(f"[{author_name}] {text}")
            break

async def _group_replies(sisters, initiator, text, phase):
    responders = [s for s in sisters if s.sister_info["name"] != initiator]
    random.shuffle(responders)
    for bot in responders:
        if bot.is_ready() and random.random() < 0.85:
            name = bot.sister_info["name"]
            handler = BEHAVIOR_HANDLERS.get(name)
            if handler:
                try:
                    await asyncio.sleep(random.randint(4, 16))
                    await handler(state, config, sisters, initiator, text, config["family_group_channel"])
                except Exception as e:
                    log_event(f"[{name}][REPLY ERROR] {e}")

# ---------------------------------------------------------------------------
# Seasonal memory integration
# ---------------------------------------------------------------------------

def pull_shared_memories(event: str) -> list[str]:
    """Gather 1–2 seasonal memories per sibling for context seeding."""
    memories = []
    for name, (load_fn, _) in MEMORY_FUNCS.items():
        mem = load_fn()
        if "seasonal_memory" in mem and event in mem["seasonal_memory"]:
            mset = mem["seasonal_memory"][event]
            if mset:
                memories.append(random.choice(mset))
    return memories[:6]

def append_new_seasonal_notes(event: str):
    """Append one new shared moment for each sibling."""
    ideas = {
        "Halloween": [
            "decorations collapsed halfway through the night",
            "Will’s costume was too convincing",
            "Ivy tried to dye the cat orange again"
        ],
        "Christmas": [
            "the pudding almost caught fire again",
            "we forgot wrapping paper and used magazines",
            "Selene made too much cocoa for five people"
        ],
        "New Year": [
            "we all fell asleep before midnight",
            "Aria made a tiny toast with tea instead of champagne",
            "Cass actually smiled during the countdown"
        ],
        "Valentine's Day": [
            "Will made cards for everyone",
            "Aria bought herself roses",
            "Ivy pranked Cass with heart confetti"
        ]
    }

    for name in MEMORY_FUNCS.keys():
        note = random.choice(ideas.get(event, [f"A small moment from {event.lower()}"]))
        add_seasonal_memory(name, event, note)

# ---------------------------------------------------------------------------
# Rituals with holiday context & memories
# ---------------------------------------------------------------------------

async def post_with_holiday_context(sisters, phase, default_texts):
    holiday = get_current_holiday()
    initiator = random.choice(list(BEHAVIOR_HANDLERS.keys()))

    memories = pull_shared_memories(holiday) if holiday else []

    if holiday:
        prefix = f"({holiday}) "
    else:
        prefix = ""

    base_text = random.choice(default_texts)
    if memories:
        memory_line = random.choice(memories)
        text = f"{prefix}{base_text} Remember when {memory_line}?"
    else:
        text = prefix + base_text

    await _family_post(sisters, initiator, text)
    await _group_replies(sisters, initiator, text, phase)

    if IMAGE_FEATURES and holiday:
        await generate_and_post_daily_outfits(sisters, holiday_theme=holiday)

    if holiday:
        append_new_seasonal_notes(holiday)

# ---------------------------------------------------------------------------
# Daily rituals
# ---------------------------------------------------------------------------

async def morning_ritual(sisters):
    texts = [
        "☀️ Morning everyone — new day, new rhythm.",
        "🌅 Rise and shine — who’s making coffee?",
        "🕊️ Let’s start the day soft and steady."
    ]
    await post_with_holiday_context(sisters, "morning", texts)
    state["morning_done_today"] = True
    save_state()

async def midday_checkin(sisters):
    texts = [
        "🍱 Lunch break — who’s actually eating properly?",
        "☕ Midday check-in: any chaos yet?",
        "💬 Take five, stretch, hydrate — reminder from me."
    ]
    await post_with_holiday_context(sisters, "midday", texts)
    state["midday_done_today"] = True
    save_state()

async def evening_checkin(sisters):
    texts = [
        "🌆 Almost done — how’s everyone holding up?",
        "🕯️ Quiet hour, anyone watching something good?",
        "🌇 Just sitting with a snack and my thoughts."
    ]
    await post_with_holiday_context(sisters, "evening", texts)
    state["evening_done_today"] = True
    save_state()

async def night_ritual(sisters):
    texts = [
        "🌙 Good night, everyone. Sleep easy.",
        "💤 Time for blankets and silence.",
        "🌌 Grateful for the small things today."
    ]
    await post_with_holiday_context(sisters, "night", texts)
    state["night_done_today"] = True
    save_state()

# ---------------------------------------------------------------------------
# Schedule Loop
# ---------------------------------------------------------------------------

async def daily_schedule_loop(sisters):
    """AEDT-aware loop for rituals, check-ins, and seasonal memories."""
    while True:
        now = datetime.now(AEDT)
        h = now.hour

        if 6 <= h < 8 and not state.get("morning_done_today"):
            await morning_ritual(sisters)

        if 11 <= h < 14 and not state.get("midday_done_today"):
            await midday_checkin(sisters)

        if 18 <= h < 20 and not state.get("evening_done_today"):
            await evening_checkin(sisters)

        if 21 <= h < 23 and not state.get("night_done_today"):
            await night_ritual(sisters)

        if 2 <= h < 5:
            for k in ["morning_done_today", "midday_done_today", "evening_done_today", "night_done_today"]:
                state[k] = False

        save_state()
        await asyncio.sleep(300)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    sisters = []
    for fn in ENSURE_FUNCS:
        fn(state, config, sisters)
    log_event("[INIT] Sibling systems started with seasonal memory support.")
    asyncio.create_task(daily_schedule_loop(sisters))

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    now = datetime.now(AEDT)
    return {
        "status": "ok",
        "time_AEDT": now.strftime("%Y-%m-%d %H:%M:%S"),
        "holiday": get_current_holiday() or "None"
    }
