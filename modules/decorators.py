from functools import wraps
from pyrogram import Client
from pyrogram.types import Message, CallbackQuery
from config import OWNER_ID
from datetime import datetime, timezone
from .postgres_database import get_database
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

__all__ = [
    'owner_only',
    'admin_only',
    'is_owner',
    'is_og',
    'is_sudo',
    'is_admin',
    'check_banned',
    'user_not_banned',
    'ignore_old_messages',
    'auto_register_user',
    'require_membership'
]

def owner_only(func):
    """Decorator to restrict function to owner only"""
    @wraps(func)
    async def wrapped(client: Client, message: Message, *args, **kwargs):
        try:
            user_id = message.from_user.id
            if not is_owner(user_id):
                return
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            # Log the error but don't crash the bot
            print(f"Error in owner_only decorator for function {func.__name__}: {e}")
            try:
                # Try to send a generic error message
                await message.reply_text("❌ An error occurred while processing your request. Please try again later.")
            except:
                # If even the error message fails, just log it
                print(f"Failed to send error message for {func.__name__}")
    return wrapped

def admin_only(func):
    """Decorator to restrict function to admins only"""
    @wraps(func)
    async def wrapped(client: Client, message: Message, *args, **kwargs):
        try:
            user_id = message.from_user.id
            try:
                db = get_database()
                
                # Check if user is admin (owner, sudo, or og)
                if not (is_owner(user_id) or await is_sudo(db, user_id) or await is_og(db, user_id)):
                    return
            except Exception as db_error:
                # If database is not initialized, just continue
                print(f"Database not ready for admin check: {db_error}")
                # Allow the command to proceed if database is not ready
            
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            # Log the error but don't crash the bot
            print(f"Error in admin_only decorator for function {func.__name__}: {e}")
            try:
                # Try to send a generic error message
                await message.reply_text("❌ An error occurred while processing your request. Please try again later.")
            except:
                # If even the error message fails, just log it
                print(f"Failed to send error message for {func.__name__}")
    return wrapped

def is_owner(user_id: int) -> bool:
    """Check if user is the owner"""
    if isinstance(OWNER_ID, list):
        return user_id in OWNER_ID
    return user_id == OWNER_ID

async def is_og(db, user_id: int) -> bool:
    """Check if user is an OG"""
    user_data = await db.get_user(user_id)
    return user_data and user_data.get('og', False)

async def is_sudo(db, user_id: int) -> bool:
    """Check if user is a sudo admin"""
    user_data = await db.get_user(user_id)
    return user_data and user_data.get('sudo', False)

async def is_admin(db, user_id: int) -> bool:
    """Check if user is any type of admin (owner, OG, sudo)"""
    if isinstance(OWNER_ID, list):
        if user_id in OWNER_ID:
            return True
    elif user_id == OWNER_ID:
        return True
    user_data = await db.get_user(user_id)
    return user_data and (user_data.get('og', False) or user_data.get('sudo', False))

async def check_banned(db, user_id: int) -> bool:
    """Check if user is banned from the bot (temporary or permanent)"""
    from .ban_manager import check_user_ban_status
    is_banned, _ = await check_user_ban_status(user_id, db)
    return is_banned

def user_not_banned(func):
    """Decorator to check if user is not banned"""
    @wraps(func)
    async def wrapped(client: Client, message: Message, *args, **kwargs):
        try:
            user_id = message.from_user.id
            try:
                db = get_database()
                
                # Always allow admins
                if await is_admin(db, user_id):
                    return await func(client, message, *args, **kwargs)
                
                # Check if user is banned
                if await check_banned(db, user_id):
                    await message.reply_text(
                        "*❌ ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ғʀᴏᴍ ᴜsɪɴɢ ᴛʜɪs ʙᴏᴛ\\!*",
                        parse_mode="markdown"
                    )
                    return
            except Exception as db_error:
                # If database is not initialized, just continue
                print(f"Database not ready for ban check: {db_error}")
                # Allow the command to proceed if database is not ready
            
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            # Log the error but don't crash the bot
            print(f"Error in user_not_banned decorator for function {func.__name__}: {e}")
            try:
                # Try to send a generic error message
                await message.reply_text("❌ An error occurred while processing your request. Please try again later.")
            except:
                # If even the error message fails, just log it
                print(f"Failed to send error message for {func.__name__}")
    return wrapped

def check_banned(func):
    """Decorator to check if user is banned before executing function"""
    @wraps(func)
    async def wrapper(client: Client, message_or_callback, *args, **kwargs):
        try:
            # Get user from either message or callback query
            if isinstance(message_or_callback, Message):
                user = message_or_callback.from_user
            elif isinstance(message_or_callback, CallbackQuery):
                user = message_or_callback.from_user
            else:
                print(f"check_banned: Unexpected type {type(message_or_callback)}")
                return  # Do not call the function with an invalid type

            user_id = user.id
            try:
                db = get_database()
                
                # Check if user is banned using new ban manager
                from .ban_manager import check_user_ban_status
                is_banned, _ = await check_user_ban_status(user_id, db)
                if is_banned:
                    # Silently ignore banned users
                    return
            except Exception as db_error:
                # If database is not initialized, just continue
                print(f"Database not ready for ban check: {db_error}")
                # Allow the command to proceed if database is not ready
            
            return await func(client, message_or_callback, *args, **kwargs)
        except Exception as e:
            print(f"Error in check_banned decorator: {e}")
            # Allow the command to proceed even if there's an error
            return await func(client, message_or_callback, *args, **kwargs)
    return wrapper

