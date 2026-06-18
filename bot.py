import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import random
import os
from datetime import datetime

TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])

DB_FILE             = "champions.db"
ASSIGNMENTS_CHANNEL = "battle-assignments"
RESULTS_CHANNEL     = "battle-results"
LEADERBOARD_CHANNEL = "leaderboard"

TIERS = [
    (0,    999,  "Pokeball 1",       "Pokeball 1"),
    (1000, 1099, "Pokeball 2",       "Pokeball 2"),
    (1100, 1199, "Pokeball 3",       "Pokeball 3"),
    (1200, 1299, "Greatball 4",      "Greatball 4"),
    (1300, 1399, "Greatball 3",      "Greatball 3"),
    (1400, 1499, "Greatball 2",      "Greatball 2"),
    (1500, 1599, "Greatball 1",      "Greatball 1"),
    (1600, 1699, "Ultraball 4",      "Ultraball 4"),
    (1700, 1799, "Ultraball 3",      "Ultraball 3"),
    (1800, 1899, "Ultraball 2",      "Ultraball 2"),
    (1900, 1999, "Ultraball 1",      "Ultraball 1"),
    (2000, 2099, "Masterball 4",     "Masterball 4"),
    (2100, 2199, "Masterball 3",     "Masterball 3"),
    (2200, 2299, "Masterball 2",     "Masterball 2"),
    (2300, 2399, "Masterball 1",     "Masterball 1"),
    (2400, 9999, "Champions League", "Champions League"),
]

STARTING_ELO = {
    "Pokeball 1": 500,    "Pokeball 2": 1050,   "Pokeball 3": 1150,
    "Greatball 4": 1250,  "Greatball 3": 1350,  "Greatball 2": 1450, "Greatball 1": 1550,
    "Ultraball 4": 1650,  "Ultraball 3": 1750,  "Ultraball 2": 1850, "Ultraball 1": 1950,
    "Masterball 4": 2050, "Masterball 3": 2150, "Masterball 2": 2250,"Masterball 1": 2350,
    "Champions League": 2500,
}

def get_tier(elo):
    for lo, hi, name, _ in TIERS:
        if lo <= elo <= hi:
            return name
    return "Champions League"

