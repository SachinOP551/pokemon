import logging
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from modules.postgres_database import get_database

from .decorators import check_banned

# Rarity emojis mapping - Updated to match the correct order
RARITY_EMOJIS = {
    "Common": "⚪️",
    "Medium": "🟢",
    "Rare": "🟠",
    "Legendary": "🟡",
    "Exclusive": "🫧",
    "Elite": "💎",
    "Limited Edition": "🔮",
    "Ultimate": "🔱",
    "Premium": "🧿",
    "Supreme": "👑",
    "Mythic": "🔴",
    "Zenith": "💫",
    "Ethereal": "❄️",
    "Mega Evolution": "🧬"
}

# In-memory lock for srarity sessions: message_id -> user_id
SRARITY_SESSION_LOCK = {}

@check_banned
async def srarity_command(client: Client, message: Message):
    """Show rarity selection buttons"""
    keyboard = []
    row = []
    for rarity, emoji in RARITY_EMOJIS.items():
        if len(row) == 2:
            keyboard.append(row)
            row = []
        row.append(InlineKeyboardButton(f"{emoji} {rarity}", callback_data=f"r_{rarity}"))
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent = await message.reply_text(
        "<b>🎭 Select a rarity to view characters</b>\nChoose a rarity below to see all available characters in that category.",
        reply_markup=reply_markup
    )
    # Lock this menu to the user who triggered it
    SRARITY_SESSION_LOCK[sent.id] = message.from_user.id

@check_banned
async def rarity_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    data = callback_query.data
    user_id = callback_query.from_user.id
    # Guard: message may be None (shouldn't happen, but just in case)
    if not callback_query.message:
        await callback_query.answer("This menu is no longer available.", show_alert=True)
        return
    msg_id = callback_query.message.id
    # Edge case: Only allow the user who triggered the menu to interact
    allowed_user_id = SRARITY_SESSION_LOCK.get(msg_id)
    if allowed_user_id is not None and user_id != allowed_user_id:
        await callback_query.answer("Access denied: you are not the one who triggered this action.", show_alert=True)
        return
    # Handle close button
    if data == "close":
        # Clean up lock BEFORE deleting message
        SRARITY_SESSION_LOCK.pop(msg_id, None)
        try:
            await callback_query.message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")
            await callback_query.message.edit_text("<b>❌ Closed</b>")
        return
    # Handle back button
    if data == "r_back":
        await show_rarity_menu(callback_query)
        return
    # Handle page navigation
    if data.startswith("p_"):
        _, rarity, page = data.split('_')
        page = int(page)
        await show_rarity_list(callback_query, rarity, page)
        return
    # Handle rarity selection
    if data.startswith("r_"):
        rarity = data[2:]
        await show_rarity_list(callback_query, rarity, 1)
        return

def get_rarity_keyboard(rarity, page, total_pages):
    keyboard = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"p_{rarity}_{page-1}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"p_{rarity}_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="r_back")])
    keyboard.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    return InlineKeyboardMarkup(keyboard)

async def show_rarity_menu(callback_query: CallbackQuery):
    keyboard = []
    row = []
    for rarity, emoji in RARITY_EMOJIS.items():
        if len(row) == 2:
            keyboard.append(row)
            row = []
        row.append(InlineKeyboardButton(f"{emoji} {rarity}", callback_data=f"r_{rarity}"))
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await callback_query.message.edit_text(
        "<b>🎭 Select a rarity to view characters</b>\nChoose a rarity below to see all available characters in that category.",
        reply_markup=reply_markup
    )

async def show_rarity_list(callback_query: CallbackQuery, rarity: str, page: int):
    db = get_database()
    items_per_page = 15
    try:
        # Use SQL query for PostgreSQL instead of MongoDB find()
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Get total count
                count_result = await conn.fetchrow(
                    "SELECT COUNT(*) FROM characters WHERE rarity = $1",
                    rarity
                )
                total = count_result[0] if count_result else 0
                
                # Get characters for current page
                offset = (page - 1) * items_per_page
                characters = await conn.fetch(
                    "SELECT character_id, name FROM characters WHERE rarity = $1 ORDER BY character_id LIMIT $2 OFFSET $3",
                    rarity, items_per_page, offset
                )
        else:  # MongoDB
            characters = await db.characters.find({'rarity': rarity}, {'character_id': 1, 'name': 1}).sort('character_id', 1).to_list(None)
            total = len(characters)
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            characters = characters[start_idx:end_idx]
        
        total_pages = (total + items_per_page - 1) // items_per_page or 1
        
        # Initialize msg variable
        msg = ""
        
        if not characters:
            msg += "<b>❌ No characters available in this rarity!</b>"
        else:
            for char in characters:
                if hasattr(db, 'pool'):  # PostgreSQL
                    char_id = char['character_id']
                    name = char['name']
                else:  # MongoDB
                    char_id = char['character_id']
                    name = char['name']
                msg += f"<code>({char_id})</code> {RARITY_EMOJIS.get(rarity, '')} {name}\n"
        
        reply_markup = get_rarity_keyboard(rarity, page, total_pages)
        await callback_query.message.edit_text(msg, reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Error in show_rarity_list: {e}")
        await callback_query.message.edit_text(
            "<b>❌ An error occurred while loading characters! Please try again.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="r_back")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ])
        )