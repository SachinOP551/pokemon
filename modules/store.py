import random
from datetime import datetime
## No shared daily_store import needed for per-user store
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from modules.postgres_database import get_database
from pyrogram.enums import ChatType
from modules.decorators import owner_only

RARITY_EMOJIS = {
    "Common": "⚪️",
    "Medium": "🟢",
    "Rare": "🟠",
    "Legendary": "🟡",
    "Exclusive": "🫧",
    "Elite": "💎",
    "Limited Edition": "🔮",
    "Ultimate": "🔱",
    "Supreme": "👑",
    "Zenith": "💫",
    "Ethereal": "❄️",
    "Mythic": "🔴",
    "Premium": "🧿"
}

RARITY_PRICES = {
    "Common": 15000,
    "Medium": 18500,
    "Rare": 24500,
    "Legendary": 36500,
    "Exclusive": 320000,
    "Elite": 625900,
    "Limited Edition": 1320000,
    # Ultimate price is handled separately (shards only)
    "Supreme": 1440000000,
    "Ethereal": 2670000,
    "Mythic": 1288000,
    "Zenith": 1528000,
    "Premium": 40000000  # 4 crore tokens
}

ULTIMATE_SHARD_PRICE = 120000  # 120K shards

STORE_IMAGE_URL = "https://ibb.co/cKVVS0wm"
REFRESH_COST = 45000

# Format the store message as per the user's example
# Now takes refreshes and max_refreshes
MAX_REFRESHES = 3

def format_store_message(chars, refreshes, refresh_cost=REFRESH_COST):
    # Safety check: filter out any characters with is_video=True that might have slipped through
    chars = [c for c in chars if not c.get("is_video", False)]
    
    msg = "<b>This Is Your Today's Store:</b>\n"
    for c in chars:
        emoji = RARITY_EMOJIS.get(c["rarity"], "❓")
        # Always prefer character_id for display
        char_id = c.get("character_id") or c.get("id") or c.get("_id")
        if c["rarity"] == "Ultimate":
            msg += f"<b>\n{emoji} {char_id} {c['name']}\nRarity: {c['rarity']} | Price: {ULTIMATE_SHARD_PRICE:,} 🎐 Shards\n</b>"
        else:
            price = RARITY_PRICES.get(c["rarity"], 100000)
            msg += f"<b>\n{emoji} {char_id} {c['name']}\nRarity: {c['rarity']} | Price: {price:,} tokens\n</b>"
    msg += "\n"
    if refreshes == 0:
        msg += f"<b>🔄 1 free refresh left today.({MAX_REFRESHES - refreshes} total left)</b>"
    else:
        left = MAX_REFRESHES - refreshes
        if left > 0:
            msg += f"<b>🔄 Refresh cost: {refresh_cost:,} tokens. ({left} left today)</b>"
        else:
            msg += "<b>❌ No refreshes left today.</b>"
    return msg

def get_store_keyboard(refreshes):
    buttons = []
    # Add buy button
    buttons.append([InlineKeyboardButton("🛒 Buy Character", callback_data="buy_from_store")])
    
    # Add refresh button if available
    if refreshes < MAX_REFRESHES:
        btn_text = "🔄 Refresh Store (Free)" if refreshes == 0 else f"🔄 Refresh Store ({REFRESH_COST:,} tokens)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data="refresh_store")])
    
    return InlineKeyboardMarkup(buttons) if buttons else None

# Define weights for rarities
RARITY_WEIGHTS = {
    "Common": 1,
    "Medium": 1,
    "Rare": 1,
    "Legendary": 1,
    "Exclusive": 1,
    "Elite": 1,
    "Limited Edition": 1,
    "Ultimate": 2,
    "Ethereal": 1,
    "Mythic": 1,
    "Zenith": 1,
    "Premium": 3  # Added Premium with weight 1
    # "Supreme" is excluded
}

