from typing import List, Tuple, Optional
import asyncio
import aiohttp
import json
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from modules.decorators import auto_register_user
from modules.postgres_database import get_database
from modules.battle import RARITY_STATS, RARITY_MOVES


# Local type emoji map tailored to your requested emojis
TYPE_EMOJIS = {
    "Normal": "⚪",
    "Fire": "🔥",
    "Water": "💧",
    "Electric": "⚡",
    "Grass": "🌱",
    "Ice": "❄️",
    "Fighting": "🥊",
    "Poison": "☠️",
    "Ground": "⛰",
    "Flying": "🦅",
    "Psychic": "🔮",
    "Bug": "🐛",
    "Rock": "🪨",
    "Ghost": "👻",
    "Dragon": "🐉",
    "Dark": "🌑",
    "Steel": "🔩",  # requested
    "Fairy": "🧚",
}



_MOVE_CACHE: dict[str, List[dict]] = {}
_STATS_CACHE: dict[str, dict] = {}

# Load Necrozma forms data once
NECROZMA_FORMS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "necrozma_forms.json")
_NECROZMA_DATA: Optional[dict] = None

def _load_necrozma_data() -> dict:
    global _NECROZMA_DATA
    if _NECROZMA_DATA is None:
        try:
            with open(NECROZMA_FORMS_PATH, "r", encoding="utf-8") as f:
                _NECROZMA_DATA = json.load(f)
        except Exception:
            _NECROZMA_DATA = {}
    return _NECROZMA_DATA

def _get_necrozma_form_data(name: str) -> Optional[dict]:
    data = _load_necrozma_data()
    key = normalize_name(name)
    # Accept both exact keys and flexible matching
    candidates = {
        "necrozma dusk mane": "Necrozma Dusk Mane",
        "necrozma dawn wings": "Necrozma Dawn Wings",
    }
    canonical = candidates.get(key)
    if canonical and canonical in data:
        return data.get(canonical)
    # Fallback: try direct access if the provided name matches the keys exactly
    return data.get(name)


def parse_types(type_field: str) -> List[str]:
    if not type_field:
        return []
    raw = type_field.replace("|", "/").replace(",", "/")
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    # Deduplicate while preserving order
    seen = set()
    result = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def format_types_with_emojis(type_field: str) -> str:
    types = parse_types(type_field)
    if not types:
        return "[Unknown]"
    pretty: List[str] = []
    for t in types:
        emoji = TYPE_EMOJIS.get(t, "⚪")
        pretty.append(f"{t} {emoji}")
    return "[" + " / ".join(pretty) + "]"


def build_poke_keyboard(owner_user_id: int, char_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Stats", callback_data=f"poke_stats_{owner_user_id}_{char_id}"),
                InlineKeyboardButton("🎯 Moveset", callback_data=f"poke_moves_{owner_user_id}_{char_id}"),
            ]
        ]
    )


def build_moves_only_keyboard(owner_user_id: int, char_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ℹ️ Info", callback_data=f"poke_info_{owner_user_id}_{char_id}"),
            ]
        ]
    )


def build_stats_only_keyboard(owner_user_id: int, char_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ℹ️ Info", callback_data=f"poke_info_{owner_user_id}_{char_id}"),
            ]
        ]
    )


async def _get_user_and_character(user_id: int, char_id: int):
    db = get_database()
    user = await db.get_user(user_id)
    character = await db.get_character(char_id)
    return user, character


def _user_owns_character(user: dict, char_id: int) -> bool:
    chars = (user or {}).get("characters") or []
    try:
        return int(char_id) in set(chars)
    except Exception:
        return False


