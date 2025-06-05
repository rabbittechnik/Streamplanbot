import discord
import os
import json
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

WEEK_OPTIONS = [
    ("13.05.2025 - 19.05.2025", "13.05.2025", "19.05.2025"),
    ("20.05.2025 - 26.05.2025", "20.05.2025", "26.05.2025"),
    ("27.05.2025 - 02.06.2025", "27.05.2025", "02.06.2025")
]

DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
TIME_OPTIONS = [
    ("Kein Stream", "🟥"),
    ("Eventueller Stream", "🟨"),
    ("12:00 Uhr", "🟩"), ("14:00 Uhr", "🟩"), ("16:00 Uhr", "🟩"),
    ("18:00 Uhr", "🟩"), ("20:00 Uhr", "🟩"), ("22:00 Uhr", "🟩")
]

game_emojis = {
    "fortnite": "🔫",
    "call of duty": "🔫", "cod": "🔫",
    "minecraft": "⛏️",
    "gta": "🚗",
    "fifa": "⚽",
    "horror": "🧟",
    "just chatting": "💬",
    "league of legends": "🧙", "lol": "🧙",
    "valorant": "🎯",
    "apex": "🪂",
    "rocket league": "🚀",
    "tft": "♟️",
    "elden ring": "🗡️",
    "csgo": "🔫", "cs2": "🔫",
    "hogwarts legacy": "🧙‍♂️",
    "the sims": "🏠",
    "farming simulator": "🌾",
}

user_state = {}

SETTINGS_FILE = "channels.json"

def load_channels():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_channels(channels):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

channels_by_guild = load_channels()

# ---- Channel-Auswahl (Dropdown ODER Fallback) ----
class ChannelSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in guild.text_channels
        ][:25]  # Discord-Limit für Dropdown
        super().__init__(placeholder="Wähle den Ziel-Channel aus", options=options, min_values=1, max_values=1)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        cid = int(self.values[0])
        channels_by_guild[str(self.guild.id)] = cid
        save_channels(channels_by_guild)
        await interaction.response.send_message(
            f"✅ Channel wurde gespeichert! Streampläne werden ab jetzt in <#{cid}> gepostet.",
            ephemeral=True
        )

class FallbackModal(discord.ui.Modal, title="Channel-ID oder Name eingeben"):
    channel_input = discord.ui.TextInput(label="Channel-ID oder exakter Name", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        channel_val = self.channel_input.value.strip()
        guild = interaction.guild
        channel = None
        # Channel per ID oder Name suchen
        if channel_val.isdigit():
            channel = guild.get_channel(int(channel_val))
        if not channel:
            for ch in guild.text_channels:
                if ch.name == channel_val:
                    channel = ch
                    break
        if channel:
            channels_by_guild[str(guild.id)] = channel.id
            save_channels(channels_by_guild)
            await interaction.response.send_message(
                f"✅ Channel wurde gespeichert! Streampläne werden ab jetzt in <#{channel.id}> ({channel.mention}) gepostet.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Channel nicht gefunden! Bitte nochmal exakt angeben.",
                ephemeral=True
            )

class SetupView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=120)
        # Fallback-Button anbieten falls zu viele Channels
        if len(guild.text_channels) <= 25:
            self.add_item(ChannelSelect(guild))
        else:
            self.add_item(FallbackButton())

class FallbackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Channel per Name/ID eingeben", style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FallbackModal())

# ---- Woche wählen usw. ----
class WeekSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=label, value=label) for label, *_ in WEEK_OPTIONS]
        super().__init__(placeholder="Wähle die Woche (vom/bis)", options=options)

    async def callback(self, interaction: discord.Interaction):
        user_state[interaction.user.id] = {
            "week": self.values[0],
            "times": {},
            "games": {}
        }
        await interaction.response.edit_message(
            content="Wähle deine Streamzeiten:",
            view=StreamPlanTimePage1(interaction.user.id)
        )

class WeekView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(WeekSelect())

class TimeSelect(discord.ui.Select):
    def __init__(self, user_id, day):
        self.user_id = user_id
        options = [discord.SelectOption(label=label) for label, _ in TIME_OPTIONS]
        super().__init__(placeholder=day, options=options)

    async def callback(self, interaction: discord.Interaction):
        user_state[self.user_id]["times"][self.placeholder] = self.values[0]
        await interaction.response.defer()

