from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .decorators import is_owner, is_og
import os

from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display

# In-memory state for cooldown input
WAITING_FOR_CLAIM_COOLDOWN = set()

async def claimsettings_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    # Get current claim settings
    settings = await db.get_claim_settings()
    if not settings:
        settings = {
            'locked_rarities': [],
            'claim_cooldown': 24
        }
        await db.update_claim_settings(settings)
    # Create message showing current settings
    msg = "<b>🎯 ᴄʟᴀɪᴍ sᴇᴛᴛɪɴɢs</b>\n\n"
    msg += "<b>🔒 ʟᴏᴄᴋᴇᴅ ʀᴀʀɪᴛɪᴇs:</b>\n"
    if settings.get('locked_rarities'):
        for rarity in settings['locked_rarities']:
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            msg += f"• {emoji} {rarity}\n"
    else:
        msg += "• No rarities locked\n"
    cooldown = settings.get('claim_cooldown', 24)
    msg += f"\n<b>⏰ ᴄʟᴀɪᴍ ᴄᴏᴏʟᴅᴏᴡɴ:</b> <code>{cooldown}</code> hours"
    # Create keyboard
    keyboard = []
    for rarity in RARITIES:
        emoji = RARITY_EMOJIS.get(rarity, "❓")
        is_locked = rarity in settings.get('locked_rarities', [])
        status = "🔒" if is_locked else "🔓"
        keyboard.append([
            InlineKeyboardButton(f"{status} {emoji} {rarity}", callback_data=f"claim_toggle_{rarity}")
        ])
    keyboard.append([
        InlineKeyboardButton("⏰ Set Cooldown", callback_data="claim_cooldown")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(msg, reply_markup=reply_markup)

async def claimsettings_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await callback_query.answer("❌ You don't have permission!", show_alert=True)
        return
    data = callback_query.data
    if data.startswith("claim_toggle_"):
        rarity = data[len("claim_toggle_"):]
        settings = await db.get_claim_settings()
        locked_rarities = settings.get('locked_rarities', [])
        if rarity in locked_rarities:
            locked_rarities.remove(rarity)
        else:
            locked_rarities.append(rarity)
        await db.update_claim_settings({'locked_rarities': locked_rarities})
        # Update keyboard
        keyboard = []
        for r in RARITIES:
            emoji = RARITY_EMOJIS.get(r, "❓")
            is_locked = r in locked_rarities
            status = "🔒" if is_locked else "🔓"
            keyboard.append([
                InlineKeyboardButton(f"{status} {emoji} {r}", callback_data=f"claim_toggle_{r}")
            ])
        keyboard.append([
            InlineKeyboardButton("⏰ Set Cooldown", callback_data="claim_cooldown")
        ])
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await callback_query.answer(f"{'Locked' if rarity in locked_rarities else 'Unlocked'} {rarity} rarity", show_alert=True)
    elif data == "claim_cooldown":
        WAITING_FOR_CLAIM_COOLDOWN.add(user_id)
        await callback_query.message.reply_text(
            "<b>⏰ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴛʜᴇ ɴᴇᴡ ᴄᴏᴏʟᴅᴏᴡɴ ɪɴ ʜᴏᴜʀs (1-72):</b>"
        )
        await callback_query.answer()

async def claimsettings_cooldown_input(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in WAITING_FOR_CLAIM_COOLDOWN:
        return
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    try:
        cooldown = int(message.text)
        if not 1 <= cooldown <= 72:
            await message.reply_text("<b>❌ ᴄᴏᴏʟᴅᴏᴡɴ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 72 ʜᴏᴜʀs!</b>")
            return
        await db.update_claim_settings({'claim_cooldown': cooldown})
        await message.reply_text(f"<b>✅ ᴄʟᴀɪᴍ ᴄᴏᴏʟᴅᴏᴡɴ sᴇᴛ ᴛᴏ {cooldown} ʜᴏᴜʀs!</b>")
    except ValueError:
        await message.reply_text("<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!</b>")
    WAITING_FOR_CLAIM_COOLDOWN.discard(user_id)

def register_claim_settings_handlers(app: Client):
    app.on_message(filters.command("claimsettings"))(claimsettings_command)
    app.on_callback_query(lambda _, q: q.data.startswith("claim_toggle_") or q.data == "claim_cooldown")(claimsettings_callback)
    app.on_message(filters.text & filters.create(lambda _, m, __: hasattr(m, 'from_user') and m.from_user and m.from_user.id in WAITING_FOR_CLAIM_COOLDOWN))(claimsettings_cooldown_input)