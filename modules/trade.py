from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import os

# Import database based on configuration
from modules.postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
from .decorators import check_banned
import asyncio

# --- ActionManager remains as a class for now (used by both gift and trade) ---
class ActionManager:
    def __init__(self):
        self.active_actions = {}
    async def is_user_busy(self, db, user_id):
        user_data = await db.get_user(user_id)
        return bool(user_data and user_data.get('active_action'))
    async def get_user_action(self, db, user_id):
        user_data = await db.get_user(user_id)
        active_action = user_data.get('active_action') if user_data else None
        # Defensive: handle legacy/invalid types
        if isinstance(active_action, dict):
            action_type = active_action.get('type')
            return action_type
        # If it's a string (bad state), treat as no action
        return None
    async def set_user_action(self, db, user_id, action_type, data):
        action_data = {
            'type': action_type,
            'data': data,
            'timestamp': datetime.now().timestamp()
        }
        await db.update_user(user_id, {'active_action': action_data})
        self.active_actions[user_id] = action_data
    async def clear_user_action(self, db, user_id):
        await db.update_user(user_id, {'active_action': None})
        self.active_actions.pop(user_id, None)
    def get_action_message(self, action_type):
        messages = {
            'gift': "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ɢɪғᴛ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.",
            'trade': "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴛʀᴀᴅᴇ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.",
            'sell': "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ sᴇʟʟ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.",
            'fusion': "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ғᴜsɪᴏɴ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.",
            'massgift': "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴍᴀssɢɪғᴛ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.",
            'masssell': "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴍᴀsssᴇʟʟ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ."
        }
        return messages.get(action_type, "ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴀᴄᴛɪᴏɴ! ᴘʟᴇᴀsᴇ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.")

# Global action manager instance
action_manager = ActionManager()
# Module-level storage for active gifts
_active_gifts = {}
# Module-level storage for active trades
_active_trades = {}
# Session storage for massgift confirmation
_massgift_temp = {}
# Processing flags to prevent spam clicks
_processing_massgifts = set()
# Async locks for gift confirmations
_gift_locks = {}