async def _base_caption(character: dict, rank_stars: int = 1) -> str:
    name = character.get("name", "Unknown")
    type_field = character.get("type") or ""

    # Determine types: prefer DB, else Necrozma JSON, else PokeAPI
    necrozma_data = _get_necrozma_form_data(name) if name else None
    if type_field:
        types_pretty = format_types_with_emojis(type_field)
    elif necrozma_data and necrozma_data.get("types"):
        json_types = necrozma_data.get("types") or []
        pretty_parts: List[str] = []
        for t in json_types:
            emoji = TYPE_EMOJIS.get(t, "⚪")
            pretty_parts.append(f"{t} {emoji}")
        types_pretty = "[" + " / ".join(pretty_parts) + "]" if pretty_parts else "[Unknown]"
    else:
        types_pretty = "[Unknown]"
        if name:
            data = await fetch_pokeapi_stats(name)
            if data and data.get("types"):
                pretty_parts: List[str] = []
                for t in data.get("types", []):
                    emoji = TYPE_EMOJIS.get(t, "⚪")
                    pretty_parts.append(f"{t} {emoji}")
                if pretty_parts:
                    types_pretty = "[" + " / ".join(pretty_parts) + "]"

    # Determine region: explicit region > Necrozma=Alola > anime > Unknown
    region = character.get("anime")
    if not region and necrozma_data:
        region = "Alola"
    if not region:
        region = character.get("anime") or "Unknown"

    return (
        f"<b>{name}</b>\n"
        f"Region: <b>{region}</b>\n"
        f"Types: {types_pretty}"
    )


import aiohttp
from typing import Optional


# Mapping of display names to PokeAPI-compatible names
POKEMON_NAME_MAP = {
    "white kyurem": "kyurem-white",
    "black kyurem": "kyurem-black",
    "primal groudon": "groudon-primal",
    "primal kyogre": "kyogre-primal",
    "mega rayquaza": "rayquaza-mega",
    "zygarde 100% form": "zygarde-complete",
    "hoopa unbound": "hoopa-unbound",
    "necrozma dusk mane": "necrozma-dusk-mane",
    "necrozma dawn wings": "necrozma-dawn-wings",
    "dialga origin": "dialga",
    "palkia origin": "palkia",
    "ultra necrozma": "necrozma-ultra",
    "giratina origin": "giratina-origin",
    "zygarde core": "zygarde-10",
    "zygarde 10% form": "zygarde-10",
    "zygarde 50% form": "zygarde-50",
    "arceus (god of all pokemon)": "arceus",
    "giratina": "giratina-altered",
    "deoxys": "deoxys-attack",
    "ash greninja": "greninja-ash",
    "mega mewtwo x": "mewtwo-mega-x",
    "mega mewtwo y": "mewtwo-mega-y",
    "mega charizard x": "charizard-mega-x",
    "mega charizard y": "charizard-mega-y",
    "mega blastoise": "blastoise-mega",
    "mega beedrill": "beedrill-mega",
    "mega pidgeot": "pidgeot-mega",
    "mega alakazam": "alakazam-mega",
    "mega gengar": "gengar-mega",
    "mega gardevoir": "gardevoir-mega"
}

def normalize_name(name: str) -> str:
    """Lowercase, remove extra spaces, and normalize special characters for mapping."""
    return " ".join(name.lower().strip().replace('.', '').replace("'", '').split())



