import discord
import os
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import re

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Nutze Umgebungsvariable oder Platzhalter
TOKEN = os.getenv("DISCORD_TOKEN", "")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))

DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

def get_week_options():
    """Dynamisch: aktuelle Woche und die zwei folgenden Wochen"""
    today = datetime.today()
    # Wochenstart: Montag dieser Woche
    start = today - timedelta(days=today.weekday())
    week_options = []
    for i in range(3):
        w_start = start + timedelta(days=7*i)
        w_end = w_start + timedelta(days=6)
        label = f"{w_start.strftime('%d.%m.%Y')} - {w_end.strftime('%d.%m.%Y')}"
        week_options.append(label)
    return week_options

# Userdaten speichern
user_state = {}

# Woche auswählen
class WeekSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=label, value=label) for label in get_week_options()]
        super().__init__(placeholder="Wähle die Woche (vom/bis)", options=options)

    async def callback(self, interaction: discord.Interaction):
        user_state[interaction.user.id] = {
            "week": self.values[0],
            "times": {},
            "games": {}
        }
        await interaction.response.edit_message(
            content="Bitte gib für jeden Tag die Uhrzeit ein (z. B. 18:00), 'Kein Stream' oder 'Eventuell':",
            view=TimeInputModalView(interaction.user.id)
        )

class WeekView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(WeekSelect())

# Zeit-Eingabe als Modal
class TimeInputModal(discord.ui.Modal, title="Streamzeiten eintragen"):
    def __init__(self, user_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.inputs = []
        for day in DAYS:
            text_input = discord.ui.TextInput(
                label=day,
                placeholder="z. B. 18:00, Kein Stream, Eventuell",
                required=False
            )
            self.inputs.append(text_input)
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Uhrzeiten prüfen
        errors = []
        for i, day in enumerate(DAYS):
            val = self.inputs[i].value.strip()
            # Erlaubt: HH:MM, Kein Stream, Eventuell (alles Case-Insensitiv)
            if val == "":
                val = "Kein Stream"
            if not (re.match(r"^\d{1,2}:\d{2}$", val) or val.lower() in ["kein stream", "eventuell"]):
                errors.append(f"{day}: '{val}' ungültig")
            user_state[self.user_id]["times"][day] = val.capitalize()

        if errors:
            await interaction.response.send_message(
                f"Bitte korrigiere folgende Eingaben:\n" + "\n".join(errors) + "\nErlaubt: HH:MM, Kein Stream, Eventuell.",
                ephemeral=True
            )
            return
        # Weiter zur Spiel-Eingabe
        await interaction.response.send_modal(GameInputModal(self.user_id))

class TimeInputModalView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=600)
        self.user_id = user_id

    @discord.ui.button(label="Weiter zur Zeiteingabe", style=discord.ButtonStyle.primary)
    async def open_time_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeInputModal(self.user_id))

# Spielname als Modal
class GameInputModal(discord.ui.Modal, title="Spiele eintragen"):
    def __init__(self, user_id):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.inputs = []
        for day in DAYS:
            val = user_state[user_id]["times"][day]
            if val.lower() in ["kein stream", "eventuell"]:
                continue  # Kein Spiel nötig
            game_input = discord.ui.TextInput(
                label=f"{day} ({val}) – Spielname",
                placeholder="z. B. Fortnite",
                required=False
            )
            self.inputs.append((day, game_input))
            self.add_item(game_input)

    async def on_submit(self, interaction: discord.Interaction):
        for day, field in self.inputs:
            user_state[self.user_id]["games"][day] = field.value or "?"
        await send_plan_embed(interaction)

# Emoji-Liste wie vorher
game_emojis = {
    "fortnite": "🔫", "call of duty": "🔫", "cod": "🔫", "minecraft": "⛏️", "gta": "🚗",
    "fifa": "⚽", "horror": "🧟", "just chatting": "💬", "league of legends": "🧙", "lol": "🧙",
    "valorant": "🎯", "apex": "🪂", "rocket league": "🚀", "tft": "♟️", "elden ring": "🗡️",
    "csgo": "🔫", "cs2": "🔫", "hogwarts legacy": "🧙‍♂️", "the sims": "🏠", "farming simulator": "🌾"
}

# Embed senden wie gehabt
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
        # Emoji zur Uhrzeit
        if time.lower() == "kein stream":
            emoji = "🟥"
            game_icon = "🎮"
            line = f"{emoji} **{day}** — Kein Stream    {game_icon} -"
        elif time.lower() == "eventuell":
            emoji = "🟨"
            game_icon = "🎮"
            line = f"{emoji} **{day}** — Eventuell      {game_icon} -"
        else:
            emoji = "🟩"
            # Spiel-Emoji automatisch ergänzen
            game_icon = "🎮"
            if game != "-":
                g = game.lower()
                for key, icon in game_emojis.items():
                    if key in g:
                        game_icon += f" {icon}"
                        break
            line = f"{emoji} **{day}** — {time.ljust(10)} {game_icon} **{game}**"
        lines.append(line)
        lines.append("")  # Leerzeile

    embed.description = "\n".join(lines)

    channel = bot.get_channel(TARGET_CHANNEL_ID)
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Dein Streamplan wurde gepostet!", ephemeral=True)

# Command
@tree.command(name="streamplan", description="Erstelle deinen wöchentlichen Streamplan")
async def streamplan(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Nur der Streamer kann diesen Befehl nutzen.", ephemeral=True)
        return
    await interaction.response.send_message("📅 Wähle die Woche:", view=WeekView(), ephemeral=True)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"🤖 Bot bereit: {bot.user}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    bot.run(TOKEN)

