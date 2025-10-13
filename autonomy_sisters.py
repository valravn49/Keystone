import os
import discord
from discord.ext import commands

# Recreate each sister’s Discord bot client
from logger import log_event
from aria_commands import setup_aria_commands

intents = commands.Intents.default()
intents.message_content = True
intents.guilds = True


class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        # only Aria needs slash command registration
        if self.sister_info["name"] == "Aria":
            setup_aria_commands(self.tree, None, None, None, None)
            await self.tree.sync()


# Shared instance list
sisters = [
    SisterBot({"name": "Aria", "env_var": "ARIA_TOKEN"}),
    SisterBot({"name": "Selene", "env_var": "SELENE_TOKEN"}),
    SisterBot({"name": "Cassandra", "env_var": "CASSANDRA_TOKEN"}),
    SisterBot({"name": "Ivy", "env_var": "IVY_TOKEN"}),
]
