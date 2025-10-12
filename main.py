import asyncio
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from logger import log_event
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
    handle_sister_message,
    generate_and_post_outfit,
)
from will_behavior import ensure_will_systems, will_handle_message

# Optional FastAPI import for ASGI environments
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
AEDT = ZoneInfo("Australia/Sydney")

# ---------------------------------------------------------------------------
# Scheduling parameters (AEDT local)
# ---------------------------------------------------------------------------
MORNING_HOUR_AEDT = 6
NIGHT_HOUR_AEDT = 22
SPONTANEOUS_INTERVAL_MIN = 45 * 60  # 45 minutes
LOOP_SLEEP_MIN = 120  # 2 min
LOOP_SLEEP_MAX = 300  # 5 min

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_aedt():
    return datetime.now(AEDT)

# ---------------------------------------------------------------------------
# Main family loop
# ---------------------------------------------------------------------------
async def family_main_loop(state, config, sisters):
    """Background loop for rituals, outfits, and spontaneous chatter."""
    log_event("[SYSTEM] Family loop started (AEDT synchronized).")
    ensure_will_systems(state, config, sisters)

    last_spontaneous = None
    last_outfit_check = None
    last_morning = None
    last_night = None

    while True:
        now = now_aedt()

        # Morning ritual
        if now.hour == MORNING_HOUR_AEDT and (not last_morning or last_morning.date() != now.date()):
            try:
                log_event("[RITUAL] Running morning ritual (AEDT).")
                await send_morning_message(state, config, sisters)

                # Post outfit photos for each sibling
                for entry in config.get("rotation", []):
                    await generate_and_post_outfit(state, config, sisters, entry["name"])
                last_morning = now
            except Exception as e:
                log_event(f"[ERROR] Morning ritual failed: {e}")

        # Night ritual
        if now.hour == NIGHT_HOUR_AEDT and (not last_night or last_night.date() != now.date()):
            try:
                log_event("[RITUAL] Running night ritual (AEDT).")
                await send_night_message(state, config, sisters)
                last_night = now
            except Exception as e:
                log_event(f"[ERROR] Night ritual failed: {e}")

        # Spontaneous chatter
        if not last_spontaneous or (now - last_spontaneous).total_seconds() >= SPONTANEOUS_INTERVAL_MIN:
            if random.random() < 0.65:  # ~65% chance per interval
                try:
                    log_event("[SPONT] Running spontaneous chat check.")
                    await send_spontaneous_task(state, config, sisters)
                except Exception as e:
                    log_event(f"[ERROR] Spontaneous chat failed: {e}")
            last_spontaneous = now

        # Midday outfit refresh (once per day after 12:00)
        if (not last_outfit_check or last_outfit_check.date() != now.date()) and now.hour >= 12:
            try:
                log_event("[OUTFIT] Midday outfit refresh check.")
                for entry in config.get("rotation", []):
                    await generate_and_post_outfit(state, config, sisters, entry["name"])
                last_outfit_check = now
            except Exception as e:
                log_event(f"[ERROR] Outfit refresh failed: {e}")

        await asyncio.sleep(random.randint(LOOP_SLEEP_MIN, LOOP_SLEEP_MAX))

# ---------------------------------------------------------------------------
# Message event hook (called when a message appears in the family group)
# ---------------------------------------------------------------------------
async def on_message(state, config, sisters, author, content, channel_id):
    """Routes inter-sibling and Will responses."""
    if not author or not content:
        return

    try:
        await handle_sister_message(state, config, sisters, author, content, channel_id)
        await will_handle_message(state, config, sisters, author, content, channel_id)
    except Exception as e:
        log_event(f"[ERROR] on_message failed for {author}: {e}")

# ---------------------------------------------------------------------------
# Autonomy startup
# ---------------------------------------------------------------------------
def start_autonomy_system(state, config, sisters):
    """Launches the family loop in the background."""
    log_event("[BOOT] Starting autonomy system (AEDT synchronized).")
    asyncio.create_task(family_main_loop(state, config, sisters))

# ---------------------------------------------------------------------------
# FastAPI app for ASGI environments
# ---------------------------------------------------------------------------
app = FastAPI(title="Autonomy System", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """
    Automatically triggers the background family loop
    when deployed under Uvicorn / ASGI.
    """
    global STATE, CONFIG, SISTERS
    try:
        # Lazy imports of shared state/config — replace these with your actual imports
        from autonomy_state import state as STATE
        from autonomy_config import config as CONFIG
        from autonomy_sisters import sisters as SISTERS

        start_autonomy_system(STATE, CONFIG, SISTERS)
        log_event("[ASGI] Background autonomy loop started.")
    except Exception as e:
        log_event(f"[ERROR] Startup loop failed: {e}")

@app.get("/")
async def root():
    """Status endpoint for hosted environments."""
    return {
        "status": "running",
        "timezone": "Australia/Sydney (AEDT)",
        "message": "Autonomy system active and synchronized"
    }

@app.get("/health")
async def health_check():
    """Simple uptime ping."""
    return {"ok": True, "time_aedt": now_aedt().isoformat()}
