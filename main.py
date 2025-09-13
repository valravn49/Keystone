# ==============================
# Scheduled Messages
# ==============================
async def send_morning_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead = rotation["lead"]
    rest = rotation["rest"]
    supports = ", ".join(rotation["supports"])

    # Personality-specific opening
    if lead == "Aria":
        opening = "🌅 Good morning, love. Let’s begin the day calmly and with order."
    elif lead == "Selene":
        opening = "🌅 Mmm… good morning, dreamer. Let’s flow softly into today together."
    elif lead == "Cassandra":
        opening = "🌅 Good morning. Stand tall, be proud, and show me your discipline today."
    elif lead == "Ivy":
        opening = "🌅 Hey cutie, morning! I bet you’re still warm in bed, but I’m watching~"
    else:
        opening = f"🌅 Good morning from **{lead}**!"

    msg = (
        f"{opening}\n\n"
        f"🌟 Lead: {lead} | 🌙 Rest: {rest} | ✨ Support: {supports}\n\n"
        f"Today's weekly theme is **{theme}**.\n"
        f"Remember:\n"
        f"- Complete your chastity log.\n"
        f"- Skincare morning routine.\n"
        f"- Confirm morning cage hygiene checklist (`done`).\n"
        f"- Evening journal later today.\n"
        f"Formal outfits & training gear only for logging.\n"
        f"Log wake-up time as discipline.\n"
    )
    await post_to_family(msg)
    state["rotation_index"] += 1
    print(f"[SCHEDULER] Morning message sent by {lead}")

async def send_night_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead = rotation["lead"]
    rest = rotation["rest"]
    supports = ", ".join(rotation["supports"])

    # Personality-specific opening
    if lead == "Aria":
        opening = "🌙 Good night, love. Rest peacefully, tomorrow is another steady step."
    elif lead == "Selene":
        opening = "🌙 Shhh… the night embraces you. Drift into dreams softly."
    elif lead == "Cassandra":
        opening = "🌙 Good night. You’ve had your orders—reflect and be honest with yourself."
    elif lead == "Ivy":
        opening = "🌙 Night night, sweet thing. Don’t think I won’t check in your dreams~"
    else:
        opening = f"🌙 Good night from **{lead}**."

    msg = (
        f"{opening}\n\n"
        f"🌟 Lead: {lead} | 🌙 Rest: {rest} | ✨ Support: {supports}\n\n"
        f"Reflection: Did you rise promptly at 6:00am? Log success or slip.\n"
        f"Tonight’s theme flavor is still **{theme}**.\n"
        f"Formal outfits & training gear only are logged (no underwear/loungewear).\n"
        f"Overnight plug check: confirm if planned.\n"
    )
    await post_to_family(msg)
    print(f"[SCHEDULER] Night message sent by {lead}")
