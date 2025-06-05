import discord
import os
import json
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Dynamisch: Aktuelle + 2 weitere Wochen berechnen
def get_week_options():
    today = datetime.now()
    start = today - timedelta(days=today.weekday())
    week_options = []
    for i in range(3):
        ws = start + timedelta(weeks=i)
        we = ws + timedelta(days=6)
        week_label = f"{ws.strftime('%d.%m.%Y')} - {we.strftime('%d.%m.%Y')}"
        week_options.append((week_label, ws.strftime('%d.%m.%Y'), we.strftime('%d.%m.%Y')))
    return week_options

DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
SPECIALS = ["Kein Stream", "Eventueller Stream"]

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

class ChannelSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in guild.text_channels
        ][:25]
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
        if len(guild.text_channels) <= 25:
            self.add_item(ChannelSelect(guild))
        else:
            self.add_item(FallbackButton())

class FallbackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Channel per Name/ID eingeben", style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FallbackModal())

# --- Woche wählen ---
class WeekSelect(discord.ui.Select):
    def __init__(self):
        week_options = get_week_options()
        options = [discord.SelectOption(label=label, value=label) for label, *_ in week_options]
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

# --- NEU: Zeit-Eingabe als Textfeld + Buttons ---
class TimeInputModal(discord.ui.Modal):
    def __init__(self, user_id, day):
        super().__init__(title=f"{day}: Uhrzeit eingeben")
        self.user_id = user_id
        self.day = day
        self.time_input = discord.ui.TextInput(
            label="Uhrzeit im Format HH:MM (z.B. 18:00)",
            placeholder="z.B. 18:00",
            required=False,
            max_length=5
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.time_input.value.strip()
        if not val:
            await interaction.response.send_message("❌ Bitte gib eine Uhrzeit im Format HH:MM ein!", ephemeral=True)
            return
        # Validierungs-RegEx: 00:00 bis 23:59
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", val):
            await interaction.response.send_message("❌ Ungültiges Format! Bitte z.B. 18:00 eingeben.", ephemeral=True)
            return
        user_state[self.user_id]["times"][self.day] = val
        # Zeige erneut die View für diese Seite
        await interaction.response.edit_message(view=page_view_by_day(self.user_id, self.day))

class KeinStreamButton(discord.ui.Button):
    def __init__(self, user_id, day):
        super().__init__(label="Kein Stream", style=discord.ButtonStyle.danger, row=0)
        self.user_id = user_id
        self.day = day

    async def callback(self, interaction: discord.Interaction):
        user_state[self.user_id]["times"][self.day] = "Kein Stream"
        await interaction.response.edit_message(view=page_view_by_day(self.user_id, self.day))

class EventuellButton(discord.ui.Button):
    def __init__(self, user_id, day):
        super().__init__(label="Eventuell", style=discord.ButtonStyle.secondary, row=0)
        self.user_id = user_id
        self.day = day

    async def callback(self, interaction: discord.Interaction):
        user_state[self.user_id]["times"][self.day] = "Eventueller Stream"
        await interaction.response.edit_message(view=page_view_by_day(self.user_id, self.day))

class ZeitEingabeButton(discord.ui.Button):
    def __init__(self, user_id, day):
        super().__init__(label="Uhrzeit eingeben", style=discord.ButtonStyle.success, row=1)
        self.user_id = user_id
        self.day = day

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TimeInputModal(self.user_id, self.day))

def page_view_by_day(user_id, first_day):
    # Sucht heraus, auf welcher Seite sich dieser Tag befindet, und gibt die richtige View zurück
    idx = DAYS.index(first_day)
    if idx < 3:
        return StreamPlanTimePage1(user_id)
    elif idx < 5:
        return StreamPlanTimePage2(user_id)
    else:
        return StreamPlanTimePage3(user_id)

class StreamPlanTimePage1(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        for day in DAYS[:3]:
            # Zeile mit "Kein Stream", "Eventuell", "Uhrzeit eingeben"
            self.add_item(KeinStreamButton(user_id, day))
            self.add_item(EventuellButton(user_id, day))
            self.add_item(ZeitEingabeButton(user_id, day))
        self.add_item(NavButton("Weiter ➡️", StreamPlanTimePage2, user_id))

class StreamPlanTimePage2(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        for day in DAYS[3:5]:
            self.add_item(KeinStreamButton(user_id, day))
            self.add_item(EventuellButton(user_id, day))
            self.add_item(ZeitEingabeButton(user_id, day))
        self.add_item(NavButton("⬅️ Zurück", StreamPlanTimePage1, user_id))
        self.add_item(NavButton("➡️ Weiter", StreamPlanTimePage3, user_id))

class StreamPlanTimePage3(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        for day in DAYS[5:]:
            self.add_item(KeinStreamButton(user_id, day))
            self.add_item(EventuellButton(user_id, day))
            self.add_item(ZeitEingabeButton(user_id, day))
        self.add_item(NavButton("⬅️ Zurück", StreamPlanTimePage2, user_id))
        self.add_item(GameInputButton())

class NavButton(discord.ui.Button):
    def __init__(self, label, target_view, user_id):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.target_view = target_view
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=self.target_view(self.user_id))

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

class GameInputButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Weiter zur Spieleingabe 🎮", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GameModal(interaction.user.id))

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

        # Emoji je nach Art
        if time == "Kein Stream":
            emoji = "🟥"
        elif time == "Eventueller Stream":
            emoji = "🟨"
        else:
            emoji = "🟩"

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
            line = f"{emoji} **{day}** — {str(time).ljust(14)} {game_icon} **{game}**"

        lines.append(line)
        lines.append("")  # Leerzeile

    embed.description = "\n".join(lines)

    guild_id = str(interaction.guild_id)
    if guild_id in channels_by_guild:
        channel_id = channels_by_guild[guild_id]
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Dein Streamplan wurde gepostet!", ephemeral=True)
            return

    await interaction.response.send_message("❌ Ziel-Channel nicht gesetzt! Bitte führe zuerst /setup aus.", ephemeral=True)

@tree.command(name="setup", description="Wähle den Channel, in dem der Bot posten soll (nur Admins!)")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
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