def ignore_old_messages(max_age_seconds=300):  # Default 5 minutes
    """Decorator to ignore messages older than max_age_seconds"""
    def decorator(func):
        @wraps(func)
        async def wrapped(client: Client, message: Message, *args, **kwargs):
            # Get message date
            message_date = message.date
            
            # Calculate message age in seconds
            current_time = datetime.now(timezone.utc)
            message_age = (current_time - message_date).total_seconds()
            
            # Ignore if message is too old
            if message_age > max_age_seconds:
                return
            
            return await func(client, message, *args, **kwargs)
        return wrapped
    return decorator

def auto_register_user(func):
    """Decorator to auto-register users in the database if they use any command."""
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        try:
            # Check if database is initialized by trying to get it
            try:
                db = get_database()
                user = message.from_user
                if user:
                    existing_user = await db.get_user(user.id)
                    if not existing_user:
                        user_data = {
                            'user_id': user.id,
                            'username': user.username,
                            'first_name': user.first_name,
                            'coins': 100,  # Starting bonus
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
                            },
                            'joined_at': datetime.now(),
                            'shards': 0  # 🎐 Shards currency
                        }
                        await db.add_user(user_data)
            except Exception as db_error:
                # If database is not initialized, just continue without registration
                print(f"Database not ready for auto-registration: {db_error}")
                # Don't fail the command, just continue
            
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            # Log the error but don't crash the bot
            print(f"Error in auto_register_user decorator for function {func.__name__}: {e}")
            # Don't send error message, just continue with the command
            return await func(client, message, *args, **kwargs)
    return wrapper


async def _is_user_member_of_chat(client: Client, chat_username_or_id: str, user_id: int) -> bool:
    """Return True if the user is currently a member of the given chat."""
    try:
        member = await client.get_chat_member(chat_username_or_id, user_id)
        status = member.status
        # Accept active member/admin/owner
        try:
            # Pyrogram v2 enum
            return status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED)
        except Exception:
            # Fallback for older pyrograms: compare by string
            status_str = str(status).lower()
            return not any(s in status_str for s in ["left", "kicked", "banned"])
    except Exception as e:
        try:
            print(f"require_membership: get_chat_member failed: {e}")
        except:
            pass
        return False


def require_membership(chat_username_or_id: str, join_link: str = None):
    """Decorator that requires the user to be a member of a specific chat to proceed.

    chat_username_or_id: e.g., '@CollectXPokemonChat' or a chat ID
    join_link: Optional explicit invite/join link to show in the prompt
    """
    def decorator(func):
        @wraps(func)
        async def wrapped(client: Client, message_or_callback, *args, **kwargs):
            try:
                # Extract user and reply method
                if isinstance(message_or_callback, Message):
                    user = message_or_callback.from_user
                    reply = message_or_callback.reply_text
                elif isinstance(message_or_callback, CallbackQuery):
                    user = message_or_callback.from_user
                    reply = message_or_callback.message.reply_text if message_or_callback.message else None
                else:
                    return

                if not user:
                    return

                user_id = user.id
                # Admins bypass
                try:
                    db = get_database()
                    if await is_admin(db, user_id):
                        return await func(client, message_or_callback, *args, **kwargs)
                except Exception as db_error:
                    try:
                        print(f"require_membership: admin check skipped due to DB error: {db_error}")
                    except:
                        pass

                # Membership check
                is_member = await _is_user_member_of_chat(client, chat_username_or_id, user_id)
                if not is_member:
                    link = join_link or (chat_username_or_id if str(chat_username_or_id).startswith("http") else f"https://t.me/{str(chat_username_or_id).lstrip('@')}")
                    chat_handle = f"@{str(chat_username_or_id).lstrip('@')}"
                    text = (
                        "<b>🔒 Access Restricted</b>\n\n"
                        "To use this feature, please join our group first:\n"
                        f"<a href=\"{link}\">{chat_handle}</a>\n\n"
                        "After joining, run the command again."
                    )
                    markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ Join Group", url=link)]]
                    )
                    if reply:
                        await reply(text, reply_markup=markup, disable_web_page_preview=True)
                    return

                return await func(client, message_or_callback, *args, **kwargs)
            except Exception as e:
                try:
                    print(f"Error in require_membership decorator for {func.__name__}: {e}")
                except:
                    pass
                # Fail-open to avoid blocking if unexpected error
                return await func(client, message_or_callback, *args, **kwargs)
        return wrapped
    return decorator