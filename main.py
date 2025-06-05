import discord
import os
import json
import re
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

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

def get_week_options():
    today = datetime.today()
    week_options = []
    this_monday = today - timedelta(days=today.weekday())
    for i in range(3):
        start = this_monday + timedelta(days=i*7)
        end = start + timedelta(days=6)
        label = f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        week_options.append((label, start.strftime('%d.%m.%Y'), end.strftime('%d.%m.%Y')))
    return week_options

def is_valid_time(timestr):
    return bool(re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", timestr))

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

# ---- Woche wählen (dynamisch) ----
class WeekSelect(discord.ui.Select):
    def __init__(self):
        week_options = get_week_options()
        options = [discord.SelectOption(label=label, value=label) for label, *_ in week_options]
        super().__init__(placeholder="Wähle die Woche (vom/bis)", options=options)

    async def callback(self, interaction: discord.Interaction):
        user_state[interaction.user.id] = {
            "week": self.values[0],
            "days": {},
            "times": {},
            "games": {}
        }
        await interaction.response.edit_message(
            content="Für jeden Tag auswählen: Kein Stream / Eventuell / Stream",
            view=StreamTypePage(interaction.user.id, page=1)
        )

class WeekView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(WeekSelect())

# ---- Tages-Auswahl pro Tag (Kein Stream / Eventuell / Stream) ----
class StreamTypeSelect(discord.ui.Select):
    def __init__(self, user_id, day):
        options = [
            discord.SelectOption(label="Kein Stream", value="Kein Stream", emoji="🟥"),
            discord.SelectOption(label="Eventueller Stream", value="Eventuell", emoji="🟨"),
            discord.SelectOption(label="Stream", value="Stream", emoji="🟩"),
        ]
        super().__init__(placeholder=day, options=options)
        self.user_id = user_id
        self.day = day

    async def callback(self, interaction: discord.Interaction):
        user_state[self.user_id]["days"][self.day] = self.values[0]
        await interaction.response.defer()

# ---- Navigation-Button (View-Wechsel) ----
class NavButton(discord.ui.Button):
    def __init__(self, label, target_view_func):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.target_view_func = target_view_func

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=self.target_view_func(interaction.user.id))

# ---- Tages-Auswahl-Page (3 Tage pro Seite) ----
class StreamTypePage(discord.ui.View):
    def __init__(self, user_id, page=1):
        super().__init__(timeout=300)
        days_per_page = 3
        start_idx = (page-1) * days_per_page
        end_idx = start_idx + days_per_page
        self.user_id = user_id
        self.page = page
        days = DAYS[start_idx:end_idx]
        for day in days:
            self.add_item(StreamTypeSelect(user_id, day))
        if start_idx > 0:
            self.add_item(NavButton("⬅️ Zurück", lambda uid: StreamTypePage(uid, page-1)))
        if end_idx < len(DAYS):
            self.add_item(NavButton("➡️ Weiter", lambda uid: StreamTypePage(uid, page+1)))
        else:
            self.add_item(NavButton("Weiter zu Uhrzeit", lambda uid: StreamTimeInputPage(uid, 1)))

# ---- Zeit-Eingabe-Page (Seitenweise für ausgewählte Tage, 3 pro Seite, immer EIN Modal pro Seite) ----
class TimeTextMultiModal(discord.ui.Modal):
    def __init__(self, user_id, days, page, total_pages):
        super().__init__(title=f"Uhrzeiten eintragen ({page}/{total_pages})")
        self.user_id = user_id
        self.days = days
        self.inputs = []
        for day in days:
            input_field = discord.ui.TextInput(
                label=f"{day} – Uhrzeit", 
                placeholder="z.B. 18:00", 
                required=True
            )
            self.inputs.append(input_field)
            self.add_item(input_field)
        self.page = page
        self.total_pages = total_pages

    async def on_submit(self, interaction: discord.Interaction):
        for idx, day in enumerate(self.days):
            value = self.inputs[idx].value
            if not is_valid_time(value):
                await interaction.response.send_message(
                    f"❌ Ungültiges Uhrzeit-Format für {day}! Bitte als HH:MM (z.B. 18:00) eingeben.", ephemeral=True
                )
                return
            user_state[self.user_id]["times"][day] = value

        selected_days = [d for d, v in user_state[self.user_id]["days"].items() if v in ("Eventuell", "Stream")]
        days_per_page = 3
        next_page = self.page + 1
        start_idx = (next_page - 1) * days_per_page
        next_days = selected_days[start_idx:start_idx+days_per_page]
        total_pages = (len(selected_days) + days_per_page - 1) // days_per_page

        if next_days:
            await interaction.response.edit_message(
                content="Weitere Uhrzeiten eintragen:",
                view=StreamTimeInputPage(self.user_id, next_page, total_pages)
            )
        else:
            await interaction.response.edit_message(
                content="Spiele eintragen (optional):",
                view=GameInputButtonView()
            )

class TimeInputMultiButton(discord.ui.Button):
    def __init__(self, user_id, days, page, total_pages):
        super().__init__(
            label=f"Uhrzeiten für {', '.join(days)} eintragen",
            style=discord.ButtonStyle.primary
        )
        self.user_id = user_id
        self.days = days
        self.page = page
        self.total_pages = total_pages

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TimeTextMultiModal(self.user_id, self.days, self.page, self.total_pages))

class StreamTimeInputPage(discord.ui.View):
    def __init__(self, user_id, page=1, total_pages=None):
        super().__init__(timeout=300)
        selected_days = [d for d, v in user_state[user_id]["days"].items() if v in ("Eventuell", "Stream")]
        days_per_page = 3
        start_idx = (page-1)*days_per_page
        end_idx = start_idx+days_per_page
        days = selected_days[start_idx:end_idx]
        if total_pages is None:
            total_pages = (len(selected_days) + days_per_page - 1) // days_per_page
        if days:
            self.add_item(TimeInputMultiButton(user_id, days, page, total_pages))
        if start_idx > 0:
            self.add_item(NavButton("⬅️ Zurück", lambda uid: StreamTimeInputPage(uid, page-1, total_pages)))
        if end_idx < len(selected_days):
            self.add_item(NavButton("➡️ Weiter", lambda uid: StreamTimeInputPage(uid, page+1, total_pages)))
        elif selected_days:
            self.add_item(GameInputButton())

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
            if user_state[user_id]["days"].get(day, "Kein Stream") != "Kein Stream":
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

class GameInputButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(GameInputButton())

# ---- Embed-Plan senden ----
async def send_plan_embed(interaction: discord.Interaction):
    data = user_state[interaction.user.id]
    week = data["week"]
    days_selection = data["days"]
    times = data.get("times", {})
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
        selection = days_selection.get(day, "Kein Stream")
        time = times.get(day, "-")
        game = games.get(day, "-")
        emoji = "⚪"
        if selection == "Kein Stream":
            emoji = "🟥"
            line = f"{emoji} **{day}** — Kein Stream    🎮 -"
        elif selection == "Eventuell":
            emoji = "🟨"
            line = f"{emoji} **{day}** — Eventueller Stream um **{time if time != '-' else '?'}** 🎮 {game or '-'}"
        elif selection == "Stream":
            emoji = "🟩"
            line = f"{emoji} **{day}** — Stream um **{time if time != '-' else '?'}** 🎮 {game or '-'}"
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

# ---- Slash-Commands ----

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
