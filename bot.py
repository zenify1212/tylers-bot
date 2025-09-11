import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

# Database setup
conn = sqlite3.connect('tickets.db')
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS config (
    guild_id INTEGER PRIMARY KEY,
    category_id INTEGER,
    staff_roles TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS panels (
    panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    panel_name TEXT,
    options TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS stats (
    guild_id INTEGER PRIMARY KEY,
    total_tickets INTEGER DEFAULT 0
)''')

conn.commit()

class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.synced = False

    async def setup_hook(self):
        if not self.synced:
            await self.tree.sync()
            self.synced = True

bot = TicketBot()

@bot.tree.command(name="setup", description="Configure the ticket system")
@app_commands.describe(category="Ticket category", staff_roles="Staff roles (mention multiple)")
async def setup(interaction: discord.Interaction, category: discord.CategoryChannel, staff_roles: str):
    roles = [r.id for r in interaction.guild.roles if r.mention in staff_roles.split()]
    cursor.execute("REPLACE INTO config (guild_id, category_id, staff_roles) VALUES (?, ?, ?)",
                   (interaction.guild.id, category.id, ','.join(map(str, roles))))
    conn.commit()
    await interaction.response.send_message("Setup completed.", ephemeral=True)

class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Close Ticket", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.channel.delete(reason="Ticket closed")

class TicketView(discord.ui.View):
    def __init__(self, options, panel_id):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        for label in options:
            self.add_item(TicketButton(label=label, panel_id=panel_id))

class TicketButton(discord.ui.Button):
    def __init__(self, label, panel_id):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.panel_id = panel_id

    async def callback(self, interaction: discord.Interaction):
        cursor.execute("SELECT category_id, staff_roles FROM config WHERE guild_id=?", (interaction.guild.id,))
        row = cursor.fetchone()
        if not row:
            await interaction.response.send_message("Bot is not configured. Use /setup.", ephemeral=True)
            return

        category_id, staff_roles = row
        category = interaction.guild.get_channel(category_id)
        staff_roles = [interaction.guild.get_role(int(r)) for r in staff_roles.split(',')]

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await category.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)

        embed = discord.Embed(
            title="Ticket Opened",
            description=f"{interaction.user.mention}, thank you for opening a ticket!\n\nA staff member will be with you shortly.",
            colour=discord.Colour.dark_grey()
        )
        embed.set_footer(text=f"{interaction.guild.name} • Support")

        view = discord.ui.View()
        view.add_item(CloseButton())

        await channel.send(embed=embed, view=view)

        cursor.execute("INSERT INTO stats (guild_id, total_tickets) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET total_tickets = total_tickets + 1", (interaction.guild.id,))
        conn.commit()

        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)


@bot.tree.command(name="panel", description="Create a ticket panel")
@app_commands.describe(name="Name of the panel", options="Up to 10 button labels, separated by commas")
async def panel(interaction: discord.Interaction, name: str, options: str):
    opts = [o.strip() for o in options.split(",") if o.strip()]
    if len(opts) == 0 or len(opts) > 10:
        await interaction.response.send_message("You must provide between 1 and 10 options.", ephemeral=True)
        return

    cursor.execute("INSERT INTO panels (guild_id, panel_name, options) VALUES (?, ?, ?)",
                   (interaction.guild.id, name, ','.join(opts)))
    conn.commit()
    panel_id = cursor.lastrowid

    embed = discord.Embed(
        title=f"{name}",
        description="Click a button below to open a ticket.",
        colour=discord.Colour.dark_grey()
    )
    embed.set_footer(text=f"Ticket Panel • {interaction.guild.name}")

    view = TicketView(opts, panel_id)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Panel created.", ephemeral=True)


@bot.tree.command(name="close", description="Close the current ticket")
async def close(interaction: discord.Interaction):
    if interaction.channel and interaction.channel.name.startswith("ticket-"):
        await interaction.channel.delete(reason="Closed via command")
        await interaction.response.send_message("Ticket closed.", ephemeral=True)
    else:
        await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)


@bot.tree.command(name="stats", description="Show ticket statistics")
async def stats(interaction: discord.Interaction):
    cursor.execute("SELECT total_tickets FROM stats WHERE guild_id=?", (interaction.guild.id,))
    row = cursor.fetchone()
    total = row[0] if row else 0

    embed = discord.Embed(
        title="Ticket Statistics",
        description=f"Total tickets created: **{total}**",
        colour=discord.Colour.dark_grey()
    )
    embed.set_footer(text=f"{interaction.guild.name} • Stats")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="status", description="Get bot latency")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong: {round(bot.latency * 1000)}ms", ephemeral=True)


@bot.event
async def on_ready():
    cursor.execute("SELECT panel_id, options FROM panels")
    for panel_id, options in cursor.fetchall():
        opts = options.split(',')
        bot.add_view(TicketView(opts, panel_id))
    print(f"Logged in as {bot.user}")

bot.run("MTQxNTY4OTQzMzAwODcwNTYxNg.GEdorW.LCE2GoK2XB4aSPEuQIBBbNroIZpD9tVj0mHI1w")