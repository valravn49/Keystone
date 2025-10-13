from discord.ext import commands

intents = commands.Intents.default()
intents.message_content = True
intents.guilds = True

class WillBot(commands.Bot):
    def __init__(self, info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = info

will_bot = WillBot({"name": "Will", "env_var": "WILL_TOKEN"})
