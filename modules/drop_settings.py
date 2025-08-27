from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .decorators import admin_only, is_owner, is_og
import os

# Import database based on configuration
from modules.postgres_database import get_database, RARITIES, RARITY_EMOJIS
from datetime import datetime

# --- Drop Settings Commands ---

@admin_only
async def drop_settings_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    # Check if user has permission
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    # Get current settings
    settings = await db.get_drop_settings()
    # Ensure all required keys exist
    if not settings:
        settings = {}
    if 'locked_rarities' not in settings:
        settings['locked_rarities'] = []
    if 'rarity_frequency' not in settings:
        settings['rarity_frequency'] = {}
    if 'daily_limits' not in settings:
        settings['daily_limits'] = {}
    if 'daily_drops' not in settings:
        settings['daily_drops'] = {}

    # Build settings message
    message_text = "<b>🎮 Drop Settings</b>\n\n"
    # Show locked rarities
    message_text += "<b>🔒 Locked Rarities:</b>\n"
    if settings['locked_rarities']:
        for rarity in settings['locked_rarities']:
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            message_text += f"├ {emoji} {rarity}\n"
    else:
        message_text += "├ No rarities locked\n"
    message_text += "└\n\n"
    # Show rarity frequency and daily limits
    message_text += "<b>📊 Rarity Settings:</b>\n"
    has_settings = False
    for rarity, emoji in RARITY_EMOJIS.items():
        if rarity not in settings['locked_rarities']:
            settings_info = []
            if rarity in settings['rarity_frequency']:
                settings_info.append(f"Freq: {settings['rarity_frequency'][rarity]} msgs")
            if rarity in settings['daily_limits']:
                current_drops = settings['daily_drops'].get(rarity, 0)
                settings_info.append(f"Limit: {current_drops}/{settings['daily_limits'][rarity]}")
            if settings_info:
                has_settings = True
                message_text += f"├ {emoji} {rarity}\n"
                message_text += "│ └ " + " | ".join(settings_info) + "\n"
    if not has_settings:
        message_text += "├ No custom settings set\n"
    message_text += "└\n\n"
    # Add instructions
    message_text += "<b>Commands:</b>\n"
    message_text += "├ /lockrarity <rarity> - Lock a rarity\n"
    message_text += "├ /unlockrarity <rarity> - Unlock a rarity\n"
    message_text += "├ /setfrequency <rarity> <messages> - Set drop frequency\n"
    message_text += "└ /setdailylimit <rarity> <limit> - Set daily drop limit"
    # Create keyboard
    keyboard = [
        [
            InlineKeyboardButton("🔒 Lock Rarity", callback_data="drop_lock"),
            InlineKeyboardButton("🔓 Unlock Rarity", callback_data="drop_unlock")
        ],
        [
            InlineKeyboardButton("📊 Set Frequency", callback_data="drop_frequency"),
            InlineKeyboardButton("📈 Set Daily Limit", callback_data="drop_daily_limit")
        ],
        [
            InlineKeyboardButton("🔄 Reset All", callback_data="drop_reset")
        ]
    ]
    await message.reply_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@admin_only
async def lock_rarity_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    parts = message.text.split()[1:]
    if not parts:
        await message.reply_text("❌ Please provide a rarity!")
        return
    rarity = " ".join(parts)
    if rarity not in RARITIES:
        await message.reply_text("❌ Invalid rarity!")
        return
    settings = await db.get_drop_settings()
    if not settings:
        settings = {
            'locked_rarities': [],
            'rarity_frequency': {r: 100 for r in RARITIES.keys()}
        }
    if rarity not in settings['locked_rarities']:
        settings['locked_rarities'].append(rarity)
        await db.update_drop_settings(settings)
        emoji = RARITY_EMOJIS.get(rarity, "❓")
        await message.reply_text(f"✅ {emoji} {rarity} has been locked!")
    else:
        await message.reply_text("❌ This rarity is already locked!")

@admin_only
async def unlock_rarity_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    parts = message.text.split()[1:]
    if not parts:
        await message.reply_text("❌ Please provide a rarity!")
        return
    rarity = " ".join(parts)
    if rarity not in RARITIES:
        await message.reply_text("❌ Invalid rarity!")
        return
    settings = await db.get_drop_settings()
    if not settings:
        settings = {
            'locked_rarities': [],
            'rarity_frequency': {r: 100 for r in RARITIES.keys()}
        }
    if rarity in settings['locked_rarities']:
        settings['locked_rarities'].remove(rarity)
        await db.update_drop_settings(settings)
        emoji = RARITY_EMOJIS.get(rarity, "❓")
        await message.reply_text(f"✅ {emoji} {rarity} has been unlocked!")
    else:
        await message.reply_text("❌ This rarity is not locked!")