def calc_elo(winner_elo, loser_elo, k=32):
    expected   = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    new_winner = round(winner_elo + k * (1 - expected))
    new_loser  = round(loser_elo  + k * (0 - (1 - expected)))
    return new_winner, new_loser

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
guild_obj = discord.Object(id=GUILD_ID)

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS players (
            discord_id TEXT PRIMARY KEY, username TEXT NOT NULL,
            switch_code TEXT, poke_username TEXT,
            elo INTEGER DEFAULT 1000, wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0, registered_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_id TEXT NOT NULL, player2_id TEXT NOT NULL,
            winner_id TEXT, scheduled_at TEXT, completed_at TEXT)""")
        await db.commit()

async def get_player(discord_id):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)) as c:
            return await c.fetchone()

async def get_all_players():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players ORDER BY elo DESC") as c:
            return await c.fetchall()

async def get_channel(guild, name):
    return discord.utils.get(guild.channels, name=name)

async def update_member_role(member, new_tier):
    tier_names = {t[2] for t in TIERS}
    to_remove  = [r for r in member.roles if r.name in tier_names]
    new_role   = discord.utils.get(member.guild.roles, name=new_tier)
    try:
        if to_remove: await member.remove_roles(*to_remove, reason="Rank update")
        if new_role:  await member.add_roles(new_role, reason="Rank update")
    except discord.Forbidden:
        pass

def build_leaderboard(players):
    embed = discord.Embed(title="Pokemon Champions Leaderboard", color=discord.Color.gold(), timestamp=datetime.utcnow())
    if not players:
        embed.description = "No players yet."
        return embed
    medals = ["Gold", "Silver", "Bronze"]
    lines  = []
    for i, p in enumerate(players[:20]):
        icon   = medals[i] if i < 3 else f"#{i+1}"
        record = f"{p['wins']}W-{p['losses']}L"
        lines.append(f"{icon} **{p['username']}** - {get_tier(p['elo'])} - {p['elo']} ELO - {record}")
    embed.description = "\n".join(lines)
    embed.set_footer(text="Updates after every match")
    return embed

async def refresh_leaderboard(guild):
    ch = await get_channel(guild, LEADERBOARD_CHANNEL)
    if not ch: return
    players = await get_all_players()
    embed   = build_leaderboard(players)
    async for msg in ch.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            await msg.edit(embed=embed); return
    await ch.send(embed=embed)

@bot.event
async def on_ready():
    await init_db()
    try:
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"Bot online - {len(synced)} commands synced")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.tree.command(guild=guild_obj, name="register", description="Register yourself for Pokemon Champions")
@app_commands.describe(poke_username="Your in-game Pokemon Champions username", switch_code="Your Switch friend code (SW-XXXX-XXXX-XXXX)", starting_rank="Your current rank")
@app_commands.choices(starting_rank=[
    app_commands.Choice(name="Pokeball 1",      value="Pokeball 1"),
    app_commands.Choice(name="Pokeball 2",      value="Pokeball 2"),
    app_commands.Choice(name="Pokeball 3",      value="Pokeball 3"),
    app_commands.Choice(name="Greatball 4",     value="Greatball 4"),
    app_commands.Choice(name="Greatball 3",     value="Greatball 3"),
    app_commands.Choice(name="Greatball 2",     value="Greatball 2"),
    app_commands.Choice(name="Greatball 1",     value="Greatball 1"),
    app_commands.Choice(name="Ultraball 4",     value="Ultraball 4"),
    app_commands.Choice(name="Ultraball 3",     value="Ultraball 3"),
    app_commands.Choice(name="Ultraball 2",     value="Ultraball 2"),
    app_commands.Choice(name="Ultraball 1",     value="Ultraball 1"),
    app_commands.Choice(name="Masterball 4",    value="Masterball 4"),
    app_commands.Choice(name="Masterball 3",    value="Masterball 3"),
    app_commands.Choice(name="Masterball 2",    value="Masterball 2"),
    app_commands.Choice(name="Masterball 1",    value="Masterball 1"),
    app_commands.Choice(name="Champions League",value="Champions League"),
])
async def cmd_register(interaction, poke_username: str, switch_code: str, starting_rank: app_commands.Choice[str]):
    existing = await get_player(str(interaction.user.id))
    if existing:
        await interaction.response.send_message(f"Already registered with {existing['elo']} ELO.", ephemeral=True); return
    elo = STARTING_ELO.get(starting_rank.value, 1000)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO players (discord_id,username,switch_code,poke_username,elo,registered_at) VALUES (?,?,?,?,?,?)",
            (str(interaction.user.id), interaction.user.display_name, switch_code, poke_username, elo, datetime.utcnow().isoformat()))
        await db.commit()
    await update_member_role(interaction.user, starting_rank.value)
    embed = discord.Embed(title="Registration Complete!", color=discord.Color.green())
    embed.add_field(name="In-Game Name", value=poke_username, inline=True)
    embed.add_field(name="Switch Code",  value=switch_code,   inline=True)
    embed.add_field(name="Rank",         value=starting_rank.value, inline=True)
    embed.add_field(name="Starting ELO", value=str(elo), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(guild=guild_obj, name="rank", description="Check your rank and ELO")
@app_commands.describe(player="Player to look up (leave blank for yourself)")
async def cmd_rank(interaction, player: discord.Member = None):
    target = player or interaction.user
    data   = await get_player(str(target.id))
    if not data:
        await interaction.response.send_message("Not registered. Use /register!", ephemeral=True); return
    total   = data["wins"] + data["losses"]
    winrate = f"{round(data['wins']/total*100)}%" if total else "N/A"
    embed   = discord.Embed(title=f"Stats for {data['username']}", color=discord.Color.blue())
    embed.add_field(name="Rank",   value=get_tier(data["elo"]), inline=True)
    embed.add_field(name="ELO",    value=str(data["elo"]),      inline=True)
    embed.add_field(name="Record", value=f"{data['wins']}W-{data['losses']}L ({winrate})", inline=True)
    embed.add_field(name="Switch Code",  value=data["switch_code"]   or "N/A", inline=True)
    embed.add_field(name="In-Game Name", value=data["poke_username"] or "N/A", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(guild=guild_obj, name="schedule", description="[Admin] Schedule random matches for all players")
@app_commands.checks.has_permissions(administrator=True)
async def cmd_schedule(interaction):
    await interaction.response.defer()
    players = await get_all_players()
    if len(players) < 2:
        await interaction.followup.send("Need at least 2 players registered."); return
    pool = list(players); random.shuffle(pool)
    pairs = []
    while len(pool) >= 2: pairs.append((pool.pop(), pool.pop()))
    bye = pool[0] if pool else None
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        for p1, p2 in pairs:
            await db.execute("INSERT INTO matches (player1_id,player2_id,scheduled_at) VALUES (?,?,?)", (p1["discord_id"], p2["discord_id"], now))
        await db.commit()
    ch = await get_channel(interaction.guild, ASSIGNMENTS_CHANNEL)
    if not ch:
        await interaction.followup.send("Cannot find #battle-assignments."); return
    embed = discord.Embed(title=f"Match Schedule - {datetime.utcnow().strftime('%B %d, %Y')}",
        description=f"**{len(pairs)} matches** - good luck!", color=discord.Color.red(), timestamp=datetime.utcnow())
    for i,(p1,p2) in enumerate(pairs,1):
        embed.add_field(name=f"Match {i}",
            value=f"<@{p1['discord_id']}> ({get_tier(p1['elo'])} - {p1['elo']} ELO)\nvs\n<@{p2['discord_id']}> ({get_tier(p2['elo'])} - {p2['elo']} ELO)",
            inline=True)
    if bye: embed.set_footer(text=f"{bye['username']} has a BYE this round")
    await ch.send(embed=embed)
    await interaction.followup.send(f"Done! {len(pairs)} matches posted to {ch.mention}")

@bot.tree.command(guild=guild_obj, name="result", description="[Admin] Record a match result and update ELO")
@app_commands.describe(winner="The player who won", loser="The player who lost")
@app_commands.checks.has_permissions(administrator=True)
async def cmd_result(interaction, winner: discord.Member, loser: discord.Member):
    await interaction.response.defer()
    w = await get_player(str(winner.id)); l = await get_player(str(loser.id))
    if not w or not l:
        await interaction.followup.send("One or both players are not registered."); return
    new_w, new_l = calc_elo(w["elo"], l["elo"])
    old_wt, old_lt, new_wt, new_lt = get_tier(w["elo"]), get_tier(l["elo"]), get_tier(new_w), get_tier(new_l)
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE players SET elo=?,wins=wins+1 WHERE discord_id=?", (new_w, str(winner.id)))
        await db.execute("UPDATE players SET elo=?,losses=losses+1 WHERE discord_id=?", (new_l, str(loser.id)))
        await db.execute("UPDATE matches SET winner_id=?,completed_at=? WHERE completed_at IS NULL AND ((player1_id=? AND player2_id=?) OR (player1_id=? AND player2_id=?))",
            (str(winner.id), now, str(winner.id), str(loser.id), str(loser.id), str(winner.id)))
        await db.commit()
    await update_member_role(winner, new_wt); await update_member_role(loser, new_lt)
    embed = discord.Embed(title="Match Result", color=discord.Color.gold(), timestamp=datetime.utcnow())
    embed.add_field(name=f"Winner - {winner.display_name}", value=f"ELO: {w['elo']} to **{new_w}** (+{new_w-w['elo']})\n{'Ranked up: '+old_wt+' to '+new_wt if new_wt!=old_wt else 'Stayed in '+new_wt}", inline=True)
    embed.add_field(name=f"Loser - {loser.display_name}",  value=f"ELO: {l['elo']} to **{new_l}** ({new_l-l['elo']})\n{'Ranked down: '+old_lt+' to '+new_lt if new_lt!=old_lt else 'Stayed in '+new_lt}", inline=True)
    rch = await get_channel(interaction.guild, RESULTS_CHANNEL)
    if rch: await rch.send(embed=embed)
    await refresh_leaderboard(interaction.guild)
    await interaction.followup.send("Result recorded!")

@bot.tree.command(guild=guild_obj, name="leaderboard", description="Show the leaderboard")
async def cmd_leaderboard(interaction):
    await interaction.response.send_message(embed=build_leaderboard(await get_all_players()))

@bot.tree.command(guild=guild_obj, name="players", description="List all registered players")
async def cmd_players(interaction):
    players = await get_all_players()
    if not players:
        await interaction.response.send_message("No players registered yet.", ephemeral=True); return
    embed = discord.Embed(title=f"Registered Players ({len(players)})", color=discord.Color.blue())
    embed.description = "\n".join([f"- **{p['username']}** - {get_tier(p['elo'])} ({p['elo']} ELO)" for p in players[:25]])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(guild=guild_obj, name="unregister", description="[Admin] Remove a player")
@app_commands.describe(player="Player to remove")
@app_commands.checks.has_permissions(administrator=True)
async def cmd_unregister(interaction, player: discord.Member):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM players WHERE discord_id=?", (str(player.id),))
        await db.commit()
    await interaction.response.send_message(f"{player.display_name} removed.")

@cmd_schedule.error
@cmd_result.error
@cmd_unregister.error
async def admin_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need Administrator permissions.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Error: {error}", ephemeral=True)

bot.run(TOKEN)
