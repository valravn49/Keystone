# main.py
import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz
from fastapi import FastAPI

from logger import log_event

# ---- Load config early ------------------------------------------------------
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config: Dict = json.load(f)

# ---- Timezone (Australia/Sydney = AEDT/AEST with DST auto handled) ----------
AEDT = pytz.timezone("Australia/Sydney")

# ---- State manager ----------------------------------------------------------
from Autonomy.state_manager import state, load_state, save_state

# ---- Behaviors (per-sibling) ------------------------------------------------
from Autonomy.behaviors.aria_behavior import (
    ensure_aria_systems, aria_handle_message,
)
from Autonomy.behaviors.selene_behavior import (
    ensure_selene_systems, selene_handle_message,
)
from Autonomy.behaviors.cassandra_behavior import (
    ensure_cass_systems, cass_handle_message,
)
from Autonomy.behaviors.ivy_behavior import (
    ensure_ivy_systems, ivy_handle_message,
)
from Autonomy.behaviors.will_behavior import (
    ensure_will_systems, will_handle_message,
)

# ---- Shared helpers ---------------------------------------------------------
from shared_context import get_today_rotation, advance_rotation, get_current_theme

# ---- Fitness & food ---------------------------------------------------------
#   We defensively support a few likely function names so you don't need to refactor nutrition.py/workouts.py
try:
    from workouts import get_today_workout
except Exception:
    get_today_workout = None

try:
    from nutrition import build_day_plan as _build_day_plan
except Exception:
    try:
        from nutrition import get_daily_meal_plan as _build_day_plan
    except Exception:
        _build_day_plan = None

# ---- Outfit & images --------------------------------------------------------
#   image_utils is allowed to point at real generators or just save prompts;
#   We only rely on these names, but guard with fallbacks.
try:
    from image_utils import (
        generate_outfit_image,      # (name, portrait_path, style_hint, season, save_dir) -> path
        process_image,              # (path) -> path
        pick_season_for_date,       # (dt) -> "spring"/"summer"/"autumn"/"winter"
        build_outfit_prompt,        # (name, personality_json, season, special) -> str
        get_portrait_path,          # (name, bold:bool=False) -> str
    )
except Exception:
    # Soft shims so the server still boots if some utils are missing
    def generate_outfit_image(*a, **k): return None
    def process_image(path): return path
    def pick_season_for_date(dt):  # AU seasons
        m = dt.month
        if m in (12, 1, 2): return "summer"
        if m in (3, 4, 5):  return "autumn"
        if m in (6, 7, 8):  return "winter"
        return "spring"
    def build_outfit_prompt(*a, **k): return "daily outfit"
    def get_portrait_path(name, bold=False):
        # default portraits directory if not specified
        base = config.get("portraits_dir", "/app/Autonomy/portraits")
        fname = f"{name.lower()}_fem.png" if (name == "Will" and bold) else f"{name.lower()}.png"
        return os.path.join(base, fname)

# =============================================================================
# FastAPI app
# =============================================================================
app = FastAPI(title="Family Orchestrator", version="2.0")

# =============================================================================
# Bot wiring
# =============================================================================

# In-process "sisters" list is managed by your Discord launcher code elsewhere.
# We keep a holder here so behaviors can post if bots are injected.
sisters: List = []  # type: ignore

HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

ENSURE = [
    ensure_aria_systems,
    ensure_selene_systems,
    ensure_cass_systems,
    ensure_ivy_systems,
    ensure_will_systems,
]

NAMES = ["Aria", "Selene", "Cassandra", "Ivy", "Will"]


# =============================================================================
# Utilities
# =============================================================================

def aedt_now() -> datetime:
    return datetime.now(AEDT)

def post_to_family(text: str, sender: str):
    """Send text to the configured family channel using the right bot instance, if available."""
    channel_id = config.get("family_group_channel")
    if not channel_id:
        log_event(f"[WARN] No family_group_channel in config; message from {sender} not delivered: {text}")
        return
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            ch = bot.get_channel(channel_id)
            if ch:
                # fire and forget
                asyncio.create_task(ch.send(text))
                log_event(f"[POST] {sender}: {text}")
            return
    # Fallback: log only
    log_event(f"[FALLBACK-POST] {sender}: {text} (no live Discord client found)")

def read_personality(name: str) -> Dict:
    pdir = config.get("personalities_dir", "/app/Autonomy/Personalities")
    path = os.path.join(pdir, f"{name}_Personality.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Failed loading personality for {name}: {e}")
        return {"name": name}

