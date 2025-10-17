import os
import asyncio
from datetime import datetime, timedelta
import pytz

# -------------------------------------------------------------------
# Core imports
# -------------------------------------------------------------------
from logger import log_event
from Autonomy.state_manager import state, load_state, save_state
from image_utils import generate_and_post_daily_outfits
from workouts import get_today_workout

# -------------------------------------------------------------------
# Behavior imports (aliased for consistency)
# -------------------------------------------------------------------
from Autonomy.behaviors.aria_behavior import (
    aria_handle_message as handle_aria_behavior,
    ensure_aria_systems,
)
from Autonomy.behaviors.selene_behavior import (
    selene_handle_message as handle_selene_behavior,
    ensure_selene_systems,
)
from Autonomy.behaviors.cassandra_behavior import (
    cass_handle_message as handle_cassandra_behavior,
    ensure_cass_systems,
)
from Autonomy.behaviors.ivy_behavior import (
    ivy_handle_message as handle_ivy_behavior,
    ensure_ivy_systems,
)
from Autonomy.behaviors.will_behavior import (
    will_handle_message as handle_will_behavior,
    ensure_will_systems,
)

# -------------------------------------------------------------------
# Rituals (morning/night)
# -------------------------------------------------------------------
from sisters_behavior import send_morning_message, send_night_message, send_spontaneous_task

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
AEST = pytz.timezone("Australia/Sydney")
DAILY_MORNING_HOUR = 6
DAILY_NIGHT_HOUR = 21
SPONTANEOUS_INTERVAL_MIN = 60 * 30
SPONTANEOUS_INTERVAL_MAX = 60 * 90

# -------------------------------------------------------------------
# Async scheduling helpers
# -------------------------------------------------------------------
async def run_morning_ritual(config, sisters):
    """Trigger morning message, workout, and outfit generation."""
    log_event("☀️ Running morning ritual...")
    await send_morning_message(state, config, sisters)
    await generate_and_post_daily_outfits(config, sisters)
    save_state(state)
    log_event("✅ Morning ritual complete.")

async def run_night_ritual(config, sisters):
    """Trigger nightly reflection and prep for tomorrow."""
    log_event("🌙 Running night ritual...")
    await send_night_message(state, config, sisters)
    save_state(state)
    log_event("✅ Night ritual complete.")

async def run_spontaneous_conversation(config, sisters):
    """Occasional mid-day sibling chatter."""
    log_event("💬 Checking for spontaneous chatter...")
    await send_spontaneous_task(state, config, sisters)
    save_state(state)

# -------------------------------------------------------------------
# Main scheduler
# -------------------------------------------------------------------
async def scheduler_loop(config, sisters, will_bot):
    """Run periodic checks for time-based rituals and chatter."""
    last_morning = None
    last_night = None
    last_spontaneous = datetime.now(AEST)

    # Start background chatter loops for each sibling
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cassandra_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, [will_bot])

    log_event("🕒 Scheduler started under AEST timezone.")

    while True:
        now = datetime.now(AEST)

        # Morning ritual at 6 AM
        if now.hour == DAILY_MORNING_HOUR and (not last_morning or (now - last_morning).seconds > 3600):
            await run_morning_ritual(config, sisters)
            last_morning = now

        # Night ritual at 9 PM
        if now.hour == DAILY_NIGHT_HOUR and (not last_night or (now - last_night).seconds > 3600):
            await run_night_ritual(config, sisters)
            last_night = now

        # Random spontaneous sibling chatter
        if (now - last_spontaneous).seconds > SPONTANEOUS_INTERVAL_MIN:
            if (now - last_spontaneous).seconds > SPONTANEOUS_INTERVAL_MAX or os.urandom(1)[0] > 128:
                await run_spontaneous_conversation(config, sisters)
                last_spontaneous = now

        await asyncio.sleep(60)  # Check every minute

# -------------------------------------------------------------------
# Discord startup
# -------------------------------------------------------------------
async def start_family(config, sisters, will_bot):
    """Start all Discord bots and launch scheduler."""
    log_event("🚀 Starting family bots...")
    load_state()

    try:
        await asyncio.gather(
            *[s.start(s.token) for s in sisters],
            will_bot.start(will_bot.token),
            scheduler_loop(config, sisters, will_bot),
        )
    except Exception as e:
        log_event(f"[ERROR] Family startup failed: {e}")
    finally:
        save_state(state)
        log_event("💾 State saved and bots shut down.")

# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------
if __name__ == "__main__":
    import config

    sisters = config.SISTERS
    will_bot = config.WILL_BOT

    try:
        asyncio.run(start_family(config.CONFIG, sisters, will_bot))
    except KeyboardInterrupt:
        log_event("🛑 Manual shutdown triggered.")
        save_state(state)
