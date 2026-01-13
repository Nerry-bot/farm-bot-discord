import discord
from discord.ext import commands
import json
import time
import random
import difflib
import os

# ================= CONFIG =================
FARM_LIMIT = 3
FARM_RESET_TIME = 3 * 60 * 60
XP_PER_FARM = (5, 10)
LEVEL_XP = 20
ATTACK_COOLDOWN = 10

LOOT_COMMON = ["Peau", "Griffe", "Potion"]
LOOT_RARE = ["Épée légendaire", "Anneau magique"]
COMMON_CHANCE = 0.25
RARE_CHANCE = 0.05

MONSTRES = [
    {"name": "Gobelin", "hp": 20, "max_hp": 20, "weakness": "feu", "color": 0x2ecc71},
    {"name": "Loup", "hp": 30, "max_hp": 30, "weakness": "terre", "color": 0x95a5a6},
    {"name": "Orc", "hp": 40, "max_hp": 40, "weakness": "eau", "color": 0xe74c3c}
]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_MESSAGE_ID = None

# ================= UTILS =================
def hp_bar(current, maximum, size=10):
    filled = int((current / maximum) * size)
    return "🟩" * filled + "⬛" * (size - filled)

def find_character(characters, name, user_id):
    owned = {k: v for k, v in characters.items() if v["owner"] == str(user_id)}
    if name in owned:
        return name
    matches = difflib.get_close_matches(name, owned.keys(), n=1, cutoff=0.5)
    return matches[0] if matches else None

async def load_characters_from_message(guild):
    global DATA_MESSAGE_ID
    channel = discord.utils.get(guild.text_channels, name="fiches-personnages")
    if not channel:
        return {}, None

    if DATA_MESSAGE_ID:
        try:
            msg = await channel.fetch_message(DATA_MESSAGE_ID)
            return json.loads(msg.content), msg
        except:
            pass

    msg = await channel.send(json.dumps({}, indent=2))
    DATA_MESSAGE_ID = msg.id
    return {}, msg

# ================= EVENTS =================
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# ================= COMMANDES =================
@bot.command()
async def addpersonnage(ctx, nom: str, *, infos: str = ""):
    characters, msg = await load_characters_from_message(ctx.guild)
    if nom in characters:
        await ctx.send("❌ Ce personnage existe déjà.")
        return

    perso = {
        "owner": str(ctx.author.id),
        "niveau": 1,
        "xp": 0,
        "rank": "F",
        "attaques": {},
        "inventaire": [],
        "farm_uses": 0,
        "last_farm_reset": 0,
        "current_monster": None,
        "rang_en_attente": None,
        "last_attack": 0
    }

    for pair in infos.split():
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k.startswith("attaque"):
                perso["attaques"][k] = v
            else:
                perso[k] = v

    characters[nom] = perso
    await msg.edit(content=json.dumps(characters, indent=2))
    await ctx.send(f"✅ `{nom}` créé avec succès.")

@bot.command()
async def farm(ctx, *, nom: str = None):
    characters, msg = await load_characters_from_message(ctx.guild)
    if not nom:
        owned = [k for k,v in characters.items() if v["owner"] == str(ctx.author.id)]
        await ctx.send("⚔️ Tes personnages :\n" + "\n".join(owned))
        return

    key = find_character(characters, nom, ctx.author.id)
    if not key:
        await ctx.send("❌ Personnage introuvable.")
        return

    char = characters[key]
    now = int(time.time())

    if now - char["last_farm_reset"] >= FARM_RESET_TIME:
        char["farm_uses"] = 0
        char["last_farm_reset"] = now

    if char["farm_uses"] >= FARM_LIMIT:
        await ctx.send("⏳ Plus de farms disponibles.")
        return

    char["farm_uses"] += 1
    monster = random.choice(MONSTRES).copy()
    char["current_monster"] = monster

    await msg.edit(content=json.dumps(characters, indent=2))

    embed = discord.Embed(
        title="🌲 Expédition",
        description=f"**{key}** rencontre un **{monster['name']}**",
        color=monster["color"]
    )
    embed.add_field(name="HP", value=hp_bar(monster["hp"], monster["max_hp"]))
    await ctx.send(embed=embed)

