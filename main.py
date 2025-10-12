import asyncio
import random
from datetime import datetime, timedelta
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

AEDT = ZoneInfo("Australia/Sydney")

# ---------------------------------------------------------------------------
# Scheduling parameters (AEDT times)
# ---------------------------------------------------------------------------
MORNING_HOUR_AEDT = 6   # 6:00 AEDT
NIGHT_HOUR_AEDT = 22    # 22:00 AEDT
SPONTANEOUS_INTERVAL_MIN = 45 * 60   # 45 minutes minimum between spontaneous posts

# ---------------------------------------------------------------------------
# Utility: current AEDT-aware time
# ---------------------------------------------------------------------------
def now_aedt():
    return datetime.now(AEDT)

# ---------------------------------------------------------------------------
# Family orchestration
# ---------------------------------------------------------------------------
async def family_main_loop(state, config, sisters):
    """
    Core asynchronous loop controlling rituals, spontaneous chatter,
    outfit generation, and Will’s chatter background task.
    """
    log_event("[SYSTEM] Family loop started (AEDT synchronized).")

    ensure_will_systems(state, config, sisters)  # starts Will’s chatter task

    last_spontaneous = None
    last_outfit_check = None
    last_morning = None
    last_night = None

    while True:
        now = now_aedt()

        # --------------------------------------------------------
        # Morning ritual (once per AEDT day)
        # --------------------------------------------------------
        if now.hour == MORNING_HOUR_AEDT and (not last_morning or last_morning.date() != now.date()):
            try:
                log_event("[RITUAL] Running morning ritual (AEDT).")
                await send_morning_message(state, config, sisters)
                # Outfit updates after morning ritual (rotation-aware)
                rotation = config.get("rotation", [])
                for entry in rotation:
                    await generate_and_post_outfit(state, config, sisters, entry["name"])
                last_morning = now
            except Exception as e:
                log_event(f"[ERROR] Morning ritual failed: {e}")

        # --------------------------------------------------------
        # Night ritual (once per AEDT day)
        # --------------------------------------------------------
        if now.hour == NIGHT_HOUR_AEDT and (not last_night or last_night.date() != now.date()):
            try:
                log_event("[RITUAL] Running night ritual (AEDT).")
                await send_night_message(state, config, sisters)
                last_night = now
            except Exception as e:
                log_event(f"[ERROR] Night ritual failed: {e}")

        # --------------------------------------------------------
        # Spontaneous chatter (probabilistic timing)
        # --------------------------------------------------------
        if not last_spontaneous or (now - last_spontaneous).total_seconds() >= SPONTANEOUS_INTERVAL_MIN:
            if random.random() < 0.65:  # ~65% chance every interval
                try:
                    log_event("[SPONT] Running spontaneous chat check.")
                    await send_spontaneous_task(state, config, sisters)
                except Exception as e:
                    log_event(f"[ERROR] Spontaneous chat failed: {e}")
            last_spontaneous = now

        # --------------------------------------------------------
        # Outfit refresh (once every AEDT day, after midday)
        # --------------------------------------------------------
        if (not last_outfit_check or last_outfit_check.date() != now.date()) and now.hour >= 12:
            try:
                log_event("[OUTFIT] Midday outfit refresh check.")
                for entry in config.get("rotation", []):
                    await generate_and_post_outfit(state, config, sisters, entry["name"])
                last_outfit_check = now
            except Exception as e:
                log_event(f"[ERROR] Outfit refresh failed: {e}")

        # --------------------------------------------------------
        # Sleep jitter: 2–5 minutes between loop checks
        # --------------------------------------------------------
        await asyncio.sleep(random.randint(120, 300))

# ---------------------------------------------------------------------------
# Message event hook (called by bot wrappers)
# ---------------------------------------------------------------------------
async def on_message(state, config, sisters, author, content, channel_id):
    """
    Handles real-time family message events — triggers inter-sibling reactions
    and Will’s contextual responses.
    """
    if not author or not content:
        return

    try:
        # Route through sibling handler
        await handle_sister_message(state, config, sisters, author, content, channel_id)
        # Route to Will’s independent reaction logic
        await will_handle_message(state, config, sisters, author, content, channel_id)
    except Exception as e:
        log_event(f"[ERROR] on_message failed for {author}: {e}")

# ---------------------------------------------------------------------------
# Bootstrap entrypoint
# ---------------------------------------------------------------------------
def start_autonomy_system(state, config, sisters):
    """
    Starts the main family loop asynchronously — non-blocking entrypoint.
    """
    log_event("[BOOT] Starting autonomy system (AEDT synchronized).")
    asyncio.create_task(family_main_loop(state, config, sisters))