def get_weighted_random_characters_sync(all_chars, count=10):
    # Prepare weights
    weights = [RARITY_WEIGHTS.get(c["rarity"], 1) for c in all_chars]
    # Select without replacement, but with weights
    selected = []
    pool = all_chars[:]
    pool_weights = weights[:]
    
    # First try to select without replacement
    for _ in range(min(count, len(pool))):
        if not pool:
            break
        chosen = random.choices(pool, weights=pool_weights, k=1)[0]
        selected.append(chosen)
        idx = pool.index(chosen)
        pool.pop(idx)
        pool_weights.pop(idx)
    
    # If we still need more characters, duplicate some from the selected ones
    while len(selected) < count:
        if selected:
            # Randomly select from already selected characters
            chosen = random.choice(selected)
            selected.append(chosen)
        else:
            # If no characters were selected at all, this shouldn't happen but handle it
            break
    return selected

async def get_weighted_random_characters(db, count=10):
    # Use PostgreSQL aggregation to get store-eligible characters
    # This method already handles filtering for Supreme rarity, is_video=True, and excluded IDs
    # Request more characters than needed to account for potential filtering
    request_count = max(count * 2, 20)  # Request at least 20 characters to ensure we get enough
    eligible_chars = await db.get_store_eligible_characters(request_count)
    
    if not eligible_chars:
        return []
    
    # Apply weighted random selection from the filtered characters
    selected = get_weighted_random_characters_sync(eligible_chars, count)
    
    # If we still don't have enough characters, try to get more from the database
    if len(selected) < count and len(eligible_chars) < request_count:
        # Try to get more characters from the database
        additional_chars = await db.get_store_eligible_characters(request_count * 2)
        if additional_chars:
            # Combine and deduplicate
            all_chars = eligible_chars + [c for c in additional_chars if c not in eligible_chars]
            selected = get_weighted_random_characters_sync(all_chars, count)
    return selected