class GameInput(discord.ui.TextInput):
    def __init__(self, day):
        super().__init__(label=f"{day} – Spielname", placeholder="z. B. Fortnite", required=False)
        self.day = day

class GameModal(discord.ui.Modal):
    def __init__(self, user_id):
        super().__init__(title="📺 Spiele eintragen")
        self.user_id = user_id
        self.inputs = []
        for day in DAYS:
            if user_state[user_id]["times"].get(day, "Kein Stream") != "Kein Stream":
                input_field = GameInput(day)
                self.inputs.append(input_field)
                self.add_item(input_field)

    async def on_submit(self, interaction: discord.Interaction):
        for field in self.inputs:
            user_state[self.user_id]["games"][field.day] = field.value or "?"
        await send_plan_embed(interaction)

class NavButton(discord.ui.Button):
    def __init__(self, label, target_view):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.target_view = target_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=self.target_view(interaction.user.id))

class GameInputButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Weiter zur Spieleingabe 🎮", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GameModal(interaction.user.id))

class StreamPlanTimePage1(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        for day in DAYS[:3]:
            self.add_item(TimeSelect(user_id, day))
        self.add_item(NavButton("Weiter ➡️", StreamPlanTimePage2))

class StreamPlanTimePage2(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        for day in DAYS[3:5]:
            self.add_item(TimeSelect(user_id, day))
        self.add_item(NavButton("⬅️ Zurück", StreamPlanTimePage1))
        self.add_item(NavButton("➡️ Weiter", StreamPlanTimePage3))

class StreamPlanTimePage3(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        for day in DAYS[5:]:
            self.add_item(TimeSelect(user_id, day))
        self.add_item(NavButton("⬅️ Zurück", StreamPlanTimePage2))
        self.add_item(GameInputButton())

# ---- Embed-Plan senden ----
async def send_plan_embed(interaction: discord.Interaction):
    data = user_state[interaction.user.id]
    week = data["week"]
    times = data["times"]
    games = data.get("games", {})

    embed = discord.Embed(
        title=f"📅 Streamplan der Woche ({week})",
        color=discord.Color.blurple(),
        timestamp=datetime.utcnow()
    )
    embed.set_author(
        name=interaction.user.name,
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )

    lines = []
    for day in DAYS:
        time = times.get(day, "Kein Stream")
        game = games.get(day, "-")

        emoji = next((e for label, e in TIME_OPTIONS if label == time), "⚪")
        g = game.lower()
        game_icon = "🎮"
        for key, em in game_emojis.items():
            if key in g:
                game_icon += " " + em
                break

        if time == "Kein Stream":
            line = f"{emoji} **{day}** — Kein Stream    🎮 -"
        elif time == "Eventueller Stream":
            line = f"{emoji} **{day}** — Eventueller Stream {game_icon} **{game}**"
        else:
            line = f"{emoji} **{day}** — {time.ljust(14)} {game_icon} **{game}**"

        lines.append(line)
        lines.append("")  # Leerzeile

    embed.description = "\n".join(lines)

    # Sende an den konfigurierten Channel!
    guild_id = str(interaction.guild_id)
    if guild_id in channels_by_guild:
        channel_id = channels_by_guild[guild_id]
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Dein Streamplan wurde gepostet!", ephemeral=True)
            return

    await interaction.response.send_message("❌ Ziel-Channel nicht gesetzt! Bitte führe zuerst /setup aus.", ephemeral=True)

# ---- Slash-Commands ----

@tree.command(name="setup", description="Wähle den Channel, in dem der Bot posten soll (nur Admins!)")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    # Prüfe auf viele Channels, dann Fallback zu Modal
    if len(interaction.guild.text_channels) <= 25:
        await interaction.response.send_message(
            "Bitte wähle einen Ziel-Channel:",
            view=SetupView(interaction.guild),
            ephemeral=True
        )
    else:
        await interaction.response.send_modal(FallbackModal())

@tree.command(name="streamplan", description="Erstelle deinen wöchentlichen Streamplan")
async def streamplan(interaction: discord.Interaction):
    await interaction.response.send_message("📅 Wähle die Woche:", view=WeekView(), ephemeral=True)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"🤖 Bot bereit: {bot.user}")

bot.run(TOKEN)