@bot.command()
async def attack(ctx, nom: str, attaque: str):
    characters, msg = await load_characters_from_message(ctx.guild)
    key = find_character(characters, nom, ctx.author.id)
    if not key:
        await ctx.send("❌ Personnage introuvable.")
        return

    char = characters[key]
    monster = char["current_monster"]
    if not monster:
        await ctx.send("❌ Aucun monstre.")
        return

    now = time.time()
    if now - char["last_attack"] < ATTACK_COOLDOWN:
        await ctx.send("⏳ Attaque en cooldown.")
        return

    if attaque not in char["attaques"]:
        await ctx.send("❌ Attaque inconnue.")
        return

    char["last_attack"] = now
    dmg = random.randint(4, 8)
    crit = random.random() < 0.1
    if crit:
        dmg *= 2

    monster["hp"] -= dmg
    monster["hp"] = max(0, monster["hp"])

    embed = discord.Embed(
        title=f"⚔️ {key} attaque !",
        description=f"{char['attaques'][attaque]} → **{dmg} dégâts**",
        color=monster["color"]
    )

    embed.add_field(
        name=monster["name"],
        value=hp_bar(monster["hp"], monster["max_hp"]),
        inline=False
    )

    if monster["hp"] == 0:
        xp = random.randint(*XP_PER_FARM)
        char["xp"] += xp
        loot_msg = ""

        if random.random() < COMMON_CHANCE:
            item = random.choice(LOOT_COMMON)
            char["inventaire"].append(item)
            loot_msg += f"\n🎁 {item}"

        if random.random() < RARE_CHANCE:
            item = random.choice(LOOT_RARE)
            char["inventaire"].append(item)
            loot_msg += f"\n✨ {item}"

        char["current_monster"] = None
        embed.add_field(
            name="🏆 Victoire",
            value=f"+{xp} XP{loot_msg}",
            inline=False
        )

        while char["xp"] >= char["niveau"] * LEVEL_XP:
            char["xp"] -= char["niveau"] * LEVEL_XP
            char["niveau"] += 1
            embed.add_field(
                name="🎉 Niveau gagné",
                value=f"Niveau {char['niveau']}",
                inline=False
            )

    await msg.edit(content=json.dumps(characters, indent=2))
    await ctx.send(embed=embed)

@bot.command()
async def fiche(ctx, nom: str):
    characters, _ = await load_characters_from_message(ctx.guild)
    key = find_character(characters, nom, ctx.author.id)
    if not key:
        await ctx.send("❌ Personnage introuvable.")
        return

    c = characters[key]
    embed = discord.Embed(title=f"🧙 {key}", color=0x3498db)
    embed.add_field(name="🎖️ Rang", value=c["rank"])
    embed.add_field(name="📈 Niveau", value=c["niveau"])
    embed.add_field(name="✨ XP", value=c["xp"])
    embed.add_field(
        name="⚔️ Attaques",
        value="\n".join(c["attaques"].values()) or "Aucune",
        inline=False
    )
    embed.add_field(
        name="🎒 Inventaire",
        value=", ".join(c["inventaire"]) or "Vide",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command()
async def menu(ctx):
    embed = discord.Embed(title="📜 Menu FarmBot", color=0xf1c40f)
    embed.add_field(name="🧙 Personnage", value="!addpersonnage <nom> attaque1=... attaque2=...")
    embed.add_field(name="🌲 Farm", value="!farm <nom>")
    embed.add_field(name="⚔️ Combat", value="!attack <nom> <attaque>")
    embed.add_field(name="📖 Fiche", value="!fiche <nom>")
    await ctx.send(embed=embed)

# ================= LANCEMENT =================
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