async def get_daily_store_offer(db, user_id):
    """Get or generate the shared daily store offer for all users."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    user = await db.get_user(user_id)
    offer = user.get("store_offer", {}) if user else {}
    # Defensive: If offer is a string, parse it as JSON
    import json
    if isinstance(offer, str):
        try:
            offer = json.loads(offer)
        except Exception:
            offer = {}
    if not isinstance(offer, dict):
        offer = None
    # Only generate a new store if it's a new day or offer is missing or offer['date'] != today
    if not offer or offer.get("date") != today:
        offer_chars = await get_weighted_random_characters(db, 10)
        offer = {
            "date": today,
            "characters": [c.get("character_id") or c.get("id") or c.get("_id") for c in offer_chars],
            "refreshes": 0,
            "purchased": [],
            "pending_buy": None
        }
        await db.update_user(user_id, {"store_offer": offer})
    # Ensure all required fields exist for compatibility
    if "refreshes" not in offer:
        offer["refreshes"] = 0
    if "purchased" not in offer:
        offer["purchased"] = []
    if "pending_buy" not in offer:
        offer["pending_buy"] = None
    if "characters" not in offer or not isinstance(offer["characters"], list) or not offer["characters"]:
        # Generate a new offer if characters is missing or invalid
        offer_chars = await get_weighted_random_characters(db, 10)
        offer["characters"] = [c.get("character_id") or c.get("id") or c.get("_id") for c in offer_chars]
        await db.update_user(user_id, {"store_offer": offer})
    return offer

@Client.on_message(filters.command("mystore"))
async def mystore_command(client: Client, message: Message):
    # print(f"[DEBUG] chat.type: {repr(message.chat.type)} (type: {type(message.chat.type)})")
    wait_msg = await message.reply("Please wait, let me fetch today's store for you....")
    db = get_database()
    user_id = message.from_user.id
    offer = await get_daily_store_offer(db, user_id)
    
    # Batch fetch all characters for speed using PostgreSQL
    char_ids = offer["characters"]
    char_docs = await db.get_characters_by_ids(char_ids)
    
    id_to_char = {c.get('character_id') or c.get('id') or c.get('_id'): c for c in char_docs}
    chars = [id_to_char.get(cid) for cid in char_ids if id_to_char.get(cid)]
    
    # Safety check: filter out any characters with is_video=True that might have slipped through
    chars = [c for c in chars if not c.get("is_video", False)]
    
    refreshes = offer.get("refreshes", 0)
    text = format_store_message(chars, refreshes)
    # Only show buttons in private chat (enum check)
    reply_markup = None
    if message.chat.type == ChatType.PRIVATE:
        reply_markup = get_store_keyboard(refreshes)
    await message.reply_photo(
        STORE_IMAGE_URL,
        caption=text,
        reply_markup=reply_markup
    )
    await wait_msg.delete()

@Client.on_callback_query(filters.regex("^buy_from_store$"))
async def buy_from_store_callback(client: Client, callback_query: CallbackQuery):
    # Delete the store message
    await callback_query.message.delete()
    
    # Mark user as waiting for ID input
    waiting_for_id[callback_query.from_user.id] = True
    
    # Ask for character ID
    await callback_query.message.reply(
        "🛒 <b>Buy Character from Store</b>\n\n"
        "Please enter the ID of the character you want to buy:\n"
        "Example: `123`"
    )
    await callback_query.answer("Please enter the character ID")

@Client.on_callback_query(filters.regex("^refresh_store$"))
async def refresh_store_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user_id = callback_query.from_user.id
    today = datetime.utcnow().strftime("%Y-%m-%d")
    user = await db.get_user(user_id)
    offer = user.get("store_offer", {}) if user else {}
    # Defensive: If offer is a string, parse it as JSON
    import json
    if isinstance(offer, str):
        try:
            offer = json.loads(offer)
        except Exception:
            offer = {}
    refreshes = offer.get("refreshes", 0)
    # If offer is not for today, reset refreshes and offer in DB
    if offer.get("date") != today:
        refreshes = 0
        # Reset offer for today, preserving purchased and pending_buy if present
        purchased = offer.get("purchased", [])
        pending_buy = offer.get("pending_buy", None)
        offer["date"] = today
        offer["refreshes"] = 0
        offer["purchased"] = purchased
        offer["pending_buy"] = pending_buy
        await db.update_user(user_id, {"store_offer": offer})
        # Re-fetch offer from DB to ensure we have the latest state
        user = await db.get_user(user_id)
        offer = user.get("store_offer", {}) if user else {}
        refreshes = offer.get("refreshes", 0)
    if refreshes >= MAX_REFRESHES:
        await callback_query.answer("No refreshes left today!", show_alert=True)
        return
    free_refresh = refreshes == 0
    # Check tokens if not free
    if not free_refresh and user.get("wallet", 0) < REFRESH_COST:
        await callback_query.answer("Not enough tokens for refresh!", show_alert=True)
        return
    # Deduct tokens if not free
    if not free_refresh:
        await db.update_user(user_id, {"wallet": user["wallet"] - REFRESH_COST})
    # Generate new offer using fast random sampling
    offer_chars = await get_weighted_random_characters(db, 10)
    
    new_refreshes = refreshes + 1
    # Preserve purchased and pending_buy fields
    purchased = offer.get("purchased", [])
    pending_buy = offer.get("pending_buy", None)
    new_offer = {
        "date": today,
        "characters": [c.get("character_id") or c.get("id") or c.get("_id") for c in offer_chars],
        "refreshes": new_refreshes,
        "purchased": purchased,
        "pending_buy": pending_buy
    }
    
    await db.update_user(user_id, {"store_offer": new_offer})
    # Batch fetch all characters for speed using PostgreSQL
    char_ids = new_offer["characters"]
    char_docs = await db.get_characters_by_ids(char_ids)
    
    id_to_char = {c.get('character_id') or c.get('id') or c.get('_id'): c for c in char_docs}
    chars = [id_to_char.get(cid) for cid in char_ids if id_to_char.get(cid)]
    
    # Safety check: filter out any characters with is_video=True that might have slipped through
    chars = [c for c in chars if not c.get("is_video", False)]
    
    text = format_store_message(chars, new_refreshes)
    reply_markup = get_store_keyboard(new_refreshes)
    await callback_query.edit_message_caption(
        caption=text,
        reply_markup=reply_markup
    )
    await callback_query.answer("Store refreshed!")

# Dictionary to track users waiting for character ID input
waiting_for_id = {}

@Client.on_message(filters.command("buy"))
async def buy_command(client: Client, message: Message):
    # Only allow /buy in private chat (enum check)
    if message.chat.type != ChatType.PRIVATE:
        await message.reply("<b>Please use the /buy command in the bot's DM (private chat)</b>")
        return
    db = get_database()
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply("Usage: /buy <id>")
        return
    char_id = int(args[1])
    await process_buy_request(client, message, char_id)

@Client.on_message(filters.regex(r"^\d+$") & filters.private)
async def handle_id_input(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in waiting_for_id:
        # Remove from waiting list
        del waiting_for_id[user_id]
        
        # Process the ID input
        char_id = int(message.text)
        await process_buy_request(client, message, char_id)
    else:
        # Not waiting for ID, ignore
        pass

async def process_buy_request(client: Client, message: Message, char_id: int):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    offer = user.get("store_offer", {}) if user else {}
    # Defensive: If offer is a string, parse it as JSON
    import json
    if isinstance(offer, str):
        try:
            offer = json.loads(offer)
        except Exception:
            offer = {}
    if not isinstance(offer, dict):
        offer = {}
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Reset purchased list if new day
    if offer.get("date") != today:
        offer["purchased"] = []
        offer["date"] = today
        offer["pending_buy"] = None
        await db.update_user(user_id, {"store_offer": offer})
    purchased = offer.get("purchased", [])
    offer_chars = offer.get("characters", [])
    pending_buy = offer.get("pending_buy")
    if char_id not in offer_chars:
        await message.reply("This character is not available in your store offer.")
        return
    if char_id in purchased:
        await message.reply("You have already purchased this character from your store today. You can buy it again tomorrow!")
        return
    if pending_buy == char_id:
        await message.reply("You already have a pending confirmation for this character. Please confirm or wait before trying again.")
        return
    char = await db.get_character(char_id)
    if not char:
        await message.reply("Character not found.")
        return
    if char["rarity"] == "Ultimate":
        if user.get("shards", 0) < ULTIMATE_SHARD_PRICE:
            await message.reply("You don't have enough 🎐 Shards!")
            return
    else:
        price = RARITY_PRICES.get(char["rarity"], 100000)
        if user.get("wallet", 0) < price:
            await message.reply("You don't have enough tokens!")
            return
    # Set pending confirmation
    offer["pending_buy"] = char_id
    await db.update_user(user_id, {"store_offer": offer})
    # Show confirmation with image and button
    img_url = char.get("img_url")
    if char["rarity"] == "Ultimate":
        caption = (
            f"<b>Confirm Purchase</b>\n\n"
            f"<b>Name:</b> {char['name']}\n"
            f"<b>Rarity:</b> {char['rarity']}\n"
            f"<b>Price:</b> {ULTIMATE_SHARD_PRICE:,} 🎐 Shards\n\n"
            f"Are you sure you want to buy this character?"
        )
    else:
        price = RARITY_PRICES.get(char["rarity"], 100000)
        caption = (
            f"<b>Confirm Purchase</b>\n\n"
            f"<b>Name:</b> {char['name']}\n"
            f"<b>Rarity:</b> {char['rarity']}\n"
            f"<b>Price:</b> {price:,} tokens\n\n"
            f"Are you sure you want to buy this character?"
        )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm Purchase", callback_data=f"confirm_buy_{char_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_buy_{char_id}")
        ]
    ])
    if img_url:
        await message.reply_photo(img_url, caption=caption, reply_markup=keyboard)
    else:
        await message.reply(caption, reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^confirm_buy_(\d+)$"))
async def confirm_buy_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user_id = callback_query.from_user.id
    char_id = int(callback_query.data.split("_")[-1])
    user = await db.get_user(user_id)
    offer = user.get("store_offer", {}) if user else {}
    # Defensive: If offer is a string, parse it as JSON
    import json
    if isinstance(offer, str):
        try:
            offer = json.loads(offer)
        except Exception:
            offer = {}
    if not isinstance(offer, dict):
        offer = {}
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Reset purchased list if new day
    if offer.get("date") != today:
        offer["purchased"] = []
        offer["date"] = today
        offer["pending_buy"] = None
        await db.update_user(user_id, {"store_offer": offer})
    purchased = offer.get("purchased", [])
    offer_chars = offer.get("characters", [])
    pending_buy = offer.get("pending_buy")
    if char_id not in offer_chars:
        await callback_query.answer("Not in your store offer.", show_alert=True)
        return
    if char_id in purchased:
        await callback_query.answer("Already purchased today.", show_alert=True)
        return
    if pending_buy != char_id:
        await callback_query.answer("No pending confirmation for this character. Please use /buy <id> again.", show_alert=True)
        return
    char = await db.get_character(char_id)
    if not char:
        await callback_query.answer("Character not found.", show_alert=True)
        return
    if char["rarity"] == "Ultimate":
        if user.get("shards", 0) < ULTIMATE_SHARD_PRICE:
            await callback_query.answer("Not enough 🎐 Shards!", show_alert=True)
            return
    else:
        price = RARITY_PRICES.get(char["rarity"], 100000)
        if user.get("wallet", 0) < price:
            await callback_query.answer("Not enough tokens!", show_alert=True)
            return
    # Deduct tokens, add character, mark as purchased, clear pending
    if char["rarity"] == "Ultimate":
        await db.update_user(user_id, {
            "shards": user["shards"] - ULTIMATE_SHARD_PRICE,
            "characters": user.get("characters", []) + [char_id],
            "store_offer": {
                **offer,
                "purchased": purchased + [char_id],
                "pending_buy": None,
                "date": today
            }
        })
    else:
        await db.update_user(user_id, {
            "wallet": user["wallet"] - price,
            "characters": user.get("characters", []) + [char_id],
            "store_offer": {
                **offer,
                "purchased": purchased + [char_id],
                "pending_buy": None,
                "date": today
            }
        })
    # Log transaction
    await db.log_user_transaction(user_id, "store_purchase", {
        "character_id": char_id,
        "name": char["name"],
        "rarity": char["rarity"],
        "price": ULTIMATE_SHARD_PRICE if char["rarity"] == "Ultimate" else price,
        "date": today
    })
    if char["rarity"] == "Ultimate":
        await callback_query.edit_message_caption(
            caption=f"<b>Congratulations!</b> You bought <b>{char['name']}</b> for <b>{ULTIMATE_SHARD_PRICE:,}</b> 🎐 Shards."
        )
    else:
        await callback_query.edit_message_caption(
            caption=f"<b>Congratulations!</b> You bought <b>{char['name']}</b> for <b>{price:,}</b> tokens."
        )
    await callback_query.answer("Purchase successful!")

@Client.on_callback_query(filters.regex(r"^cancel_buy_(\d+)$"))
async def cancel_buy_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user_id = callback_query.from_user.id
    char_id = int(callback_query.data.split("_")[-1])
    user = await db.get_user(user_id)
    offer = user.get("store_offer", {}) if user else {}
    # Defensive: If offer is a string, parse it as JSON
    import json
    if isinstance(offer, str):
        try:
            offer = json.loads(offer)
        except Exception:
            offer = {}
    if not isinstance(offer, dict):
        offer = {}
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Reset purchased list if new day
    if offer.get("date") != today:
        offer["purchased"] = []
        offer["date"] = today
        offer["pending_buy"] = None
        await db.update_user(user_id, {"store_offer": offer})
    pending_buy = offer.get("pending_buy")
    if not pending_buy:
        await callback_query.edit_message_caption(
            caption="<b>No purchase is currently pending.</b>"
        )
        await callback_query.answer("No purchase is currently pending.")
        return
    # Always clear pending buy, regardless of char_id
    offer["pending_buy"] = None
    await db.update_user(user_id, {"store_offer": offer})
    await callback_query.edit_message_caption(
        caption="<b>Purchase cancelled.</b>"
    )
    await callback_query.answer("Purchase cancelled.")

@Client.on_message(filters.command("refreshallstores"))
@owner_only
async def refresh_all_stores_command(client: Client, message: Message):
    db = get_database()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    user_ids = await db.get_all_user_ids()
    updated = 0
    for user_id in user_ids:
        offer_chars = await get_weighted_random_characters(db, 10)
        offer = {
            "date": today,
            "characters": [c.get("character_id") or c.get("id") or c.get("_id") for c in offer_chars],
            "refreshes": 0
        }
        await db.update_user(user_id, {"store_offer": offer})
        updated += 1
    await message.reply(f"✅ Refreshed store for <b>{updated}</b> users.")
