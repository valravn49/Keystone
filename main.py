import os
import asyncio
import datetime
import pytz
import discord
from discord.ext import tasks
from fastapi import FastAPI

from logger import log_event
from autonomy_sisters import start_sisters
from autonomy_will import start_will
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
    get_today_rotation,
    get_current_theme,
)
from will_behavior import ensure_will_systems
from self_update import queue_update, apply_updates_if_sleeping, generate_organic_updates
from image_utils import generate_daily_outfit_images

# ---------------------------------------------------------------------
# 🕰 Timezone: Australian Eastern Daylight Time (AEDT)
# ---------------------------------------------------------------------
AEDT = pytz.timezone("Australia/Sydney")

def aedt_time(hour: int, minute: int = 0):
    """Return a timezone-aware datetime.time object in AEDT."""
    now = datetime.datetime.now(AEDT)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target.timetz()

# ---------------------------------------------------------------------
# 🧠 Shared global state
# ---------------------------------------------------------------------
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},
    "spontaneous_end_tasks": {},
    "last_spontaneous_task": None,
}

# ---------------------------------------------------------------------
# ☀️ Morning ritual — happens at 6:00 AM AEDT
# ---------------------------------------------------------------------
@tasks.loop(time=aedt_time(6, 0))
async def morning_task():
    log_event("[TASK] Morning ritual starting.")
    from autonomy_sisters import sisters  # Lazy import for updated state
    await send_morning_message(state, {}, sisters)
    await generate_daily_outfit_images(state, sisters)
    log_event("[TASK] Morning ritual complete.")

# ---------------------------------------------------------------------
# 🌙 Night ritual — happens at 10:00 PM AEDT
# ---------------------------------------------------------------------
@tasks.loop(time=aedt_time(22, 0))
async def night_task():
    log_event("[TASK] Night ritual starting.")
    from autonomy_sisters import sisters
    await send_night_message(state, {}, sisters)
    log_event("[TASK] Night ritual complete.")

# ---------------------------------------------------------------------
# 💬 Spontaneous chatter — occurs with variable intervals
# ---------------------------------------------------------------------
@tasks.loop(minutes=55)
async def spontaneous_task():
    from autonomy_sisters import sisters
    await send_spontaneous_task(state, {}, sisters)

# ---------------------------------------------------------------------
# 🔧 Nightly update & personality drift — occurs at 3:00 AM AEDT
# ---------------------------------------------------------------------
@tasks.loop(time=aedt_time(3, 0))
async def nightly_update_task():
    from autonomy_sisters import sisters
    organic_updates = generate_organic_updates({}, state)
    bad_mood_chance = 0.15  # 15% chance per sibling

    for bot in sisters:
        name = bot.sister_info["name"]
        if name in organic_updates:
            for upd in organic_updates[name]:
                queue_update(name, upd)

        if os.getenv(f"{name.upper()}_TOKEN"):
            # Random bad mood insertion
            if asyncio.get_event_loop().time() % 7 < 1.5 or bad_mood_chance > 0.1:
                queue_update(name, {"behavior": f"{name} woke up in a bad mood today."})
        apply_updates_if_sleeping(name, state, {}, f"/Autonomy/personalities/{name}_Personality.json")

    queue_update("Will", {"personality_shift": "Sometimes bursts of confidence, retreats when flustered."})
    apply_updates_if_sleeping("Will", state, {}, "/Autonomy/personalities/Will_Personality.json")

    log_event("[TASK] Nightly update completed.")

# ---------------------------------------------------------------------
# 🧩 Startup coordination
# ---------------------------------------------------------------------
@morning_task.before_loop
@night_task.before_loop
@spontaneous_task.before_loop
@nightly_update_task.before_loop
async def before_tasks():
    await asyncio.sleep(5)

# ---------------------------------------------------------------------
# 🚀 FastAPI + Bot Startup
# ---------------------------------------------------------------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    log_event("[SYSTEM] Initializing all systems (AEDT).")
    # Launch all bots asynchronously
    asyncio.create_task(start_sisters())
    asyncio.create_task(start_will())
    await asyncio.sleep(10)

    # Start recurring tasks
    morning_task.start()
    night_task.start()
    spontaneous_task.start()
    nightly_update_task.start()

    # Ensure Will’s background chatter system is active
    from autonomy_will import will_bot
    ensure_will_systems(state, {}, [will_bot])

    log_event("[SYSTEM] All tasks started successfully (Autonomy Framework active).")

@app.get("/health")
async def health_check():
    return {"status": "ok", "timezone": "Australia/Sydney (AEDT)"}
