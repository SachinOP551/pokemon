from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from .decorators import check_banned
from .logging_utils import send_new_user_log, send_new_group_log
# Import database based on configuration
from modules.postgres_database import get_database
import random
from datetime import datetime

# Constants
SUPPORT_GROUP = "https://t.me/CollectSuperHeroesGC"
CHANNEL = "https://t.me/CollectHeroes"
BOT_USERNAME = "CollectHeroesBot"

# Welcome images
WELCOME_IMAGES = [
   "https://ibb.co/ym2wjL95",
   "https://ibb.co/rfbySH0Z",
   "https://ibb.co/hF7Knm2q",
   "https://ibb.co/RTcBSYFd",
   "https://ibb.co/0jHjbhTn",
   "https://ibb.co/s9N9MjcF",
   "https://ibb.co/0VjdNxvS"
]

# Temporarily removed decorator for debugging
async def start_command(client: Client, message: Message):
    print("[DEBUG] start_command handler called")
    print(f"Start command received from {message.from_user.id}")
    
    user = message.from_user
    try:
        db = get_database()
        print("[DEBUG] Database instance acquired in start_command")
    except Exception as e:
        print(f"[ERROR] Could not get database instance: {e}")
        # Don't fail the command, just continue without database operations
        db = None
    
    # Register user if new
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
        'shards': 0
    }
    
    # Check if user exists (only if database is available)
    if db:
        existing_user = await db.get_user(user.id)
        is_new_user = not existing_user
        
        print(f"[DEBUG] User {user.id} - existing_user: {existing_user is not None}, is_new_user: {is_new_user}")
        
        if is_new_user:
            print(f"[DEBUG] Adding new user {user.id} to database")
            await db.add_user(user_data)
            # Send new user log
            print(f"[DEBUG] Sending new user log for {user.id}")
            try:
                await send_new_user_log(client, user)
                print(f"[DEBUG] New user log sent successfully for {user.id}")
            except Exception as e:
                print(f"[ERROR] Failed to send new user log: {e}")
        else:
            print(f"[DEBUG] User {user.id} already exists, skipping registration")
    else:
        print("[DEBUG] Database not available, skipping user registration")
    
    # Create keyboard markup with more options
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ", 
                url=f"https://t.me/{BOT_USERNAME}?startgroup=true"
            )
        ],
        [
            InlineKeyboardButton("🦸 ʜᴇʟᴘ", callback_data="help"),
            InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇs", url=CHANNEL)
        ],
        [
            InlineKeyboardButton("👥 sᴜᴘᴘᴏʀᴛ", url=SUPPORT_GROUP),
            InlineKeyboardButton("❄️ ᴏᴡɴᴇʀ", url="https://t.me/Lucifer_kun")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Enhanced Super Heroes-themed welcome message with better formatting
    welcome_text = (
    f"🌸 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀɴɪᴍᴇ ᴄᴏʟʟᴇᴄᴛᴏʀ ᴜɴɪᴠᴇʀsᴇ {user.first_name}!\n\n"
    "ʏᴏᴜʀ ᴊᴏᴜʀɴᴇʏ ɪɴ ᴛʜᴇ ᴡᴏʀʟᴅ ᴏғ ᴀɴɪᴍᴇ ʙᴇɢɪɴs ʜᴇʀᴇ\n\n"
    "✨ ғᴇᴀᴛᴜʀᴇs:\n"
    "┣ ᴄᴏʟʟᴇᴄᴛ ʀᴀʀᴇ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┣ ᴛʀᴀᴅᴇ ᴡɪᴛʜ ᴏᴛʜᴇʀ ᴄᴏʟʟᴇᴄᴛᴏʀs\n"
    "┣ ᴄᴏᴍᴘᴇᴛᴇ ɪɴ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs\n"
    "┣ ᴇᴀʀɴ ᴛᴏᴋᴇɴs & ʀᴇᴡᴀʀᴅs\n"
    "┗ sʜᴏᴡᴄᴀsᴇ ʏᴏᴜʀ ᴀɴɪᴍᴇ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
    "🎮 ǫᴜɪᴄᴋ sᴛᴀʀᴛ:\n"
    "┣ /daily - ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs\n"
    "┣ /collect - ʙᴇɢɪɴ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴀɴɪᴍᴇ ʜᴇʀᴏᴇs\n"
    "┣ /claim - ᴄʟᴀɪᴍ ᴀ ғʀᴇᴇ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ\n"
    "ʀᴇᴀᴅʏ ᴛᴏ ʙᴜɪʟᴅ ʏᴏᴜʀ ᴛᴇᴀᴍ ᴏғ ᴀɴɪᴍᴇ ʜᴇʀᴏᴇs?"
)

    
    # Select random welcome image
    random_image = random.choice(WELCOME_IMAGES)
    
    print("Sending welcome message...")
    # Send photo with caption
    await message.reply_photo(
        photo=random_image,
        caption=welcome_text,
        reply_markup=reply_markup
    )
    print("Welcome message sent successfully!")

async def new_chat_members(client: Client, message: Message):
    """Handle when bot is added to a new group"""
    # Check if bot was added
    new_members = message.new_chat_members
    bot_id = (await client.get_me()).id
    
    for member in new_members:
        if member.id == bot_id:
            # Bot was added to the group
            chat = message.chat
            added_by = message.from_user
            
            # Add group to database
            db = get_database()
            await db.add_user_to_group(added_by.id, chat.id)
            # Ensure chat_settings exists/updated for this group
            try:
                await db.update_chat_settings(chat.id, {
                    'chat_title': chat.title,
                    'drop_enabled': True,
                    'drop_interval': 300,
                    'last_drop': None
                })
            except Exception:
                pass
            
            # Send new group log
            await send_new_group_log(client, chat, added_by)
            
            # Send welcome message in group with drop info
            await message.reply_text(
                f"🎉 ᴛʜᴀɴᴋs ғᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ ᴛᴏ {chat.title}!\n\n"
                f"💬 ʀᴀɴᴅᴏᴍ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪʟʟ ʙᴇ ᴅʀᴏᴘᴘᴇᴅ ʜᴇʀᴇ ᴇᴠᴇʀʏ 60 ᴍᴇssᴀɢᴇs\n\n"
                f"ʏᴏᴜ ᴄᴀɴ ᴄʜᴀɴɢᴇ ᴅʀᴏᴘᴛɪᴍᴇ ᴜsɪɴɢ /droptime !",
            )
            
            break

async def help_callback(client: Client, callback_query: CallbackQuery):
    """Handle help button callback"""
    help_text = (
    "🎌 ᴀɴɪᴍᴇ ᴄᴏʟʟᴇᴄᴛ ᴄᴏᴍᴍᴀɴᴅs 🎌\n\n"
    "📱 ʙᴀsɪᴄ ᴄᴏᴍᴍᴀɴᴅs\n"
    "┣ /start - ʀᴇsᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ\n"
    "┣ /bal - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴛᴏᴋᴇɴs\n"
    "┣ /claim - ᴄʟᴀɪᴍ ᴀ ᴅᴀɪʟʏ ғʀᴇᴇ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ\n"
    "┗ /daily - ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs\n\n"
    "🎮 ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n"
    "┣ /collect - ᴄᴏʟʟᴇᴄᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┣ /mycollection - ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n"
    "┣ /search - sᴇᴀʀᴄʜ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┣ /check - ᴄʜᴇᴄᴋ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪɴғᴏ\n"
    "┗ /srarity - sᴇᴀʀᴄʜ ʙʏ ʀᴀʀɪᴛʏ\n\n"
    "🔄 ᴛʀᴀᴅɪɴɢ\n"
    "┣ /trade - ᴛʀᴀᴅᴇ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┣ /gift - ɢɪғᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┗ /propose - ᴘʀᴏᴘᴏsᴇ ᴀ ᴛʀᴀᴅᴇ\n\n"
    "📊 ʀᴀɴᴋɪɴɢs\n"
    "┣ /tdtop - ᴛᴏᴅᴀʏ's ᴛᴏᴘ ᴄᴏʟʟᴇᴄᴛᴏʀs\n"
    "┗ /gtop - ɢʟᴏʙᴀʟ ᴛᴏᴘ ᴄᴏʟʟᴇᴄᴛᴏʀs\n\n"
    "ᴛᴀᴘ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ʀᴇᴛᴜʀɴ!"
)

    # Create back button
    keyboard = [[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Edit the message instead of deleting and sending new
    await callback_query.message.edit_text(
        help_text,
        reply_markup=reply_markup
    )

async def back_callback(client: Client, callback_query: CallbackQuery):
    """Handle back button callback"""
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ", 
                url=f"https://t.me/{BOT_USERNAME}?startgroup=true"
            )
        ],
        [
            InlineKeyboardButton("🦸 ʜᴇʟᴘ", callback_data="help"),
            InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇs", url=CHANNEL)
        ],
        [
            InlineKeyboardButton("👥 sᴜᴘᴘᴏʀᴛ", url=SUPPORT_GROUP),
            InlineKeyboardButton("❄️ ᴏᴡɴᴇʀ", url="https://t.me/Lucifer_kun")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    random_image = random.choice(WELCOME_IMAGES)
    welcome_text = (
    f"ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀɴɪᴍᴇ ᴄᴏʟʟᴇᴄᴛᴏʀ ᴜɴɪᴠᴇʀsᴇ {callback_query.from_user.first_name} 🌸\n\n"
    "ɢᴀᴛʜᴇʀ ʏᴏᴜʀ ᴛᴇᴀᴍ ᴏғ ᴀɴɪᴍᴇ ʜᴇʀᴏᴇs & ᴠɪʟʟᴀɪɴs!\n\n"
    "✨ ғᴇᴀᴛᴜʀᴇs:\n"
    "┣ ᴄᴏʟʟᴇᴄᴛ ʀᴀʀᴇ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┣ ᴛʀᴀᴅᴇ ᴡɪᴛʜ ᴏᴛʜᴇʀ ᴄᴏʟʟᴇᴄᴛᴏʀs\n"
    "┣ ᴄᴏᴍᴘᴇᴛᴇ ɪɴ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs\n"
    "┣ ᴇᴀʀɴ ᴛᴏᴋᴇɴs & ʀᴇᴡᴀʀᴅs\n"
    "┗ sʜᴏᴡᴄᴀsᴇ ʏᴏᴜʀ ᴀɴɪᴍᴇ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
    "🎮 ǫᴜɪᴄᴋ sᴛᴀʀᴛ:\n"
    "┣ /daily - ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs\n"
    "┣ /collect - ʙᴇɢɪɴ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
    "┣ /claim - ᴄʟᴀɪᴍ ᴀ ғʀᴇᴇ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ\n\n"
    "ʀᴇᴀᴅʏ ᴛᴏ ᴇᴍʙᴀʀᴋ ᴏɴ ʏᴏᴜʀ ᴀɴɪᴍᴇ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴊᴏᴜʀɴᴇʏ?"
)

    # Edit the message media (photo and caption)
    await callback_query.message.edit_media(
        media=InputMediaPhoto(media=random_image, caption=welcome_text),
        reply_markup=reply_markup
    )



def setup_start_handlers(app: Client):
    """Setup handlers for start module"""
    print("Registering start command handler...")
    app.on_message(filters.command("start"))(start_command)
    print("Registering callback handlers...")
    app.on_callback_query(filters.regex("^help$"))(help_callback)
    app.on_callback_query(filters.regex("^back$"))(back_callback)
    app.on_message(filters.new_chat_members)(new_chat_members)
    print("All start handlers registered successfully!")