def is_special_day(dt: datetime) -> Optional[str]:
    """Return special label if the date should have a themed outfit."""
    m, d = dt.month, dt.day
    if m == 10 and d == 31:
        return "halloween"
    if m == 12 and d in (24, 25):
        return "christmas"
    if m == 12 and d == 31:
        return "new_years_eve"
    if m == 1 and d == 1:
        return "new_years_day"
    return None

# =============================================================================
# Outfit generation per sibling (image + small caption)
# =============================================================================

async def generate_and_post_outfits_for_all():
    dt = aedt_now()
    season = pick_season_for_date(dt)
    special = is_special_day(dt)
    out_dir = config.get("outfit_output_dir", "/app/data/outfits")

    os.makedirs(out_dir, exist_ok=True)

    for name in NAMES:
        # Will uses masc/fem portrait choice depending on "bold" mode flag in memory (if present)
        bold = False
        if name == "Will":
            # timid/bold can be persisted by your behaviors; we read a simple flag if available
            bold = bool(state.get("Will_bold_mode", False))

        persona = read_personality(name)
        portrait = get_portrait_path(name, bold=bold)
        style_hint = build_outfit_prompt(name, persona, season, special)

        img_path = None
        try:
            img_path = generate_outfit_image(
                name=name,
                portrait_path=portrait,
                style_hint=style_hint,
                season=season,
                save_dir=out_dir,
            )
            if img_path:
                img_path = process_image(img_path)  # optional enhancement/resize/etc.
        except Exception as e:
            log_event(f"[ERROR] Outfit gen failed for {name}: {e}")

        # Text-only fallback
        tag = f" — {special}" if special else ""
        caption = f"🧵 {name} — today’s fit: {season}{tag} • {style_hint}"
        post_to_family(caption, sender=name)

        # If your bots support file upload via .send(file=...), add that here.
        # We keep text-only to stay transport-agnostic.

# =============================================================================
# Nutrition & Workout planners
# =============================================================================

def build_daily_nutrition_tip() -> Optional[str]:
    """Return a compact, friendly day tip (kept very short so it fits in chat)."""
    if not _build_day_plan:
        return None
    try:
        plan = _build_day_plan(aedt_now().date())  # accept either date or no arg
    except TypeError:
        plan = _build_day_plan()
    except Exception as e:
        log_event(f"[WARN] nutrition plan failed: {e}")
        return None

    # Plan can be dict or str; normalize to a concise line
    if isinstance(plan, dict):
        # pull a few highlights if present
        kcals = plan.get("calories")
        notes = plan.get("notes") or plan.get("tip") or ""
        meals = plan.get("meals") or []
        headline_meal = ""
        if isinstance(meals, list) and meals:
            m0 = meals[0]
            headline_meal = m0.get("name") if isinstance(m0, dict) else str(m0)
        pieces = []
        if kcals: pieces.append(f"{kcals} kcal")
        if headline_meal: pieces.append(headline_meal)
        if notes: pieces.append(notes)
        return " • ".join(pieces) if pieces else None
    elif isinstance(plan, str):
        return plan.strip()[:240]
    return None

def build_today_workout_line() -> Optional[str]:
    if not get_today_workout:
        return None
    try:
        block = get_today_workout()
    except TypeError:
        try:
            block = get_today_workout(aedt_now().date())
        except Exception:
            block = None
    except Exception as e:
        log_event(f"[WARN] workout build failed: {e}")
        block = None
    if not block:
        return None
    # keep tidy
    return str(block).strip()

# =============================================================================
# Rituals (lead/support/rest) — handled here
# =============================================================================

def choose_awake(names: List[str]) -> List[str]:
    """Basic awake filter window using schedules from config; lead is always awake for rituals."""
    now_h = aedt_now().hour
    awake = []
    schedules = config.get("schedules", {})
    for n in names:
        rng = schedules.get(n, {"wake": [6, 8], "sleep": [22, 23]})
        w_lo, w_hi = int(rng["wake"][0]), int(rng["wake"][1])
        s_lo, s_hi = int(rng["sleep"][0]), int(rng["sleep"][1])
        # inclusive open interval with overnight wrap
        if w_lo == s_lo:
            awake.append(n)
            continue
        if w_lo < s_lo:
            if w_lo <= now_h < s_lo:
                awake.append(n)
        else:
            if now_h >= w_lo or now_h < s_lo:
                awake.append(n)
    return awake

