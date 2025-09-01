from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from .decorators import check_banned
from .logging_utils import send_new_user_log, send_new_group_log
# Import database based on configuration
from modules.postgres_database import get_database, get_rarity_emoji
import random
from datetime import datetime

# Constants
SUPPORT_GROUP = "https://t.me/CollectXPokemonChat"
CHANNEL = "https://t.me/CollectPokemon"
BOT_USERNAME = "CollectXPokemonBot"

# Welcome images
WELCOME_IMAGES = [
   "https://i.ibb.co/Y4jB2SMV/e49a0413a6a838522f604369fbf772d7.jpg",
   "https://i.ibb.co/93SM8jrT/17be466f0896063b0cb4b55322887d33.jpg",
   "https://i.ibb.co/v6nZNgFK/1c86ea8ce0ff36fe87330a9829fa4335.jpg",
   "https://i.ibb.co/G4FQ2xTL/0eb1c87fe78f0f1d92d218a3d39e7714.jpg",
   "https://i.ibb.co/d083ZXZ0/6efe3c6d966a9f19978755a813a65df6.jpg"
]

# Temporarily removed decorator for debugging
async def start_command(client: Client, message: Message):
    print("[DEBUG] start_command handler called")
    print(f"Start command received from {message.from_user.id}")
    
    # Check if this is a details request from the CHECK DETAILS IN DM button
    if message.text and message.text.startswith('/start details_'):
        try:
            # Extract character ID from the start parameter
            character_id = int(message.text.split('details_')[1])
            print(f"[DEBUG] Details request for character ID: {character_id}")
            
            # Get database instance
            db = get_database()
            if not db:
                await message.reply_text("❌ Database connection error. Please try again later.")
                return
            
            # Fetch character details
            character = await db.get_character(character_id)
            if not character:
                await message.reply_text("❌ Character not found. It may have been removed from the database.")
                return
            
            # Get rarity emoji
            rarity_emoji = get_rarity_emoji(character.get('rarity', 'Unknown'))
            
            # Format character details message
            details_text = (
                f"🔍 <b>CHARACTER DETAILS</b> 🔍\n\n"
                f"📛 <b>Name:</b> <code>{character.get('name', 'Unknown')}</code>\n"
                f"{rarity_emoji} <b>Rarity:</b> {character.get('rarity', 'Unknown')}\n"
                f"⛩ <b>Region:</b> {character.get('anime', 'Unknown')}\n"
                f"🏷 <b>Type:</b> {character.get('type', 'Unknown')}\n"
                f"🆔 <b>ID:</b> <code>{character.get('character_id', 'Unknown')}</code>\n"
            )
            
            
            
            # Send character details with media
            if character.get('is_video', False):
                video_source = character.get('img_url') or character.get('file_id')
                await client.send_video(
                    chat_id=message.chat.id,
                    video=video_source,
                    caption=details_text
                )
            else:
                photo = character.get('img_url') or character.get('file_id')
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=photo,
                    caption=details_text
                )
            
            return
            
        except (ValueError, IndexError) as e:
            print(f"[ERROR] Failed to parse character ID from start parameter: {e}")
            # Fall through to normal start command
        except Exception as e:
            print(f"[ERROR] Error handling details request: {e}")
            await message.reply_text("❌ Error fetching character details. Please try again later.")
            return
    
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
    f"⚡ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴘᴏᴋᴇᴍᴏɴ ᴛʀᴀɪɴᴇʀ ᴜɴɪᴠᴇʀsᴇ, {user.first_name}!\n\n"
    "ʏᴏᴜʀ ᴊᴏᴜʀɴᴇʏ ᴛᴏ ʙᴇᴄᴏᴍᴇ ᴀ ᴍᴀsᴛᴇʀ ᴘᴏᴋᴇᴍᴏɴ ᴛʀᴀɪɴᴇʀ ʙᴇɢɪɴs ʜᴇʀᴇ.\n\n"
    "✨ ғᴇᴀᴛᴜʀᴇs:\n"
    "┣ ᴄᴀᴛᴄʜ ᴀ ᴠᴀʀɪᴇᴛʏ ᴏғ ᴘᴏᴋᴇᴍᴏɴ\n"
    "┣ ᴘᴀʀᴛɪᴄɪᴘᴀᴛᴇ ɪɴ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs ᴀɴᴅ ᴛᴏᴜʀɴᴀᴍᴇɴᴛs\n"
    "┣ ᴇᴀʀɴ ᴛᴏᴋᴇɴs, ʀᴇᴡᴀʀᴅs, ᴀɴᴅ ʀᴀʀᴇ ɪᴛᴇᴍs\n"
    "┗ sʜᴏᴡᴄᴀsᴇ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
    "🎮 ǫᴜɪᴄᴋ sᴛᴀʀᴛ:\n"
    "┣ /daily - ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs\n"
    "┣ /catch - ʙᴇɢɪɴ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n"
    "┣ /trade - ᴛʀᴀᴅᴇ ᴘᴏᴋᴇᴍᴏɴ ᴡɪᴛʜ ᴏᴛʜᴇʀ ᴛʀᴀɪɴᴇʀs\n"
    "ʀᴇᴀᴅʏ ᴛᴏ ʙᴜɪʟᴅ ʏᴏᴜʀ ᴅʀᴇᴀᴍ ᴘᴏᴋᴇᴍᴏɴ ᴛᴇᴀᴍ?"
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