async def fetch_pokeapi_stats(pokemon_name: str) -> Optional[dict]:
    """Fetch Pokemon stats from PokeAPI with special forms handling and caching."""
    
    name_key = normalize_name(pokemon_name)
    if not name_key:
        return None

    # Force refetch if cache exists but you want fresh data
    if name_key in _STATS_CACHE:
        # Optional: remove stale entry
        _STATS_CACHE.pop(name_key)

    # Apply special forms mapping
    clean_name = POKEMON_NAME_MAP.get(name_key, name_key).replace(' ', '-')

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://pokeapi.co/api/v2/pokemon/{clean_name}") as response:
                if response.status != 200:
                    print(f"Failed to fetch {clean_name} from PokeAPI. Status: {response.status}")
                    return None

                data = await response.json()

                # Extract base stats
                base_stats = {}
                for stat in data.get('stats', []):
                    stat_name = stat['stat']['name']
                    base_value = stat['base_stat']
                    mapping = {
                        'hp': 'hp',
                        'attack': 'atk',
                        'defense': 'def',
                        'special-attack': 'spa',
                        'special-defense': 'spd',
                        'speed': 'spe'
                    }
                    if stat_name in mapping:
                        base_stats[mapping[stat_name]] = base_value

                # Ensure all stats exist
                for s in ['hp','atk','def','spa','spd','spe']:
                    base_stats.setdefault(s, 0)

                # Max-level stats
                IV = 31
                EV = 252
                LEVEL = 100
                max_level_stats = {}
                for stat_name, base in base_stats.items():
                    if stat_name == 'hp':
                        max_level_stats[stat_name] = int(((base * 2 + IV + EV // 4) * LEVEL) / 100 + LEVEL + 10)
                    else:
                        max_level_stats[stat_name] = int(((base * 2 + IV + EV // 4) * LEVEL) / 100 + 5)

                result = {
                    'base_stats': base_stats,
                    'max_level_stats': max_level_stats,
                    'types': [t['type']['name'].title() for t in data.get('types', [])],
                    'height': data.get('height', 0) / 10,  # meters
                    'weight': data.get('weight', 0) / 10,  # kg
                    'abilities': [a['ability']['name'].replace('-', ' ').title() for a in data.get('abilities', [])]
                }

                # Cache the fresh result
                _STATS_CACHE[name_key] = result
                return result

    except Exception as e:
        print(f"Error fetching PokeAPI stats for {pokemon_name}: {e}")
        return None





def calculate_max_level_stats_from_rarity(rarity: str) -> dict:
    """Calculate max level stats from rarity using battle.py system with perfect IVs/EVs"""
    base_stats = RARITY_STATS.get(rarity, RARITY_STATS["Common"])
    
    # Use the same formula as PokeAPI: base * 2 + 31 (IVs) + 63 (EVs) + 5 (level bonus)
    max_level_stats = {
    'hp': int(base_stats['hp'] * 2 + 31 + 63 + 100 + 10),  # correct HP formula
    'atk': int(base_stats['atk'] * 2 + 31 + 63 + 5),
    'def': int(base_stats['def'] * 2 + 31 + 63 + 5),
    'spe': int(base_stats['spe'] * 2 + 31 + 63 + 5),
    'spa': int(base_stats.get('spa', base_stats['spe']) * 2 + 31 + 63 + 5),
    'spd': int(base_stats.get('spd', base_stats['spe']) * 2 + 31 + 63 + 5)
}
    return max_level_stats

def format_stats_display(stats: dict, is_max_level: bool = True) -> str:
    """Format stats for display"""
    stats_text = ""
    stats_text += f"❤️ <b>HP:</b> {stats.get('hp', 0)}\n"
    stats_text += f"⚔️ <b>ATK:</b> {stats.get('atk', 0)}\n"
    stats_text += f"🛡️ <b>DEF:</b> {stats.get('def', 0)}\n"
    stats_text += f"💨 <b>SPE:</b> {stats.get('spe', 0)}\n"
    stats_text += f"🔮 <b>SPA:</b> {stats.get('spa', 0)}\n"
    stats_text += f"🌟 <b>SPD:</b> {stats.get('spd', 0)}\n"
    
    return stats_text

async def _stats_text(character: dict) -> str:
    """Get comprehensive stats text with PokeAPI integration"""
    pokemon_name = character.get('name', '')
    pokeapi_data = None
    max_level_stats = None
    
    # Try Necrozma JSON first, then PokeAPI
    if pokemon_name:
        necrozma_data = _get_necrozma_form_data(pokemon_name)
        if necrozma_data:
            pokeapi_data = necrozma_data
            max_level_stats = necrozma_data.get('max_level_stats')
        else:
            pokeapi_data = await fetch_pokeapi_stats(pokemon_name)
            if pokeapi_data:
                max_level_stats = pokeapi_data['max_level_stats']
    
    # Fallback to rarity-based stats if PokeAPI fails
    if not max_level_stats:
        max_level_stats = calculate_max_level_stats_from_rarity(character.get('rarity', 'Common'))
    
    # Format the stats display
    stats_text = format_stats_display(max_level_stats, is_max_level=True)
    
    
    return stats_text




async def _fetch_pokeapi_moves(pokemon_name: str, session: aiohttp.ClientSession) -> Optional[List[dict]]:
    """Fetch top damaging moves for a Pokémon, considering special forms and preferred damage type."""
    
    name_key = normalize_name(pokemon_name)
    if not name_key:
        return None

    # Check cache
    if name_key in _MOVE_CACHE:
        return _MOVE_CACHE[name_key]

    # Apply special forms mapping
    clean_name = POKEMON_NAME_MAP.get(name_key, name_key).replace(' ', '-').replace('.', '').replace("'", '')

    try:
        # Fetch Pokémon details
        resp = await session.get(f"https://pokeapi.co/api/v2/pokemon/{clean_name}")
        if resp.status != 200:
            return None
        data = await resp.json()

        # Extract ATK and SPA
        stats = {s["stat"]["name"]: s["base_stat"] for s in data.get("stats", [])}
        atk = stats.get("attack", 0)
        spa = stats.get("special-attack", 0)

        # Determine preferred damage class
        if abs(spa - atk) <= 10:
            preferred_class = None  # balanced
        elif spa > atk:
            preferred_class = "special"
        else:
            preferred_class = "physical"

        best: List[Tuple[str, str, int, int, float, str]] = []  # (name, type, power, acc, score, dmg_class)
        sem = asyncio.Semaphore(10)

        async def fetch_move_detail(entry):
            move_info = entry.get("move") or {}
            mname = (move_info.get("name") or "").replace("-", " ").title()
            murl = move_info.get("url")
            if not murl:
                return
            async with sem:
                r = await session.get(murl)
                if r.status != 200:
                    return
                j = await r.json()
                power = j.get("power")
                accuracy = j.get("accuracy")
                mtype = (j.get("type", {}) or {}).get("name", "Unknown").title()
                dmg_class = (j.get("damage_class", {}) or {}).get("name", "").lower()

                if isinstance(power, int) and isinstance(accuracy, int) and power > 0 and accuracy >= 80:
                    if preferred_class and dmg_class != preferred_class:
                        return
                    score = power * (accuracy / 100.0)
                    best.append((mname, mtype, power, accuracy, score, dmg_class))

        # Fetch first 100 moves concurrently
        tasks = [fetch_move_detail(e) for e in data.get("moves", [])[:500]]
        await asyncio.gather(*tasks)

        if not best:
            return None

        # Sort moves by score
        best_sorted = sorted(best, key=lambda x: x[4], reverse=True)

        # Pick top 4 unique-type moves (max 1 Normal)
        result = []
        used_types = set()
        has_normal = False

        for n, t, p, a, _, dmg_class in best_sorted:
            if t in used_types:
                continue
            if t == "Normal" and has_normal:
                continue
            result.append({"name": n, "type": t, "power": p, "accuracy": a, "class": dmg_class})
            used_types.add(t)
            if t == "Normal":
                has_normal = True
            if len(result) == 4:
                break

        _MOVE_CACHE[name_key] = result
        return result

    except Exception as e:
        print(f"Error fetching moves for {pokemon_name}: {e}")
        return None






async def _moves_text(character: dict) -> str:
    # Prefer character-specific moves from DB column `moves`
    char_moves = character.get("moves")
    parsed_moves: List[dict] = []

    # If Necrozma JSON provides moves for this form, use them immediately
    name_for_moves = character.get("name") or ""
    necrozma_data = _get_necrozma_form_data(name_for_moves) if name_for_moves else None
    if necrozma_data and isinstance(necrozma_data.get("moves"), list) and necrozma_data["moves"]:
        parsed_moves = list(necrozma_data["moves"])  # shallow copy to avoid accidental mutation

    if not parsed_moves and char_moves:
        try:
            # If stored as JSON string, parse it
            if isinstance(char_moves, str):
                import json
                try:
                    char_moves = json.loads(char_moves)
                except Exception:
                    # Not JSON, attempt to parse free-form string e.g.
                    # "Thunderbolt (Power: 90, Acc: 100%), Wild Charge (Power: 90, Acc: 100%)"
                    def infer_type_from_name(name: str) -> str:
                        n = name.lower()
                        if any(k in n for k in ["thunder", "volt", "charge", "bolt", "zap"]):
                            return "Electric"
                        if any(k in n for k in ["flame", "fire", "burn", "v-create", "blaze"]):
                            return "Fire"
                        if any(k in n for k in ["water", "hydro", "geyser", "surf"]):
                            return "Water"
                        if any(k in n for k in ["ice", "glacia", "freeze", "blizzard"]):
                            return "Ice"
                        if any(k in n for k in ["psychic", "psy", "mind"]):
                            return "Psychic"
                        if any(k in n for k in ["iron", "steel", "metal"]):
                            return "Steel"
                        if any(k in n for k in ["dragon"]):
                            return "Dragon"
                        if any(k in n for k in ["shadow", "ghost"]):
                            return "Ghost"
                        if any(k in n for k in ["rock", "stone"]):
                            return "Rock"
                        if any(k in n for k in ["earth", "quake", "ground"]):
                            return "Ground"
                        if any(k in n for k in ["leaf", "grass", "seed", "vine"]):
                            return "Grass"
                        if any(k in n for k in ["dark", "night"]):
                            return "Dark"
                        if any(k in n for k in ["fairy", "charm", "gleam"]):
                            return "Fairy"
                        if any(k in n for k in ["poison", "toxic", "sludge"]):
                            return "Poison"
                        if any(k in n for k in ["bug", "u-turn", "x-scissor"]):
                            return "Bug"
                        if any(k in n for k in ["fight", "punch", "kick", "blast", "chop"]):
                            return "Fighting"
                        if any(k in n for k in ["fly", "aerial", "wing"]):
                            return "Flying"
                        return "Normal"
                    import re
                    # Split by '),', keep last ')'
                    chunks = [c.strip() for c in re.split(r"\)\s*,\s*", char_moves) if c.strip()]
                    moves_list = []
                    for chunk in chunks:
                        if not chunk.endswith(")"):
                            chunk = chunk + ")"
                        # Pattern with explicit Type
                        m1 = re.match(r"^(.*?)\s*\(\s*Type:\s*([A-Za-z ]+)\s*,\s*Power:\s*(\d+)\s*,\s*Acc:\s*(\d+)%\s*\)\s*$", chunk)
                        # Pattern without Type
                        m2 = re.match(r"^(.*?)\s*\(\s*Power:\s*(\d+)\s*,\s*Acc:\s*(\d+)%\s*\)\s*$", chunk)
                        if m1:
                            name = m1.group(1).strip()
                            mtype = m1.group(2).strip().title()
                            power = int(m1.group(3))
                            acc = int(m1.group(4))
                            moves_list.append({
                                "name": name,
                                "power": power,
                                "accuracy": acc,
                                "type": mtype or infer_type_from_name(name)
                            })
                        elif m2:
                            name = m2.group(1).strip()
                            power = int(m2.group(2))
                            acc = int(m2.group(3))
                            moves_list.append({
                                "name": name,
                                "power": power,
                                "accuracy": acc,
                                "type": infer_type_from_name(name)
                            })
                    char_moves = moves_list
            # Expect a list of move dicts
            if isinstance(char_moves, list):
                parsed_moves = [m for m in char_moves if isinstance(m, dict)]
        except Exception:
            parsed_moves = []

    # Try PokeAPI if no character-specific moves or parsing failed
    if not parsed_moves:
        name = character.get("name") or ""
        try:
            async with aiohttp.ClientSession() as session:
                api_moves = await _fetch_pokeapi_moves(name, session)
                if api_moves:
                    parsed_moves = api_moves
        except Exception:
            parsed_moves = []

    # Fallback to rarity-based moves when neither character-specific nor API moves
    if not parsed_moves:
        rarity = character.get("rarity", "Common")
        parsed_moves = list(RARITY_MOVES.get(rarity, []))  # type: ignore

    if not parsed_moves:
        return "🎯 <b>Moveset</b>\nNo moves available."

    lines: List[str] = ["🎯 <b>Moveset</b>"]
    for m in parsed_moves:
        name = m.get("name", "Unknown")
        power = m.get("power", "-")
        acc = m.get("accuracy", "-")
        mtype = m.get("type", "Normal")
        emoji = TYPE_EMOJIS.get(mtype, "⚪")
        effect = m.get("effect", "")
        lines.append(f"<b>{name}</b> [{mtype} {emoji}]\nPower: {power}, Accuracy: {acc}")
        if effect:
            lines.append(f"  {effect}")
    return "\n".join(lines)


@auto_register_user
async def poke_command(client: Client, message: Message):
    user_id = message.from_user.id
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("Usage: <code>/poke &lt;character_id&gt;</code>\nExample: <code>/poke 444</code>")
        return
    char_id = int(parts[1])

    user, character = await _get_user_and_character(user_id, char_id)
    if not character:
        await message.reply_text("❌ Pokémon not found.")
        return
    if not _user_owns_character(user, char_id):
        await message.reply_text("❌ You don't own this Pokémon.")
        return

    caption = await _base_caption(character, rank_stars=1)
    keyboard = build_poke_keyboard(user_id, char_id)

    # Prefer Telegram-stored file_id if present, else fallback to img_url
    file_id = character.get("file_id")
    img_url = character.get("img_url")
    try:
        if file_id:
            await client.send_photo(message.chat.id, file_id, caption=caption, reply_markup=keyboard)
        elif img_url:
            await client.send_photo(message.chat.id, img_url, caption=caption, reply_markup=keyboard)
        else:
            # No media; send as text with buttons
            await message.reply_text(caption, reply_markup=keyboard)
            return
    except Exception:
        # Fallback to text if sending media fails
        await message.reply_text(caption, reply_markup=keyboard)
        return


async def poke_callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data or ""
    if not (data.startswith("poke_stats_") or data.startswith("poke_moves_") or data.startswith("poke_info_")):
        await callback_query.answer()
        return
    try:
        parts = data.split("_")
        char_id = int(parts[-1])
        owner_id = int(parts[-2]) if len(parts) >= 3 else None
    except Exception:
        await callback_query.answer("Invalid data", show_alert=True)
        return

    user_id = callback_query.from_user.id
    # Access control: only owner can use inline buttons
    if owner_id is not None and user_id != owner_id:
        await callback_query.answer("Access denied", show_alert=True)
        return
    user, character = await _get_user_and_character(user_id, char_id)
    if not character or not _user_owns_character(user, char_id):
        await callback_query.answer("Not available", show_alert=True)
        return

    if data.startswith("poke_info_"):
        # Return to main pokemon info
        text = await _base_caption(character, rank_stars=1)
        keyboard = build_poke_keyboard(user_id, char_id)
    elif data.startswith("poke_stats_"):
        # Show only stats
        text = await _stats_text(character)
        keyboard = build_stats_only_keyboard(user_id, char_id)
    else:  # poke_moves_
        # Show only moves
        text = await _moves_text(character)
        keyboard = build_moves_only_keyboard(user_id, char_id)

    try:
        await client.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.id,
            caption=text,
            reply_markup=keyboard,
        )
        await callback_query.answer()
    except Exception:
        # If it's not a media message or edit failed, just edit text
        try:
            await client.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.id,
                text=text,
                reply_markup=keyboard,
            )
            await callback_query.answer()
        except Exception:
            await callback_query.answer("Unable to update.", show_alert=True)


