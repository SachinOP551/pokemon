import logging
from pyrogram import Client
from pyrogram.types import User, Chat, Message
from config import LOG_CHANNEL_ID
import datetime

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    return logging.getLogger(__name__)

DROPTIME_LOG_CHANNEL = -1002774565540 # New channel for droptime logs

async def send_drop_log(client: Client, admin_user: User, character: dict, chat: Chat):
    """Send log message when a character is dropped"""
    log_message = (
        f"<b>🎯 CHARACTER DROP LOG</b>\n\n"
        f"👤 Admin: {admin_user.first_name} (@{admin_user.username})\n"
        f"🆔 Admin ID: `{admin_user.id}`\n"
        f"📦 Character: {character['name']}\n"
        f"💎 Rarity: {character['rarity']}\n"
        f"🆔 Character ID: `{character['character_id']}`\n"
        f"📍 Dropped In: {chat.title}\n"
        f"🆔 Group ID: `{chat.id}`"
    )

    try:
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send drop log: {e}")

async def send_droptime_log(client: Client, admin_user: User, new_time: int, chat: Chat):
    """Send log message when droptime is set"""
    log_message = (
        f"⚠ ᴅʀᴏᴘᴛɪᴍᴇ sᴇᴛ ᴛᴏ {new_time} ʙʏ {admin_user.first_name} ɪɴ ɢʀᴏᴜᴘ {chat.id}"
    )

    try:
        # Send to main log channel
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send to main log channel: {e}")
    
    try:
        # Try to send to droptime log channel
        await client.send_message(
            chat_id=DROPTIME_LOG_CHANNEL,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send droptime log (channel may be invalid): {e}")
        # Don't crash the bot, just log the error

async def send_token_log(client: Client, admin_user: User, target_user: User, amount: int, action: str):
    """Send log message for token manipulation"""
    log_message = (
        f"<b>💰 TOKEN TRANSACTION LOG</b>\n\n"
        f"👤 Admin: {admin_user.first_name} (@{admin_user.username})\n"
        f"🆔 Admin ID: `{admin_user.id}`\n"
        f"👥 Target: {target_user.first_name} (@{target_user.username})\n"
        f"🆔 Target ID: `{target_user.id}`\n"
        f"💸 Action: {action}\n"
        f"💵 Amount: *{amount:,}* TOKENS"
    )

    try:
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send token log: {e}")

async def send_character_log(client: Client, admin_user: User, target_user: User, character: dict, action: str):
    """Send log message for character give/take"""
    log_message = (
        f"<b>👥 CHARACTER TRANSACTION LOG</b>\n\n"
        f"👤 Admin: {admin_user.first_name} (@{admin_user.username})\n"
        f"🆔 Admin ID: `{admin_user.id}`\n"
        f"📨 Target: {target_user.first_name} (@{target_user.username})\n"
        f"🆔 Target ID: `{target_user.id}`\n"
        f"👤 Character: {character['name']}\n"
        f"💎 Rarity: {character['rarity']}\n"
        f"🆔 Character ID: `{character['character_id']}`\n"
        f"💬 Action: {action}\n"
    )

    try:
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send character log: {e}")

async def send_redeem_log(client: Client, admin_user: User, code_type: str, code: str, max_claims: int, details: dict):
    """Send log message when a redeem code is created"""
    if code_type == 'character':
        log_message = (
            f"<b>🎯 CHARACTER REDEEM CODE CREATED!</b>\n\n"
            f"👤 Admin: {admin_user.first_name} (@{admin_user.username})\n"
            f"🆔 Admin ID: `{admin_user.id}`\n"
            f"🎨 Character: {details['name']}\n"
            f"💎 Rarity: {details['rarity']}\n"
            f"🆔 Character ID: `{details['character_id']}`\n"
            f"🔑 Code: `{code}`\n"
            f"📊 Max Claims: `{max_claims}`"
        )
    elif code_type == 'shard':
        log_message = (
            f"<b>🎐 SHARD REDEEM CODE CREATED!</b>\n\n"
            f"👤 Admin: {admin_user.first_name} (@{admin_user.username})\n"
            f"🆔 Admin ID: `{admin_user.id}`\n"
            f"🎐 Shards: `{details['shard_amount']}`\n"
            f"🔑 Code: `{code}`\n"
            f"📊 Max Claims: `{max_claims}`"
        )
    else:  # token
        log_message = (
            f"<b>💰 TOKEN REDEEM CODE CREATED!</b>\n\n"
            f"👤 Admin: {admin_user.first_name} (@{admin_user.username})\n"
            f"🆔 Admin ID: `{admin_user.id}`\n"
            f"💵 Tokens: `{details['token_amount']}`\n"
            f"🔑 Code: `{code}`\n"
            f"📊 Max Claims: `{max_claims}`"
        )

    try:
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send redeem log: {e}")

async def send_new_user_log(client: Client, user: User):
    """Send log message when a new user starts the bot"""
    print(f"[DEBUG] send_new_user_log called for user {user.id}")
    
    log_message = (
        f"👤 New User Started The Bot\n\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🪽First Name: {user.first_name}\n"
        f"💍 Username: {f'@{user.username}' if user.username else '`N/A`'}"
    )

    print(f"[DEBUG] Log message prepared: {log_message}")
    print(f"[DEBUG] Attempting to send to channel: {DROPTIME_LOG_CHANNEL}")

    try:
        await client.send_message(
            chat_id=DROPTIME_LOG_CHANNEL,
            text=log_message
        )
        print(f"[DEBUG] New user log sent successfully to channel {DROPTIME_LOG_CHANNEL}")
    except Exception as e:
        print(f"[ERROR] Failed to send new user log (channel may be invalid): {e}")
        # Don't crash the bot, just log the error

async def send_new_group_log(client: Client, chat: Chat, added_by: User):
    """Send log message when bot is added to a new group"""
    # Get member count safely
    member_count = 'N/A'
    try:
        member_count = await client.get_chat_members_count(chat.id)
    except Exception:
        pass

    log_message = (
        f"<b>🔰 Bot Added To New Group !! 🔰</b>\n\n"
        f"<b>📛 Group</b>: {chat.title}\n"
        f"<b>🆔 Group ID</b>: `{chat.id}`\n"
        f"<b>🔗 Group Username</b>: {f'@{chat.username}' if chat.username else '`N/A`'}\n\n"
        f"<b>👤 Added By</b>: {added_by.first_name} (@{added_by.username})\n"
        f"<b>📊 Members Count</b>: `{member_count}`"
    )

    try:
        await client.send_message(
            chat_id=DROPTIME_LOG_CHANNEL,
            text=log_message
        )
    except Exception as e:
        print(f"Failed to send new group log (channel may be invalid): {e}")
        # Don't crash the bot, just log the error

async def send_admin_log(client: Client, admin: User, action: str, target: str = None, extra: str = None):
    """Send a log message to the admin log channel."""
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    admin_info = f"👮‍♂️ <b>Admin:</b> {admin.mention if hasattr(admin, 'mention') else admin.first_name} (@{admin.username}) (<code>{admin.id}</code>)"
    action_info = f"⚡ <b>Action:</b> {action}"
    target_info = f"🎯 <b>Target:</b> {target}" if target else ""
    extra_info = f"📝 <b>Extra:</b> {extra}" if extra else ""
    log_message = f"<b>[ADMIN LOG]</b>\n🕒 <b>Time:</b> {time_str}\n{admin_info}\n{action_info}"
    if target_info:
        log_message += f"\n{target_info}"
    if extra_info:
        log_message += f"\n{extra_info}"
    try:
        try:
            await client.get_chat(LOG_CHANNEL_ID)
        except Exception as meet_err:
            print(f"Could not get admin log chat before send: {meet_err}")
        await client.send_message(LOG_CHANNEL_ID, log_message)
    except Exception as e:
        print(f"Failed to send admin log: {e}")

async def send_character_admin_log(client: Client, admin_user, action: str, character: dict):
    """Send a log message to the droptime log channel for character add/edit/delete/reset."""
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = (
        f"<b>[CHARACTER LOG]</b>\n🕒 <b>Time:</b> {time_str}\n"
        f"👮‍♂️ <b>Admin:</b> {admin_user.mention if hasattr(admin_user, 'mention') else admin_user.first_name} (@{admin_user.username}) (<code>{admin_user.id}</code>)\n"
        f"⚡ <b>Action:</b> {action}\n"
        f"👤 <b>Name:</b> {character.get('name', '-') }\n"
        f"💎 <b>Rarity:</b> {character.get('rarity', '-') }\n"
        f"🆔 <b>ID:</b> <code>{character.get('character_id', character.get('_id', '-'))}</code>"
    )
    try:
        await client.send_message(DROPTIME_LOG_CHANNEL, log_message)
    except Exception as e:
        print(f"Failed to send character admin log (channel may be invalid): {e}")
        # Don't crash the bot, just log the error