async def show_character_details(client: Client, message: Message, character_id: int):
    """Show character details when user clicks CHECK DETAILS IN DM"""
    try:
        db = get_database()
        if not db:
            await message.reply_text("❌ Database connection error. Please try again later.")
            return
        
        # Get character details from database
        character = await db.get_character(character_id)
        if not character:
            await message.reply_text("❌ Character not found or has been removed.")
            return
        
        # Get rarity emoji
        rarity_emoji = get_rarity_emoji(character.get('rarity', 'Unknown'))
        
        # Create detailed character info
        details_text = (
            f"🔍 <b>Character Details</b>\n\n"
            f"👤 <b>Name:</b> {character.get('name', 'Unknown')}\n"
            f"{rarity_emoji} <b>Rarity:</b> {character.get('rarity', 'Unknown')}\n"
            f"⛩ <b>Region:</b> {character.get('anime', 'Unknown')}\n"
            f"🆔 <b>ID:</b> <code>{character.get('character_id', 'Unknown')}</code>\n"
        )
        
        # Add type if available
        if character.get('type'):
            details_text += f"🏷 <b>Type:</b> {character.get('type')}\n"
        
        # Create keyboard with options
        keyboard = [
            [
                InlineKeyboardButton("🔙 Back to Start", callback_data="back"),
                InlineKeyboardButton("📱 Add to Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send character details
        if character.get('is_video', False):
            # For video characters
            video_source = character.get('img_url') or character.get('file_id')
            await message.reply_video(
                video=video_source,
                caption=details_text,
                reply_markup=reply_markup
            )
        else:
            # For photo characters
            photo = character.get('img_url') or character.get('file_id')
            await message.reply_photo(
                photo=photo,
                caption=details_text,
                reply_markup=reply_markup
            )
            
    except Exception as e:
        print(f"Error showing character details: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text("❌ An error occurred while fetching character details. Please try again later.")

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
    "🎌 ᴘᴏᴋᴇᴍᴏɴ ᴛʀᴀɪɴᴇʀ ᴄᴏᴍᴍᴀɴᴅs 🎌\n\n"
    "📱 ʙᴀsɪᴄ ᴄᴏᴍᴍᴀɴᴅs\n"
    "┣ /start - ʀᴇsᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ\n"
    "┣ /bal - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴛᴏᴋᴇɴs\n"
    "┣ /claim - ʀᴇᴄᴇɪᴠᴇ ᴀ ᴅᴀɪʟʏ ғʀᴇᴇ ᴘᴏᴋᴇᴍᴏɴ\n"
    "┗ /daily - ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs\n\n"
    "🎮 ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n"
    "┣ /catch - ᴄᴀᴛᴄʜ ᴘᴏᴋᴇᴍᴏɴ\n"
    "┣ /mycollection - ᴠɪᴇᴡ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n"
    "┣ /search - sᴇᴀʀᴄʜ ᴘᴏᴋᴇᴍᴏɴ\n"
    "┣ /check - ᴠɪᴇᴡ ᴘᴏᴋᴇᴍᴏɴ ᴅᴇᴛᴀɪʟs\n"
    "┗ /rarity - sᴇᴀʀᴄʜ ʙʏ ʀᴀʀɪᴛʏ\n\n"
    "🔄 ᴛʀᴀᴅɪɴɢ\n"
    "┣ /trade - ᴛʀᴀᴅᴇ ᴘᴏᴋᴇᴍᴏɴ\n"
    "┣ /gift - ɢɪғᴛ ᴘᴏᴋᴇᴍᴏɴ ᴛᴏ ᴏᴛʜᴇʀ ᴛʀᴀɪɴᴇʀs\n"
    "┗ /propose - ᴘʀᴏᴘᴏsᴇ ᴀ ᴛʀᴀᴅᴇ\n\n"
    "📊 ʀᴀɴᴋɪɴɢs\n"
    "┣ /tdtop - ᴛᴏᴅᴀʏ's ᴛᴏᴘ ᴛʀᴀɪɴᴇʀs\n"
    "┗ /gtop - ɢʟᴏʙᴀʟ ᴛᴏᴘ ᴛʀᴀɪɴᴇʀs\n\n"
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
    f"⚡ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴘᴏᴋᴇᴍᴏɴ ᴛʀᴀɪɴᴇʀ ᴜɴɪᴠᴇʀsᴇ, {callback_query.from_user.first_name}! 🌟\n\n"
    "✨ ғᴇᴀᴛᴜʀᴇs:\n"
    "┣ ᴄᴀᴛᴄʜ ᴀ ᴠᴀʀɪᴇᴛʏ ᴏғ ᴘᴏᴋᴇᴍᴏɴ\n"
    "┣ ᴘᴀʀᴛɪᴄɪᴘᴀᴛᴇ ɪɴ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs\n"
    "┣ ᴇᴀʀɴ ᴛᴏᴋᴇɴs, ʀᴇᴡᴀʀᴅs & ʀᴀʀᴇ ɪᴛᴇᴍs\n"
    "┗ sʜᴏᴡᴄᴀsᴇ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
    "🎮 ǫᴜɪᴄᴋ sᴛᴀʀᴛ:\n"
    "┣ /daily - ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs\n"
    "┣ /catch - ʙᴇɢɪɴ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n"
    "┣ /trade - ᴛʀᴀᴅᴇ ᴘᴏᴋᴇᴍᴏɴ ᴡɪᴛʜ ᴏᴛʜᴇʀs\n\n"
    "ʀᴇᴀᴅʏ ᴛᴏ ᴇᴍʙᴀʀᴋ ᴏɴ ʏᴏᴜʀ ᴘᴏᴋᴇᴍᴏɴ ᴛʀᴀɪɴɪɴɢ ᴊᴏᴜʀɴᴇʏ?"
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
