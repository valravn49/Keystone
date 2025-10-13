import os
import asyncio
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from logger import log_event
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
    handle_sister_message,
    generate_and_post_outfit,
)
from will_behavior import ensure_will_systems, will_handle_message

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
AEDT = ZoneInfo("Australia/Sydney")

# ---------------------------------------------------------------------------
# Scheduling constants
# ---------------------------------------------------------------------------
MORNING_HOUR_AEDT = 6
NIGHT_HOUR_AEDT = 22
SPONT_INTERVAL = 45 * 60  # 45 minutes
LOOP_SLEEP_MIN = 120
LOOP_SLEEP_MAX = 300

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def now_aedt():
    return datetime.now(AEDT)

# ---------------------------------------------------------------------------
# Main family loop (background)
# ---------------------------------------------------------------------------
async def family_main_loop(state, config, sisters, will_bot):
    log_event("[SYSTEM] Family loop started (AEDT synchronized).")
    ensure_will_systems(state, config, [will_bot])

    last_spontaneous = None
    last_outfit_check = None
    last_morning = None
    last_night = None

    while True:
        now = now_aedt()

        # Morning ritual
        if now.hour == MORNING_HOUR_AEDT and (not last_morning or last_morning.date() != now.date()):
            try:
                log_event("[RITUAL] Morning ritual running.")
                await send_morning_message(state, config, sisters)
                for entry in config.get("rotation", []):
                    await generate_and_post_outfit(state, config, sisters, entry["name"])
                last_morning = now
            except Exception as e:
                log_event(f"[ERROR] Morning ritual: {e}")

        # Night ritual
        if now.hour == NIGHT_HOUR_AEDT and (not last_night or last_night.date() != now.date()):
            try:
                log_event("[RITUAL] Night ritual running.")
                await send_night_message(state, config, sisters)
                last_night = now
            except Exception as e:
                log_event(f"[ERROR] Night ritual: {e}")

        # Spontaneous chatter
        if not last_spontaneous or (now - last_spontaneous).total_seconds() >= SPONT_INTERVAL:
            if random.random() < 0.65:
                try:
                    await send_spontaneous_task(state, config, sisters)
                except Exception as e:
                    log_event(f"[ERROR] Spontaneous chat: {e}")
            last_spontaneous = now

        # Midday outfit refresh
        if (not last_outfit_check or last_outfit_check.date() != now.date()) and now.hour >= 12:
            try:
                log_event("[OUTFIT] Midday outfit refresh.")
                for entry in config.get("rotation", []):
                    await generate_and_post_outfit(state, config, sisters, entry["name"])
                last_outfit_check = now
            except Exception as e:
                log_event(f"[ERROR] Outfit refresh: {e}")

        await asyncio.sleep(random.randint(LOOP_SLEEP_MIN, LOOP_SLEEP_MAX))

# ---------------------------------------------------------------------------
# Discord Message Relay
# ---------------------------------------------------------------------------
async def on_message(state, config, sisters, will_bot, author, content, channel_id):
    if not author or not content:
        return
    try:
        await handle_sister_message(state, config, sisters, author, content, channel_id)
        await will_handle_message(state, config, [will_bot], author, content, channel_id)
    except Exception as e:
        log_event(f"[ERROR] on_message for {author}: {e}")

# ---------------------------------------------------------------------------
# Autonomy startup
# ---------------------------------------------------------------------------
async def start_autonomy_system(state, config, sisters, will_bot):
    """Starts all bots and the family loop."""
    log_event("[BOOT] Starting bots and autonomy system.")

    # Start Discord bots
    for bot in sisters:
        token = os.getenv(bot.sister_info["env_var"])
        if token:
            asyncio.create_task(bot.start(token))
            log_event(f"[LOGIN] Starting {bot.sister_info['name']} bot.")
        else:
            log_event(f"[WARN] Missing token for {bot.sister_info['name']}")

    will_token = os.getenv(will_bot.sister_info["env_var"])
    if will_token:
        asyncio.create_task(will_bot.start(will_token))
        log_event(f"[LOGIN] Starting Will bot.")
    else:
        log_event("[WARN] Missing Will bot token.")

    # Start main background loop
    asyncio.create_task(family_main_loop(state, config, sisters, will_bot))
    log_event("[SYSTEM] All tasks scheduled.")

# ---------------------------------------------------------------------------
# FastAPI app (ASGI entry)
# ---------------------------------------------------------------------------
app = FastAPI(title="Autonomy System", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Starts the family system automatically when ASGI app starts."""
    from autonomy_state import state
    from autonomy_config import config
    from autonomy_sisters import sisters
    from autonomy_will import will_bot

    try:
        await start_autonomy_system(state, config, sisters, will_bot)
        log_event("[ASGI] Autonomy system running.")
    except Exception as e:
        log_event(f"[ERROR] Startup event failed: {e}")

@app.get("/")
async def root():
    return {
        "status": "running",
        "timezone": "Australia/Sydney (AEDT)",
        "message": "Autonomy system active",
    }

@app.get("/health")
async def health():
    return {"ok": True, "time_aedt": now_aedt().isoformat()}