@admin_only
async def set_frequency_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    parts = message.text.split()[1:]
    if len(parts) < 2:
        await message.reply_text("❌ Please provide rarity and message count!")
        return
    rarity = " ".join(parts[:-1])
    try:
        message_count = int(parts[-1])
        if message_count < 1:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ Invalid message count!")
        return
    if rarity not in RARITIES:
        await message.reply_text("❌ Invalid rarity!")
        return
    settings = await db.get_drop_settings()
    if not settings:
        settings = {
            'locked_rarities': [],
            'rarity_frequency': {r: 100 for r in RARITIES.keys()}
        }
    settings['rarity_frequency'][rarity] = message_count
    await db.update_drop_settings(settings)
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    await message.reply_text(f"✅ {emoji} {rarity} frequency set to {message_count} messages!")

@admin_only
async def set_daily_limit_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    parts = message.text.split()[1:]
    if len(parts) < 2:
        await message.reply_text("❌ Please provide rarity and daily limit!")
        return
    rarity = " ".join(parts[:-1])
    try:
        daily_limit = int(parts[-1])
        if daily_limit < 0:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ Invalid daily limit!")
        return
    if rarity not in RARITIES:
        await message.reply_text("❌ Invalid rarity!")
        return
    settings = await db.get_drop_settings()
    if not settings:
        settings = {
            'locked_rarities': [],
            'rarity_frequency': {},
            'daily_limits': {},
            'daily_drops': {}
        }
    if 'daily_limits' not in settings:
        settings['daily_limits'] = {}
    settings['daily_limits'][rarity] = daily_limit
    await db.update_drop_settings(settings)
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    await message.reply_text(f"✅ {emoji} {rarity} daily limit set to {daily_limit} drops!")

@admin_only
async def drop_settings_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    action = callback_query.data
    if action == "drop_lock":
        # Show rarity selection for locking
        keyboard = []
        for rarity, emoji in RARITY_EMOJIS.items():
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {rarity}",
                callback_data=f"lock_{rarity}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="drop_settings")])
        await callback_query.edit_message_text(
            "Select rarity to lock:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif action == "drop_unlock":
        # Show locked rarities for unlocking
        settings = await db.get_drop_settings()
        if not settings or not settings['locked_rarities']:
            await callback_query.answer("No rarities are locked!", show_alert=True)
            return
        keyboard = []
        for rarity in settings['locked_rarities']:
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {rarity}",
                callback_data=f"unlock_{rarity}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="drop_settings")])
        await callback_query.edit_message_text(
            "Select rarity to unlock:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif action == "drop_frequency":
        # Show rarity selection for frequency
        keyboard = []
        for rarity, emoji in RARITY_EMOJIS.items():
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {rarity}",
                callback_data=f"freq_{rarity}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="drop_settings")])
        await callback_query.edit_message_text(
            "Select rarity to set frequency:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif action == "drop_reset":
        # Reset all settings
        settings = {
            'locked_rarities': [],
            'rarity_frequency': {r: 100 for r in RARITIES.keys()},
            'daily_limits': {},
            'daily_drops': {},
            'last_reset_date': datetime.now().strftime('%Y-%m-%d')
        }
        await db.update_drop_settings(settings)
        await callback_query.answer("All settings have been reset!", show_alert=True)
        await drop_settings_command(client, callback_query.message)
    elif action == "drop_settings":
        await drop_settings_command(client, callback_query.message)
    elif action.startswith("lock_"):
        rarity = action[5:]
        settings = await db.get_drop_settings()
        if not settings:
            settings = {
                'locked_rarities': [],
                'rarity_frequency': {r: 100 for r in RARITIES.keys()}
            }
        if rarity not in settings['locked_rarities']:
            settings['locked_rarities'].append(rarity)
            await db.update_drop_settings(settings)
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            await callback_query.answer(f"{emoji} {rarity} has been locked!", show_alert=True)
        else:
            await callback_query.answer("This rarity is already locked!", show_alert=True)
        await drop_settings_command(client, callback_query.message)
    elif action.startswith("unlock_"):
        rarity = action[7:]
        settings = await db.get_drop_settings()
        if settings and rarity in settings['locked_rarities']:
            settings['locked_rarities'].remove(rarity)
            await db.update_drop_settings(settings)
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            await callback_query.answer(f"{emoji} {rarity} has been unlocked!", show_alert=True)
        else:
            await callback_query.answer("This rarity is not locked!", show_alert=True)
        await drop_settings_command(client, callback_query.message)
    elif action.startswith("freq_"):
        rarity = action[5:]
        await callback_query.edit_message_text(
            f"Set drop frequency for {rarity}:\n\nSend the number of messages between drops.\nExample: 50"
        )
        # You may want to store the rarity in a temp dict for the next message

# --- Handler Registration ---
def register_drop_settings_handlers(app: Client):
    app.add_handler(filters.command("dropsettings"), drop_settings_command)
    app.add_handler(filters.command("lockrarity"), lock_rarity_command)
    app.add_handler(filters.command("unlockrarity"), unlock_rarity_command)
    app.add_handler(filters.command("setfrequency"), set_frequency_command)
    app.add_handler(filters.command("setdailylimit"), set_daily_limit_command)
    app.add_handler(filters.callback_query(lambda _, q: q.data.startswith("drop_") or q.data.startswith("lock_") or q.data.startswith("unlock_") or q.data.startswith("freq_")), drop_settings_callback)