async def send_morning_message():
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead = rotation["lead"]

    workouts_line = build_today_workout_line()
    nutrition_tip = build_daily_nutrition_tip()

    parts = [f"🌅 Morning — theme: {theme}."]
    if workouts_line:
        parts.append(f"🏋️ Today: {workouts_line}")
    if nutrition_tip:
        parts.append(f"🥗 Tip: {nutrition_tip}")

    msg = "  ".join(parts)
    post_to_family(msg, sender=lead)

    # Have SUPPORT siblings answer (rest may or may not)
    awake = choose_awake(NAMES)
    responders = [n for n in rotation["supports"] if n in awake]
    # guarantee at least one response
    if not responders and rotation["rest"] in awake:
        responders = [rotation["rest"]]

    async def _poke(name: str):
        handler = HANDLERS.get(name)
        if not handler:
            return
        try:
            # minimal synthetic message to kick their handler in their own voice
            await handler(state, config, sisters, lead, msg, config.get("family_group_channel", 0))
        except Exception as e:
            log_event(f"[WARN] morning poke failed for {name}: {e}")

    # space responses a bit
    for i, n in enumerate(responders):
        asyncio.create_task(asyncio.sleep(5 + i * 6))
        asyncio.create_task(_poke(n))

    # generate outfits (non-blocking)
    asyncio.create_task(generate_and_post_outfits_for_all())

    # Advance daily rotation after the morning ritual
    advance_rotation(state, config)
    save_state(state)

async def send_night_message():
    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]

    # tomorrow workout preview if available
    tomorrow_line = None
    if get_today_workout:
        try:
            tomorrow_line = get_today_workout(aedt_now().date() + timedelta(days=1))
        except Exception:
            pass

    msg = "🌙 Night — reset, hydrate, and rest."
    if tomorrow_line:
        msg += f"  🔜 Tomorrow: {tomorrow_line}"
    post_to_family(msg, sender=lead)
    save_state(state)

# =============================================================================
# Schedulers
# =============================================================================

async def daily_loop():
    """Checks every 3 minutes for morning/night windows in AEDT and triggers once."""
    while True:
        now = aedt_now()
        h, m = now.hour, now.minute

        # Morning window 06:00–07:59 (run once)
        if 6 <= h < 8 and not state.get("morning_done"):
            await send_morning_message()
            state["morning_done"] = True
            save_state(state)

        # Reset morning flag after 09:00
        if h >= 9 and state.get("morning_done"):
            state["morning_done"] = False

        # Night window 21:00–22:59 (run once)
        if 21 <= h < 23 and not state.get("night_done"):
            await send_night_message()
            state["night_done"] = True
            save_state(state)

        # Reset night flag after 00:30
        if (h == 0 and m >= 30) and state.get("night_done"):
            state["night_done"] = False

        await asyncio.sleep(180)

# =============================================================================
# FastAPI lifecycle
# =============================================================================

@app.on_event("startup")
async def startup_event():
    load_state()
    # Initialize sibling systems (schedules, chatter loops, etc.)
    for ensure in ENSURE:
        try:
            ensure(state, config, sisters)
        except Exception as e:
            log_event(f"[WARN] ensure() failed: {e}")

    # Start daily scheduler
    asyncio.create_task(daily_loop())
    log_event("[STARTUP] Orchestrator ready.")

@app.on_event("shutdown")
async def shutdown_event():
    save_state(state)
    log_event("[SHUTDOWN] State saved.")

# =============================================================================
# Endpoints (debug/admin)
# =============================================================================

@app.get("/health")
def health():
    now = aedt_now().isoformat()
    return {"status": "ok", "aedt": now, "rotation": get_today_rotation(state, config)}

@app.post("/run/morning")
async def run_morning_now():
    await send_morning_message()
    return {"ran": "morning"}

@app.post("/run/night")
async def run_night_now():
    await send_night_message()
    return {"ran": "night"}

@app.post("/run/outfits")
async def run_outfits_now():
    await generate_and_post_outfits_for_all()
    return {"ran": "outfits"}

@app.post("/simulate")
async def simulate(author: str, content: str):
    """Trigger handlers to reply as siblings to an arbitrary message."""
    # Basic relay to all others
    for name, handler in HANDLERS.items():
        if name.lower() == author.lower():
            continue
        try:
            await handler(state, config, sisters, author, content, config.get("family_group_channel", 0))
        except Exception as e:
            log_event(f"[SIM] handler {name} error: {e}")
    return {"ok": True}