@check_banned
async def gift_command(client: Client, message: Message):
    db = get_database()
    user = message.from_user
    # Check if user has any active action
    if await action_manager.is_user_busy(db, user.id):
        action_type = await action_manager.get_user_action(db, user.id)
        if isinstance(action_type, str) and action_type:
            user_data = await db.get_user(user.id)
            active_action = user_data.get('active_action') if user_data else None
            action_data = active_action['data'] if isinstance(active_action, dict) else {}
            keyboard = [[InlineKeyboardButton("❌ Cancel Action", callback_data=f"cancel_{action_type}_{action_data.get('gift_id', action_data.get('trade_id', '') )}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                f"<b>❌ {action_manager.get_action_message(action_type)}</b>",
                reply_markup=reply_markup
            )
            return
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply_text(
            "<b>🎁 Usᴀɢᴇ:</b> <code>/gift &lt;character_id&gt;</code>\n<b>ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ɢɪғᴛ ᴛᴏ!</b>"
        )
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ!</b>"
        )
        return
    try:
        char_id = int(args[1])
    except ValueError:
        await message.reply_text(
            "<b>❌ ɪɴᴠᴀʟɪᴅ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ!</b>"
        )
        return
    target_user = message.reply_to_message.from_user
    # Check if target user is busy in any action
    if await action_manager.is_user_busy(db, target_user.id):
        target_action_type = await action_manager.get_user_action(db, target_user.id)
        await message.reply_text(
            f"<b>❌ The user you are trying to gift is already busy in {target_action_type}. Ask them to cancel it first.</b>"
        )
        return
    if target_user.is_bot:
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ɢɪғᴛ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴛᴏ ʙᴏᴛs!</b>"
        )
        return
    if target_user.id == user.id:
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ɢɪғᴛ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴛᴏ ʏᴏᴜʀsᴇʟғ!</b>"
        )
        return
    character = await db.get_character(char_id)
    if not character:
        await message.reply_text(
            "<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!</b>"
        )
        return
    user_data = await db.get_user(user.id)
    if not user_data or char_id not in user_data.get('characters', []):
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ!</b>"
        )
        return
    timestamp = int(datetime.now().timestamp())
    gift_id = f"gift_{user.id}_{target_user.id}_{timestamp}"
    _active_gifts[user.id] = {
        'gift_id': gift_id,
        'from_user': user,
        'to_user': target_user,
        'character': character,
        'timestamp': timestamp
    }
    callback_gift_id = f"{user.id}_{target_user.id}_{timestamp}"
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"gift_confirm_{callback_gift_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"gift_cancel_{callback_gift_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    rarity = character['rarity']
    rarity_emoji = get_rarity_emoji(rarity)
    await message.reply_text(
        f"<b>❓ ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ɢɪғᴛ:</b>\n\n"
        f"<b>🎁 ᴛᴏ:</b> {target_user.mention}\n"
        f"<b>👤 ᴄʜᴀʀᴀᴄᴛᴇʀ:</b> {character['name']}\n"
        f"<b>{rarity_emoji} ʀᴀʀɪᴛʏ:</b> {rarity}\n"
        f"<b>🆔:</b> <code>{character['character_id']}</code>",
        reply_markup=reply_markup
    )
    await action_manager.set_user_action(db, user.id, 'gift', {
        'gift_id': gift_id,
        'target_id': target_user.id
    })

async def handle_gift_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user = callback_query.from_user
    parts = callback_query.data.split('_')
    if len(parts) < 3:
        await callback_query.answer("Invalid callback data!", show_alert=True)
        return
    action = parts[1]
    gift_id = '_'.join(parts[2:])
    gift_found = None
    gift_owner_id = None
    for uid, gift in _active_gifts.items():
        if gift['gift_id'] == f"gift_{gift_id}":
            gift_found = gift
            gift_owner_id = uid
            break
    if not gift_found:
        await callback_query.answer("Gift not found or expired!", show_alert=True)
        return
    # Prevent double processing (race condition safe)
    lock = _gift_locks.setdefault(gift_found['gift_id'], asyncio.Lock())
    async with lock:
        if gift_found.get('completed'):
            await callback_query.answer("This gift has already been processed.", show_alert=True)
            return
        if user.id != gift_found['from_user'].id:
            await callback_query.answer("Only the gift sender can confirm/cancel!", show_alert=True)
            return
        await callback_query.answer()
        if action == "confirm":
            try:
                # Mark as completed immediately to prevent double processing
                gift_found['completed'] = True
                target_data = await db.get_user(gift_found['to_user'].id)
                if not target_data:
                    await db.add_user({
                        'user_id': gift_found['to_user'].id,
                        'username': gift_found['to_user'].username,
                        'first_name': gift_found['to_user'].first_name,
                        'coins': 0,
                        'wallet': 0,
                        'bank': 0,
                        'characters': [],
                        'last_daily': None,
                        'last_weekly': None,
                        'last_monthly': None,
                        'sudo': False,
                        'og': False,
                        'collection_preferences': {
                            'mode': 'default',
                            'filter': None
                        }
                    })
                await db.remove_single_character_from_user(
                    gift_found['from_user'].id,
                    gift_found['character']['character_id']
                )
                await db.add_character_to_user(
                    gift_found['to_user'].id,
                    gift_found['character']['character_id'],
                    source='gift'
                )
                # Log transaction for sender
                await db.log_user_transaction(gift_found['from_user'].id, "gift_sent", {
                    "to_user_id": gift_found['to_user'].id,
                    "to_user_name": gift_found['to_user'].first_name,
                    "character_id": gift_found['character']['character_id'],
                    "name": gift_found['character']['name'],
                    "rarity": gift_found['character']['rarity'],
                    "date": datetime.now().strftime('%Y-%m-%d')
                })
                # Log transaction for recipient
                await db.log_user_transaction(gift_found['to_user'].id, "gift_received", {
                    "from_user_id": gift_found['from_user'].id,
                    "from_user_name": gift_found['from_user'].first_name,
                    "character_id": gift_found['character']['character_id'],
                    "name": gift_found['character']['name'],
                    "rarity": gift_found['character']['rarity'],
                    "date": datetime.now().strftime('%Y-%m-%d')
                })
                # Ensure group membership is tracked for recipient
                if callback_query.message.chat.type != "private":
                    await db.add_user_to_group(gift_found['to_user'].id, callback_query.message.chat.id)
                rarity = gift_found['character']['rarity']
                rarity_emoji = get_rarity_emoji(rarity)
                await callback_query.edit_message_text(
                    f"<b>✅ ɢɪғᴛ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                    f"<b>🎁 {gift_found['from_user'].mention}</b> ɢᴀᴠᴇ <b>{gift_found['character']['name']}</b> <b>{rarity_emoji}</b> ᴛᴏ <b>{gift_found['to_user'].mention}</b>!",
                    reply_markup=None
                )
                await action_manager.clear_user_action(db, user.id)
            except Exception as e:
                print(f"Gift error: {e}")
                await callback_query.edit_message_text(
                    "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇssɪɴɢ ᴛʜᴇ ɢɪғᴛ!</b>",
                    reply_markup=None
                )
        elif action == "cancel":
            # Mark as completed to prevent further actions
            gift_found['completed'] = True
            await callback_query.edit_message_text(
                "<b>❌ ɢɪғᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ!</b>",
                reply_markup=None
            )
            await action_manager.clear_user_action(db, user.id)
        if gift_owner_id:
            _active_gifts.pop(gift_owner_id, None)
        # Clean up lock
        _gift_locks.pop(gift_found['gift_id'], None)

@check_banned
async def trade_command(client: Client, message: Message):
    db = get_database()
    user = message.from_user
    # Check if user has any active action
    if await action_manager.is_user_busy(db, user.id):
        action_type = await action_manager.get_user_action(db, user.id)
        if isinstance(action_type, str) and action_type:
            user_data = await db.get_user(user.id)
            active_action = user_data.get('active_action') if user_data else None
            action_data = active_action['data'] if isinstance(active_action, dict) else {}
            keyboard = [[InlineKeyboardButton("❌ Cancel Action", callback_data=f"cancel_{action_type}_{action_data.get('gift_id', action_data.get('trade_id', '') )}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                f"<b>❌ {action_manager.get_action_message(action_type)}</b>",
                reply_markup=reply_markup
            )
            return
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply_text(
            "<b>🔄 Usᴀɢᴇ:</b> <code>/trade Your_Character_ID User's_Character_ID</code>\n<b>ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛʀᴀᴅᴇ ᴡɪᴛʜ!</b>"
        )
        return
    args = message.text.split()
    if len(args) != 3:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ʙᴏᴛʜ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅs!</b>"
        )
        return
    try:
        your_char_id = int(args[1])
        their_char_id = int(args[2])
    except ValueError:
        await message.reply_text(
            "<b>❌ ɪɴᴠᴀʟɪᴅ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅs!</b>"
        )
        return
    target_user = message.reply_to_message.from_user
    # Check if target user is busy in any action
    if await action_manager.is_user_busy(db, target_user.id):
        target_action_type = await action_manager.get_user_action(db, target_user.id)
        await message.reply_text(
            f"<b>❌ The user you are trying to trade with is already busy in {target_action_type}. Ask them to cancel it first.</b>"
        )
        return
    if target_user.is_bot:
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴛʀᴀᴅᴇ ᴡɪᴛʜ ʙᴏᴛs!</b>"
        )
        return
    if target_user.id == user.id:
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴛʀᴀᴅᴇ ᴡɪᴛʜ ʏᴏᴜʀsᴇʟғ!</b>"
        )
        return
    your_char = await db.get_character(your_char_id)
    their_char = await db.get_character(their_char_id)
    if not your_char or not their_char:
        await message.reply_text(
            "<b>❌ ᴏɴᴇ ᴏʀ ʙᴏᴛʜ ᴄʜᴀʀᴀᴄᴛᴇʀs ɴᴏᴛ ғᴏᴜɴᴅ!</b>"
        )
        return
    user_data = await db.get_user(user.id)
    target_data = await db.get_user(target_user.id)
    if not user_data or your_char_id not in user_data.get('characters', []):
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ!</b>"
        )
        return
    if not target_data or their_char_id not in target_data.get('characters', []):
        await message.reply_text(
            "<b>❌ ᴛʜᴇ ᴏᴛʜᴇʀ ᴜsᴇʀ ᴅᴏᴇsɴ'ᴛ ᴏᴡɴ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ!</b>"
        )
        return
    timestamp = int(datetime.now().timestamp())
    trade_id = f"trade_{user.id}_{target_user.id}_{timestamp}"
    _active_trades[trade_id] = {
        'from_user': user,
        'to_user': target_user,
        'from_char': your_char,
        'to_char': their_char,
        'timestamp': timestamp
    }
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"trade_confirm_{trade_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"trade_cancel_{trade_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    from_rarity = your_char['rarity']
    to_rarity = their_char['rarity']
    from_rarity_emoji = get_rarity_emoji(from_rarity)
    to_rarity_emoji = get_rarity_emoji(to_rarity)
    message_text = (
        f"<b>🔄 {user.mention} ᴡᴀɴᴛs ᴛᴏ ᴛʀᴀᴅᴇ:</b>\n\n"
        f"<b>ɴᴀᴍᴇ:</b> {your_char['name']}\n"
        f"<b>{from_rarity_emoji}:</b> {from_rarity}\n\n"
        f"<b>ᴡɪᴛʜ • {target_user.mention}:</b>\n\n"
        f"<b>ɴᴀᴍᴇ:</b> {their_char['name']}\n"
        f"<b>{to_rarity_emoji}:</b> {to_rarity}\n\n"
        "<b>ᴄᴏɴғɪʀᴍ ᴏʀ ᴄᴀɴᴄᴇʟ ᴛʜᴇ ᴛʀᴀᴅᴇs ᴜsɪɴɢ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ɢɪᴠᴇɴ ʙᴇʟᴏᴡ</b>"
    )
    await message.reply_text(
        message_text,
        reply_markup=reply_markup
    )
    await action_manager.set_user_action(db, user.id, 'trade', {
        'trade_id': trade_id,
        'target_id': target_user.id
    })

async def handle_trade_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user = callback_query.from_user
    parts = callback_query.data.split('_')
    if len(parts) < 3:
        await callback_query.answer("Invalid callback data!", show_alert=True)
        return
    action = parts[1]
    trade_id = '_'.join(parts[2:])
    trade = _active_trades.get(trade_id)
    if not trade:
        await callback_query.answer("Trade not found or expired!", show_alert=True)
        return
    if user.id != trade['to_user'].id:
        await callback_query.answer("Only the trade target can confirm/cancel!", show_alert=True)
        return
    await callback_query.answer()
    if action == "confirm":
        try:
            await db.remove_single_character_from_user(
                trade['from_user'].id,
                trade['from_char']['character_id']
            )
            await db.remove_single_character_from_user(
                trade['to_user'].id,
                trade['to_char']['character_id']
            )
            await db.add_character_to_user(
                trade['to_user'].id,
                trade['from_char']['character_id']
            )
            await db.add_character_to_user(
                trade['from_user'].id,
                trade['to_char']['character_id']
            )
            # Log transaction for both users
            now_str = datetime.now().strftime('%Y-%m-%d')
            await db.log_user_transaction(trade['from_user'].id, "trade_sent", {
                "to_user_id": trade['to_user'].id,
                "to_user_name": trade['to_user'].first_name,
                "sent_character_id": trade['from_char']['character_id'],
                "sent_name": trade['from_char']['name'],
                "sent_rarity": trade['from_char']['rarity'],
                "received_character_id": trade['to_char']['character_id'],
                "received_name": trade['to_char']['name'],
                "received_rarity": trade['to_char']['rarity'],
                "date": now_str
            })
            await db.log_user_transaction(trade['to_user'].id, "trade_received", {
                "from_user_id": trade['from_user'].id,
                "from_user_name": trade['from_user'].first_name,
                "sent_character_id": trade['to_char']['character_id'],
                "sent_name": trade['to_char']['name'],
                "sent_rarity": trade['to_char']['rarity'],
                "received_character_id": trade['from_char']['character_id'],
                "received_name": trade['from_char']['name'],
                "received_rarity": trade['from_char']['rarity'],
                "date": now_str
            })
            # Ensure group membership is tracked for both users
            if callback_query.message.chat.type != "private":
                await db.add_user_to_group(trade['from_user'].id, callback_query.message.chat.id)
                await db.add_user_to_group(trade['to_user'].id, callback_query.message.chat.id)
            from_rarity = trade['from_char']['rarity']
            to_rarity = trade['to_char']['rarity']
            from_rarity_emoji = get_rarity_emoji(from_rarity)
            to_rarity_emoji = get_rarity_emoji(to_rarity)
            await callback_query.edit_message_text(
                f"<b>✅ ᴛʀᴀᴅᴇ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                f"<b>{trade['from_user'].mention}</b> ᴛʀᴀᴅᴇᴅ <b>{trade['from_char']['name']}</b> <b>{from_rarity_emoji}</b> ᴡɪᴛʜ <b>{trade['to_user'].mention}</b>'s <b>{trade['to_char']['name']}</b> <b>{to_rarity_emoji}</b>!",
                reply_markup=None
            )
            await action_manager.clear_user_action(db, trade['from_user'].id)
        except Exception as e:
            print(f"Trade error: {e}")
            await callback_query.edit_message_text(
                "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇssɪɴɢ ᴛʜᴇ ᴛʀᴀᴅᴇ!</b>",
                reply_markup=None
            )
    elif action == "cancel":
        await callback_query.edit_message_text(
            "<b>❌ ᴛʀᴀᴅᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ!</b>",
            reply_markup=None
        )
        await action_manager.clear_user_action(db, trade['from_user'].id)
    _active_trades.pop(trade_id, None)

async def handle_cancel_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user = callback_query.from_user
    parts = callback_query.data.split('_')
    if len(parts) < 3:
        await callback_query.answer("Invalid callback data!", show_alert=True)
        return
    action_type = parts[1]
    action_id = '_'.join(parts[2:])
    user_data = await db.get_user(user.id)
    active_action = user_data.get('active_action') if user_data else None
    # If no active_action or not a dict, just clear and succeed
    if not active_action or not isinstance(active_action, dict):
        await action_manager.clear_user_action(db, user.id)
        await callback_query.edit_message_text(
            f"<b>✅ Action cancelled!</b>",
            reply_markup=None
        )
        await callback_query.answer("Action cancelled successfully!")
        return

    # Always allow cancellation, but warn if type doesn't match
    if active_action.get('type') != action_type:
        await callback_query.answer("Warning: Cancelling a different action type.", show_alert=True)

    # Clear all possible session data for this user
    try:
        from modules.sell import _temp_data, _masssell_temp
    except ImportError:
        _temp_data = {}
        _masssell_temp = {}
    _temp_data.pop(user.id, None)
    _masssell_temp.pop(user.id, None)
    _active_gifts.pop(user.id, None)
    _massgift_temp.pop(user.id, None)  # Clear massgift session data
    # Remove from _active_trades if present
    for k in list(_active_trades.keys()):
        if k.startswith(f"trade_{user.id}_") or k.startswith(f"trade_{user.id}"):
            _active_trades.pop(k, None)

    await action_manager.clear_user_action(db, user.id)
    await callback_query.edit_message_text(
        f"<b>✅ Action cancelled!</b>",
        reply_markup=None
    )
    await callback_query.answer("Action cancelled successfully!")

@check_banned
async def massgift_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    # Clear any masssell session for this user
    try:
        from modules.sell import _masssell_temp
        if user_id in _masssell_temp:
            del _masssell_temp[user_id]
    except ImportError:
        pass
    # Must be a reply
    if not message.reply_to_message:
        await message.reply_text("❌ Please reply to the user you want to gift to!")
        return
    target_user = message.reply_to_message.from_user
    if user_id == target_user.id:
        await message.reply_text("❌ You can't massgift to yourself!")
        return
    if await action_manager.is_user_busy(db, user_id):
        action_type = await action_manager.get_user_action(db, user_id)
        await message.reply_text(f"❌ {action_manager.get_action_message(action_type)}")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ Please provide character IDs!\nUsage: /massgift <id1> <id2> ... (up to 998)")
        return
    try:
        char_ids = [int(x) for x in args[1:999]]  # Limit to 998
    except ValueError:
        await message.reply_text("❌ Please provide valid character IDs!")
        return
    user_data = await db.get_user(user_id)
    owned_characters = user_data.get('characters', []) if user_data else []
    from collections import Counter
    owned_counts = Counter(owned_characters)
    requested_counts = Counter(char_ids)

    # --- NEW LOGIC: Check for missing characters ---
    missing = [str(cid) for cid in requested_counts if owned_counts.get(cid, 0) == 0]
    if missing:
        await message.reply_text(f"❌ Missing Characters {', '.join(missing)}")
        return

    # Only check for insufficient counts if all are present
    insufficient = [(str(cid), req_count) for cid, req_count in requested_counts.items() if owned_counts.get(cid, 0) < req_count]
    if insufficient:
        msg = "⚠️ Insufficient counts for: " + ", ".join(f"{cid} (needs {req_count})" for cid, req_count in insufficient)
        await message.reply_text(msg)
        return
    # Only keep character IDs the user owns, up to the number they own
    char_ids_to_gift = []
    temp_counts = Counter()
    for cid in char_ids:
        if owned_counts[cid] > temp_counts[cid]:
            char_ids_to_gift.append(cid)
            temp_counts[cid] += 1
    if not char_ids_to_gift:
        await message.reply_text("❌ None of these characters are valid or owned by you!")
        return
    # Batch fetch all character documents
    char_docs = []
    for char_id in char_ids_to_gift:
        char = await db.get_character(char_id)
        if char:
            char_docs.append(char)
    id_to_char = {c['character_id']: c for c in char_docs}
    char_counts = Counter(char_ids_to_gift)
    summary_lines = []
    for cid, count in char_counts.items():
        char = id_to_char.get(cid)
        if not char:
            continue
        emoji = get_rarity_emoji(char['rarity'])
        summary_lines.append(f"🌙 {count}x {char['name']} [{emoji}]")
    if not summary_lines:
        await message.reply_text("❌ None of these characters are valid or owned by you!")
        return
    # Store id_to_char in _massgift_temp for use in callback
    _massgift_temp[user_id] = {
        'char_ids': char_ids_to_gift,
        'lines': summary_lines,
        'target_id': target_user.id,
        'target_name': target_user.mention,
        'id_to_char': id_to_char
    }
    await action_manager.set_user_action(db, user_id, 'massgift', {'char_ids': char_ids_to_gift, 'target_id': target_user.id})
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Gift", callback_data="massgift_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="massgift_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"<b>ℹ️ Are you sure you want to gift these characters to {target_user.mention}?</b>\n\n"
    msg += '\n\n'.join(summary_lines)
    msg += f"\n\n<b>Recipient:</b> {target_user.mention}\n\nAre you sure you want to gift these Characters?"
    await message.reply_text(msg, reply_markup=reply_markup)

@check_banned
async def handle_massgift_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    db = get_database()
    
    # Get or create lock for this user
    if user_id not in _gift_locks:
        _gift_locks[user_id] = asyncio.Lock()
    lock = _gift_locks[user_id]
    
    # Always clear both massgift and masssell session data for this user after confirm/cancel
    def clear_all_mass_sessions():
        if user_id in _massgift_temp:
            del _massgift_temp[user_id]
        try:
            from modules.sell import _masssell_temp
            if user_id in _masssell_temp:
                del _masssell_temp[user_id]
        except ImportError:
            pass
    
    if callback_query.data == "massgift_confirm":
        # Set processing flag IMMEDIATELY to prevent spam clicks
        if user_id in _processing_massgifts:
            await callback_query.answer("Please wait, your massgift is being processed...", show_alert=True)
            return
        _processing_massgifts.add(user_id)
        
        try:
            # Check if user data exists in massgift_temp
            if user_id not in _massgift_temp:
                await callback_query.edit_message_text("❌ Session expired! Please try again!")
                clear_all_mass_sessions()
                await action_manager.clear_user_action(db, user_id)
                _processing_massgifts.discard(user_id)  # Clean up processing flag
                return
            
            async with lock:
                try:
                    # Re-fetch user data inside the lock to ensure we have the latest state
                    user_data = await db.get_user(user_id)
                    active_action = user_data.get('active_action', {}) if user_data else {}
                    
                    # Check if massgift session is still valid
                    if user_id not in _massgift_temp:
                        await callback_query.edit_message_text("❌ Session expired! Please try again!")
                        clear_all_mass_sessions()
                        await action_manager.clear_user_action(db, user_id)
                        # Clean up lock and processing flag
                        if user_id in _gift_locks:
                            del _gift_locks[user_id]
                        _processing_massgifts.discard(user_id)
                        return
                    
                    # Check if already completed
                    if _massgift_temp[user_id].get('completed'):
                        await callback_query.answer("This mass gift has already been processed.", show_alert=True)
                        _processing_massgifts.discard(user_id)
                        return
                    
                    # More lenient validation - if we have massgift_temp data, allow the action
                    # Only block if there's a completely different action type
                    if isinstance(active_action, dict) and active_action.get('type') and active_action.get('type') not in ['massgift', None]:
                        await callback_query.edit_message_text("❌ This massgift session is no longer valid (another action was started or confirmed).", disable_web_page_preview=True)
                        clear_all_mass_sessions()
                        await action_manager.clear_user_action(db, user_id)
                        # Clean up lock and processing flag
                        if user_id in _gift_locks:
                            del _gift_locks[user_id]
                        _processing_massgifts.discard(user_id)
                        return
                    try:
                        data = _massgift_temp[user_id]
                        target_id = data['target_id']
                        char_ids = data['char_ids']
                        id_to_char = data.get('id_to_char', {})
                        # Remove from sender
                        user_data = await db.get_user(user_id)
                        owned_chars = user_data.get('characters', []) if user_data else []
                        new_chars = owned_chars.copy()
                        for cid in char_ids:
                            if cid in new_chars:
                                new_chars.remove(cid)
                        # Add to recipient
                        now = datetime.now()
                        collection_history = [{
                            'character_id': cid,
                            'collected_at': now,
                            'source': 'gift'
                        } for cid in char_ids]
                        # Remove characters from sender
                        await db.update_user(user_id, {'characters': new_chars})
                        
                        # Add characters to recipient
                        target_data = await db.get_user(target_id)
                        if target_data:
                            target_chars = target_data.get('characters', []) + char_ids
                            target_history = target_data.get('collection_history', []) + collection_history
                            await db.update_user(target_id, {
                                'characters': target_chars,
                                'collection_history': target_history
                            })
                        else:
                            # Create new user if doesn't exist
                            await db.add_user({
                                'user_id': target_id,
                                'username': None,
                                'first_name': None,
                                'coins': 0,
                                'wallet': 0,
                                'bank': 0,
                                'characters': char_ids,
                                'collection_history': collection_history,
                                'last_daily': None,
                                'last_weekly': None,
                                'last_monthly': None,
                                'sudo': False,
                                'og': False,
                                'collection_preferences': {
                                    'mode': 'default',
                                    'filter': None
                                }
                            })
                        # Log transaction for sender
                        await db.log_user_transaction(user_id, "gift_sent", {
                            "to_user_id": target_id,
                            "to_user_name": data['target_name'],
                            "character_id": char_ids[0],
                            "name": id_to_char.get(char_ids[0], {}).get('name', '?'),
                            "rarity": id_to_char.get(char_ids[0], {}).get('rarity', '?'),
                            "date": now.strftime('%Y-%m-%d')
                        })
                        # Log transaction for recipient
                        await db.log_user_transaction(target_id, "gift_received", {
                            "from_user_id": user_id,
                            "from_user_name": data['target_name'],
                            "character_id": char_ids[0],
                            "name": id_to_char.get(char_ids[0], {}).get('name', '?'),
                            "rarity": id_to_char.get(char_ids[0], {}).get('rarity', '?'),
                            "date": now.strftime('%Y-%m-%d')
                        })
                        # Ensure group membership is tracked for recipient
                        if callback_query.message.chat.type != "private":
                            await db.add_user_to_group(target_id, callback_query.message.chat.id)
                        await callback_query.edit_message_text(f"✅ Successfully gifted {len(char_ids)} characters to <a href='tg://user?id={target_id}'>{data['target_name']}</a>!", disable_web_page_preview=True)
                        await action_manager.clear_user_action(db, user_id)
                        _massgift_temp[user_id]['completed'] = True
                        clear_all_mass_sessions()
                        # Clean up lock and processing flag
                        if user_id in _gift_locks:
                            del _gift_locks[user_id]
                        _processing_massgifts.discard(user_id)
                    except Exception as e:
                        print(f"Error in massgift confirmation for user {user_id}: {e}")
                        import traceback
                        print(f"Full traceback: {traceback.format_exc()}")
                        await callback_query.edit_message_text("❌ An error occurred while mass gifting!")
                        await action_manager.clear_user_action(db, user_id)
                        clear_all_mass_sessions()
                        # Clean up lock and processing flag
                        if user_id in _gift_locks:
                            del _gift_locks[user_id]
                        _processing_massgifts.discard(user_id)
                except Exception as e:
                    print(f"Error in massgift confirmation for user {user_id}: {e}")
                    import traceback
                    print(f"Full traceback: {traceback.format_exc()}")
                    await callback_query.edit_message_text("❌ An error occurred while mass gifting!")
                    await action_manager.clear_user_action(db, user_id)
                    clear_all_mass_sessions()
                    # Clean up lock and processing flag
                    if user_id in _gift_locks:
                        del _gift_locks[user_id]
                    _processing_massgifts.discard(user_id)
        except Exception as e:
            print(f"Error in massgift confirmation for user {user_id}: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            await callback_query.edit_message_text("❌ An error occurred while mass gifting!")
            await action_manager.clear_user_action(db, user_id)
            clear_all_mass_sessions()
            # Clean up processing flag
            _processing_massgifts.discard(user_id)
    
    elif callback_query.data == "massgift_cancel":
        async with lock:
            await callback_query.edit_message_text("❌ Mass gift cancelled!")
            await action_manager.clear_user_action(db, user_id)
            clear_all_mass_sessions()
            # Clean up lock
            if user_id in _gift_locks:
                del _gift_locks[user_id]

def setup_gift_handlers(app: Client):
    app.add_handler(filters.command("gift")(gift_command))
    app.add_handler(filters.callback_query(lambda _, __, query: query.data and query.data.startswith("gift_"))(handle_gift_callback))

def setup_trade_handlers(app: Client):
    app.add_handler(filters.command("trade")(trade_command))
    app.add_handler(filters.callback_query(lambda _, __, query: query.data and query.data.startswith("trade_"))(handle_trade_callback))
    app.add_handler(filters.callback_query(lambda _, __, query: query.data and query.data.startswith("cancel_") and query.data.count("_") >= 2)(handle_cancel_callback))

def setup_massgift_handlers(app: Client):
    @app.on_message(filters.command("massgift", prefixes=["/", ".", "!"]))
    async def massgift_handler(client: Client, message: Message):
        await massgift_command(client, message)

    @app.on_callback_query(filters.regex(r"^massgift_"))
    async def massgift_callback_handler(client: Client, callback_query: CallbackQuery):
        await handle_massgift_callback(client, callback_query)