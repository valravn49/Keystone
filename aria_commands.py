import discord
from nutrition import (
    log_food_entry,
    log_workout_completion,
    set_calorie_targets,
    get_daily_summary
)
from logger import log_event, log_cage_event, log_plug_event, log_service_event


def setup_aria_commands(
    tree,
    state,
    get_today_rotation,
    get_current_theme,
    send_morning_message,
    send_night_message
):
    """
    Register Aria's slash commands on the given CommandTree.
    """

    # ==============================
    # Rotation & Ritual Commands
    # ==============================
    @tree.command(name="force-rotate", description="Manually advance sister rotation")
    async def slash_force_rotate(interaction: discord.Interaction):
        state["rotation_index"] += 1
        rotation = get_today_rotation()
        log_event(f"[SLASH] Rotation advanced via slash. New lead: {rotation['lead']}")
        await interaction.response.send_message(
            f"🔄 Rotation advanced. New lead: **{rotation['lead']}**"
        )

    @tree.command(name="force-morning", description="Force the morning message")
    async def slash_force_morning(interaction: discord.Interaction):
        await send_morning_message()
        await interaction.response.send_message("☀️ Morning message forced.")

    @tree.command(name="force-night", description="Force the night message")
    async def slash_force_night(interaction: discord.Interaction):
        await send_night_message()
        await interaction.response.send_message("🌙 Night message forced.")

    # ==============================
    # Structured Logs
    # ==============================
    @tree.command(name="log-cage", description="Log a cage status update")
    async def slash_log_cage(interaction: discord.Interaction, status: str, notes: str = ""):
        log_cage_event(str(interaction.user), status, notes)
        await interaction.response.send_message(f"🔒 Cage log saved: {status} {notes}")

    @tree.command(name="log-plug", description="Log a plug training session")
    async def slash_log_plug(interaction: discord.Interaction, size: str, duration: str, notes: str = ""):
        log_plug_event(str(interaction.user), size, duration, notes)
        await interaction.response.send_message(f"🍑 Plug log saved: {size} for {duration}")

    @tree.command(name="log-service", description="Log a service task completion")
    async def slash_log_service(interaction: discord.Interaction, task: str, result: str, notes: str = ""):
        log_service_event(str(interaction.user), task, result, notes)
        await interaction.response.send_message(f"📝 Service log saved: {task} → {result}")

    # ==============================
    # Nutrition Commands
    # ==============================
    @tree.command(name="log-food", description="Log food calories")
    async def slash_log_food(interaction: discord.Interaction, food: str, calories: int):
        log_food_entry(str(interaction.user), food, calories)
        await interaction.response.send_message(f"🍽️ Logged {food} ({calories} kcal)")

    @tree.command(name="log-workout", description="Log workout completion")
    async def slash_log_workout(interaction: discord.Interaction, workout_name: str, duration: int):
        try:
            calories = log_workout_completion(str(interaction.user), workout_name, duration)
            await interaction.response.send_message(
                f"💪 Workout logged: {workout_name} ({duration} mins, {calories} kcal burned)"
            )
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {str(e)}", ephemeral=True)

    @tree.command(name="set-calories", description="Set calorie targets for weight loss and maintenance")
    async def slash_set_calories(interaction: discord.Interaction, weight_loss: int, maintenance: int):
        set_calorie_targets(weight_loss, maintenance)
        await interaction.response.send_message(
            f"⚖️ Calorie targets updated: {weight_loss} (loss) / {maintenance} (maintenance)"
        )

    @tree.command(name="nutrition-summary", description="Get today’s calorie/workout summary")
    async def slash_nutrition_summary(interaction: discord.Interaction):
        summary = get_daily_summary()
        await interaction.response.send_message(summary, ephemeral=True)
