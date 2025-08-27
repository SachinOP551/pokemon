from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, InlineQuery, InlineQueryResultArticle, InlineQueryResultPhoto, InlineQueryResultVideo, InputTextMessageContent
import re
import asyncio
import base64
import io
import logging
import mimetypes
import os
import aiohttp
import cloudinary
import cloudinary.uploader
from pyrogram.enums import ParseMode
import requests
from config import LOG_CHANNEL_ID, DROPTIME_LOG_CHANNEL, OWNER_ID
from modules.decorators import admin_only
from modules.postgres_database import get_database, RARITIES, RARITY_EMOJIS

# Constants
WAIFU = "Pokémon"
ANIME = "Region"
SUPPORT_CHAT_ID = LOG_CHANNEL_ID
LOG_CHANNEL = DROPTIME_LOG_CHANNEL

CATBOX_API_URL = "https://catbox.moe/user/api.php"

# Cloudinary configuration for video uploads
cloudinary.config(
    cloud_name="de96qtqav",
    api_key="755161292211756",
    api_secret="vO_1lOfhJQs3kI4C5v1E8fywYW8"
)

upload_details = {}
# Track user states for conversation flow
user_states = {}

# Helper functions for admin permissions
async def is_sudo(db, user_id: int) -> bool:
    """Check if user is a sudo admin"""
    user_data = await db.get_user(user_id)
    return user_data and user_data.get('sudo', False)

async def is_og(db, user_id: int) -> bool:
    """Check if user is an OG"""
    user_data = await db.get_user(user_id)
    return user_data and user_data.get('og', False)

def get_upload_error_message():
    """Get a user-friendly error message for upload failures."""
    return (
        "<b>❌ Upload failed!</b>\n\n"
        "This could be due to:\n"
        "• Network connectivity issues\n"
        "• Large file size (try a smaller image)\n"
        "• Temporary server maintenance\n"
        "• Firewall or proxy blocking uploads\n\n"
        "Please try again in a few minutes or use a smaller image file."
    )

async def get_total_waifus():
    """Get total number of waifus"""
    try:
        db = get_database()
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) as count FROM characters")
                return result['count'] if result else 0
        else:  # MongoDB
            return await db.characters.count_documents({})
    except Exception as e:
        print(f"Error getting total waifus: {e}")
        return 0

async def get_total_animes():
    """Get total number of unique animes"""
    try:
        db = get_database()
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(DISTINCT anime) as count FROM characters WHERE anime IS NOT NULL AND anime != ''")
                return result['count'] if result else 0
        else:  # MongoDB
            pipeline = [
                {"$match": {"anime": {"$exists": True, "$ne": None, "$ne": ""}}},
                {"$group": {"_id": "$anime"}},
                {"$count": "count"}
            ]
            result = list(await db.characters.aggregate(pipeline).to_list(length=1))
            return result[0]['count'] if result else 0
    except Exception as e:
        print(f"Error getting total animes: {e}")
        return 0

async def get_total_harems():
    """Get total number of unique users who have collected at least one character"""
    try:
        db = get_database()
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # First check if user_characters table exists and has data
                table_exists = await conn.fetchrow(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_characters')"
                )
                
                if not table_exists or not table_exists['exists']:
                    # If table doesn't exist, count users who have characters in their array
                    result = await conn.fetchrow(
                        "SELECT COUNT(*) as count FROM users WHERE array_length(characters, 1) > 0"
                    )
                else:
                    # Use user_characters table
                    result = await conn.fetchrow("SELECT COUNT(DISTINCT user_id) as count FROM user_characters")
                
                return result['count'] if result else 0
        else:  # MongoDB
            # For MongoDB, check if user_characters collection exists
            collections = await db.list_collection_names()
            if 'user_characters' in collections:
                pipeline = [
                    {"$group": {"_id": "$user_id"}},
                    {"$count": "count"}
                ]
                result = list(await db.user_characters.aggregate(pipeline).to_list(length=1))
                return result[0]['count'] if result else 0
            else:
                # Fallback to counting users with characters array
                count = await db.users.count_documents({"characters": {"$exists": True, "$ne": []}})
                return count
    except Exception as e:
        print(f"Error getting total harems: {e}")
        return 0

async def get_next_character_id():
    """Get the next character ID that will be assigned"""
    try:
        db = get_database()
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Get the current sequence value for character_id
                result = await conn.fetchrow(
                    "SELECT last_value FROM characters_character_id_seq"
                )
                if result:
                    return result['last_value'] + 1
                else:
                    # If sequence doesn't exist, get the max character_id and add 1
                    result = await conn.fetchrow(
                        "SELECT COALESCE(MAX(character_id), 0) + 1 as next_id FROM characters"
                    )
                    return result['next_id']
        else:  # MongoDB
            # For MongoDB, get the max _id and add 1
            result = await db.characters.find_one(
                sort=[("_id", -1)]
            )
            if result:
                return result['_id'] + 1
            else:
                return 1
    except Exception as e:
        print(f"Error getting next character ID: {e}")
        # Fallback to a simple hash-based ID
        return None



import os
import mimetypes
import asyncio
import aiohttp

async def upload_to_imgbb(file_id: str, client) -> str:
    """Upload image to ImgBB."""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Download file from Telegram
            file = await asyncio.wait_for(client.download_media(file_id), timeout=120)

            # Load file bytes and filename
            if isinstance(file, str):
                filename = os.path.basename(file)
                with open(file, 'rb') as f:
                    file_bytes = f.read()
            elif hasattr(file, 'read'):
                file.seek(0)
                file_bytes = file.read()
                filename = 'upload.jpg'
            else:
                raise Exception("Unsupported file type")

            # Guess content type
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = 'application/octet-stream'

            # Prepare form data
            timeout = aiohttp.ClientTimeout(total=60)
            connector = aiohttp.TCPConnector(ssl=False, limit=100, limit_per_host=30)
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                data = aiohttp.FormData()
                data.add_field('image', file_bytes, filename=filename, content_type=content_type)

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                # ImgBB API key in URL
                api_key = "4b74c2097adb72dfd0cc7941199d8f4c"
                url = f"https://api.imgbb.com/1/upload?key={api_key}"

                async with session.post(url, data=data, headers=headers) as response:
                    result_text = await response.text()  # Debug response
                    if response.status == 200:
                        result = await response.json()
                        if 'data' in result and 'url' in result['data']:
                            return result['data']['url']
                        else:
                            raise Exception(f"ImgBB API returned unexpected response: {result}")
                    else:
                        raise Exception(f"ImgBB API returned status {response.status}: {result_text}")

        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                print(f"[Retry {attempt+1}] Timeout while downloading Telegram media. Retrying...")
                await asyncio.sleep(2)
                continue
            print("Download timed out after multiple attempts.")
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[Retry {attempt+1}] Error uploading to ImgBB: {e}. Retrying...")
                await asyncio.sleep(2)
                continue
            print(f"Error uploading to ImgBB: {e}")
            return None

    return None


async def upload_video_to_cloudinary(file_id: str, client) -> str:
    """Upload video to Cloudinary."""
    try:
        file = await asyncio.wait_for(client.download_media(file_id), timeout=120)
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: cloudinary.uploader.upload(file, resource_type="video")
        )
        return result["secure_url"]
    except Exception as e:
        print(f"Error uploading video to Cloudinary: {e}")
        return None

async def handle_admin_panel(client, message: Message):
    """Handle the admin panel message"""
    # Check if user is admin
    user_id = message.from_user.id
    try:
        db = get_database()
        # Check if user is admin (owner, sudo, or og)
        if not (user_id == OWNER_ID or await is_sudo(db, user_id) or await is_og(db, user_id)):
            await message.reply_text("❌ You don't have permission to access the admin panel.")
            return
    except Exception as e:
        await message.reply_text("❌ Error checking permissions. Please try again later.")
        return
    
    # Fetch total counts
    total_waifus = await get_total_waifus()
    total_animes = await get_total_animes()
    total_harems = await get_total_harems()
    
    # Create the confirmation text with better formatting
    confirmation_text = (
        f"<b>⚙️ Admin Control Panel ⚙️</b>\n\n"
        f"🎀 <b>Total {WAIFU}s:</b> <code>{total_waifus:,}</code>\n"
        f"⛩️ <b>Total {ANIME}s:</b> <code>{total_animes:,}</code>\n"
        f"🔧 <b>Available Actions:</b>"
    )
    
    # Create a better button grid layout
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"➕ Add {WAIFU}", callback_data="add_waifu"),
            InlineKeyboardButton(f"➕ Add {ANIME}", callback_data="add_anime")
        ],
        [
            InlineKeyboardButton(f"✏️ Edit {WAIFU}", callback_data="edit_character"),
            InlineKeyboardButton(f"✏️ Rename {ANIME}", callback_data="rename_anime")
        ],
        [
            InlineKeyboardButton(f"🗑️ Delete {WAIFU}", callback_data="delete_character"),
            InlineKeyboardButton(f"🔄 Reset {WAIFU}", callback_data="reset_character")
        ],
        [InlineKeyboardButton("❌ Close Panel", callback_data="xxx")]
    ])

    await message.reply_text(confirmation_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

async def start_character_upload(client: Client, callback_query: CallbackQuery):
    """Start the character upload process"""
    user_id = callback_query.from_user.id
    await callback_query.message.delete()

    # Set user state to waiting for media
    user_states[user_id] = "waiting_for_media"
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Upload", callback_data="close_upload")]
    ])
    
    await client.send_message(
        user_id,
        text=f"Please send the image or video of the {WAIFU} you want to upload!",
        reply_markup=btn
    )

async def handle_media_upload(client: Client, message: Message):
    """Handle media upload from user"""
    user_id = message.from_user.id
    
    # Check if user is in upload state
    if user_id not in user_states or user_states[user_id] != "waiting_for_media":
        return False
    
    try:
        # Determine media type and get file_id
        if message.photo:
            media_type = "image"
            file_id = message.photo.file_id
            is_video = False
        elif message.video:
            media_type = "video"
            file_id = message.video.file_id
            is_video = True
        else:
            await message.reply_text("Please send a valid image or video file.")
            return True
        
        # Show processing message
        processing_msg = await message.reply_text(
            f"<i>Processing your {media_type} upload, please wait...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Upload based on media type
        if is_video:
            img_url = await upload_video_to_cloudinary(file_id, client)
        else:
            img_url = await upload_to_imgbb(file_id, client)
        
        if not img_url:
            await processing_msg.edit_text("Upload failed. Please try again.")
            return True
        
        # Store upload details
        upload_details[user_id] = {
            "img_url": img_url,
            "is_video": is_video,
            "media_type": media_type
        }
        
        # Update user state and ask for character name
        user_states[user_id] = "waiting_for_name"
        
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel Upload", callback_data="close_upload")]
        ])
        
        await message.reply_text(
            f"{media_type.capitalize()} uploaded: {img_url}\n\nNow please send the {WAIFU} name.",
            reply_markup=btn
        )
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_name_input(client: Client, message: Message):
    """Handle character name input"""
    user_id = message.from_user.id
    
    # Check if user is in name input state
    if user_id not in user_states or user_states[user_id] != "waiting_for_name":
        return False
    
    try:
        upload_details[user_id]["name"] = message.text.strip()
        
        # Update user state and ask for anime/team
        user_states[user_id] = "waiting_for_anime"
        
        # Show inline query button for easy anime selection
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔍 Search {ANIME}s", switch_inline_query_current_chat=".anime ")],
            [InlineKeyboardButton("Cancel Upload", callback_data="close_upload")]
        ])
        
        await message.reply_text(
            f"Now please select the {ANIME} for this character.\n\n"
            f"<b>🔍 Search existing {ANIME}s:</b>\n\n",
            reply_markup=btn,
            parse_mode=ParseMode.HTML
        )
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_anime_input(client: Client, message: Message):
    """Handle anime input for character upload"""
    user_id = message.from_user.id
    
    # Check if user is in anime input state
    if user_id not in user_states or user_states[user_id] != "waiting_for_anime":
        return False
    
    try:
        anime_text = message.text.strip()
        
        # Check if this is an inline query result (contains anime name and ID)
        if "🆔 ID:" in anime_text:
            # Extract anime name and ID from inline query result
            parts = anime_text.split("🆔 ID:")
            anime_name = parts[0].strip()
            anime_id = parts[1].strip()
            
            # Store the anime name (not the ID, since we want the name)
            upload_details[user_id]["anime"] = anime_name
        else:
            # This is a direct text input - treat as new anime name
            upload_details[user_id]["anime"] = anime_text
        
        # Update user state and ask for rarity
        user_states[user_id] = "waiting_for_rarity"
        
        # Create rarity buttons using real rarities from database
        rarity_buttons = []
        for rarity_name, rarity_level in sorted(RARITIES.items(), key=lambda x: x[1]):
            emoji = RARITY_EMOJIS.get(rarity_name, "⭐")
            rarity_buttons.append([InlineKeyboardButton(f"{emoji} {rarity_name}", callback_data=f"glob_{rarity_name}")])
        
        rarity_buttons.append([InlineKeyboardButton("Cancel Upload", callback_data="close_upload")])
        rarity_keyboard = InlineKeyboardMarkup(rarity_buttons)
        
        await message.reply_text(
            f"✅ {ANIME} '{upload_details[user_id]['anime']}' selected!\n\nNow choose the rarity:",
            reply_markup=rarity_keyboard
        )
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True





async def create_anime_from_upload_handler(client: Client, callback_query: CallbackQuery):
    """Handle anime creation from character upload flow"""
    user_id = callback_query.from_user.id
    
    # Set user state to waiting for anime name
    user_states[user_id] = "waiting_for_anime_name"
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    text = f"Please send the {ANIME} name you want to create:"
    
    await callback_query.message.edit_text(text, reply_markup=btn)

async def handle_rarity_selection(client: Client, callback_query: CallbackQuery):
    """Handle rarity selection"""
    user_id = callback_query.from_user.id
    
    # Check if user is in rarity selection state
    if user_id not in user_states or user_states[user_id] != "waiting_for_rarity":
        return
    
    try:
        rarity_key = callback_query.data.split("_")[1]
        # Get the proper emoji for the selected rarity
        rarity_emoji = RARITY_EMOJIS.get(rarity_key, "⭐")
        upload_details[user_id].update({"rarity": rarity_key, "rarity_sign": rarity_emoji})
        
        # Update user state to waiting for confirmation
        user_states[user_id] = "waiting_for_confirmation"
        
        # Show confirmation
        data = upload_details[user_id]
        
        # Get the next character ID for preview
        next_character_id = await get_next_character_id()
        character_id_preview = next_character_id if next_character_id else "Auto-assigned"
        
        confirmation_text = (
            f"<b>📝 Upload Confirmation</b>\n\n"
            f"🆔 <b>Pokémon ID:</b> {character_id_preview}\n"
            f"🎀 <b>Name:</b> {data['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {data['anime']}\n"
            f"⭐ <b>Rarity:</b> {data['rarity']}\n"
            f"<b>Please confirm your upload:</b>"
        )
        
        confirm_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Upload", callback_data="glob_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        
        await client.send_photo(
            chat_id=user_id,
            photo=data['img_url'],
            caption=confirmation_text,
            reply_markup=confirm_buttons
        )
        
    except Exception as e:
        await callback_query.message.reply_text(f"Error: {str(e)}")

async def confirm_upload_handler(client: Client, callback_query: CallbackQuery):
    """Confirm the character upload"""
    user_id = callback_query.from_user.id
    data = upload_details.get(user_id)
    if not data:
        await callback_query.message.reply_text("No upload data found")
        return

    try:
        # Show processing message
        await callback_query.message.edit_caption(f"<i>Processing upload and adding to database...</i>", reply_markup=None)
        
        # Get database connection
        db = get_database()
        
        # Prepare character data for database insertion
        character_data = {
            'name': data['name'],
            'anime': data['anime'],
            'rarity': data['rarity'],
            'img_url': data['img_url'],
            'is_video': data.get('is_video', False),
            'added_by': user_id
        }
        
        # Insert character into database
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    INSERT INTO characters (name, anime, rarity, img_url, is_video, added_by)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING character_id, id
                    """,
                    character_data['name'],
                    character_data['anime'],
                    character_data['rarity'],
                    character_data['img_url'],
                    character_data['is_video'],
                    character_data['added_by']
                )
                character_id = result['character_id']
                db_id = result['id']
        else:  # MongoDB
            result = await db.characters.insert_one(character_data)
            character_id = result.inserted_id
            db_id = character_id
        
        # Show success message
        media_type_text = "Video Character" if data.get('is_video') else "Character"
        await callback_query.message.edit_caption(
            f"✅ {WAIFU} successfully uploaded and added to database!\n\n"
            f"🆔 <b>Pokémon ID:</b> {character_id}\n"
            f"🎀 <b>Name:</b> {data['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {data['anime']}\n"
            f"{data['rarity_sign']} <b>Rarity:</b> {data['rarity']}",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )
        
        # Clean up user state and upload details
        if user_id in upload_details:
            del upload_details[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        # Prepare log message
        text = f"<b>✨ New {media_type_text} Uploaded by {callback_query.from_user.mention}!!</b>\n\n"
        text += f"🆔 <b>Pokémon ID:</b> {character_id}\n"
        text += f"🎀 <b>Name :</b> {data['name']}\n"
        text += f"⛩️ <b>{ANIME} :</b> {data['anime']}\n"
        text += f"{data['rarity_sign']} <b>Rarity</b> : {data['rarity']}\n"
        text += f"📹 <b>Type</b> : {media_type_text}\n"
        text += f"👤 <b>Added By:</b> {callback_query.from_user.mention} (ID: {user_id})\n\n"
        
        # Send to log channel
        if data.get('is_video'):
            await client.send_video(chat_id=LOG_CHANNEL, video=data['img_url'], caption=text, parse_mode=ParseMode.HTML)
        else:
            await client.send_photo(chat_id=LOG_CHANNEL, photo=data['img_url'], caption=text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        error_msg = f"Error during upload: {str(e)}"
        print(f"Upload error: {error_msg}")
        await callback_query.message.edit_caption(f"❌ {error_msg}", reply_markup=None)

async def close_upload_handler(client: Client, callback: CallbackQuery):
    """Close the upload process"""
    user_id = callback.from_user.id
    
    # Remove the user's upload details and state from the cache
    if user_id in upload_details:
        upload_details.pop(user_id, None)
    if user_id in user_states:
        del user_states[user_id]
    
    # Delete the message
    await callback.message.delete()
    
    # Optionally, send a confirmation message
    await client.send_message(
        chat_id=user_id,
        text="Upload process has been canceled successfully."
    )
    
async def close_admin_panel(client, callback: CallbackQuery):
    """Close the admin panel"""
    await callback.message.delete()

async def add_anime_handler(client, callback: CallbackQuery):
    """Handle adding anime"""
    user_id = callback.from_user.id
    
    # Set user state to waiting for anime name
    user_states[user_id] = "waiting_for_anime_name"
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    text = f"Please send the {ANIME} name you want to create:"
    
    await callback.message.edit_text(text, reply_markup=btn)

async def handle_anime_name_input(client: Client, message: Message):
    """Handle anime name input for creation"""
    user_id = message.from_user.id
    
    # Check if user is in anime name input state
    if user_id not in user_states or user_states[user_id] != "waiting_for_anime_name":
        return False
    
    try:
        anime_name = message.text.strip()
        
        if not anime_name or len(anime_name) < 2:
            await message.reply_text("❌ Anime name must be at least 2 characters long.")
            return True
        
        # Check if this is part of character upload or standalone anime creation
        if user_id in upload_details and "name" in upload_details[user_id]:
            # This is part of character upload - store anime name and continue
            upload_details[user_id]["anime"] = anime_name
            
            # Update user state and ask for rarity
            user_states[user_id] = "waiting_for_rarity"
            
            # Create rarity buttons using real rarities from database
            rarity_buttons = []
            for rarity_name, rarity_level in sorted(RARITIES.items(), key=lambda x: x[1]):
                emoji = RARITY_EMOJIS.get(rarity_name, "⭐")
                rarity_buttons.append([InlineKeyboardButton(f"{emoji} {rarity_name}", callback_data=f"glob_{rarity_name}")])
            
            rarity_buttons.append([InlineKeyboardButton("Cancel Upload", callback_data="close_upload")])
            rarity_keyboard = InlineKeyboardMarkup(rarity_buttons)
            
            await message.reply_text(
                f"✅ {ANIME} '{anime_name}' created and assigned!\n\nNow choose the rarity:",
                reply_markup=rarity_keyboard
            )
        else:
            # This is standalone anime creation - show confirmation
            confirmation_text = (
                f"<b>📝 {ANIME} Creation Confirmation</b>\n\n"
                f"⛩️ <b>Name:</b> {anime_name}\n\n"
                f"<b>Please confirm the {ANIME} creation:</b>"
            )
            
            confirm_buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm Creation", callback_data="confirm_anime_creation")],
                [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
            ])
            
            await message.reply_text(confirmation_text, reply_markup=confirm_buttons, parse_mode=ParseMode.HTML)
            
            # Store anime name temporarily
            if user_id not in upload_details:
                upload_details[user_id] = {}
            upload_details[user_id]["new_anime_name"] = anime_name
            
            # Update user state to waiting for confirmation
            user_states[user_id] = "waiting_for_anime_confirmation"
        
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True



async def confirm_anime_creation_handler(client: Client, callback_query: CallbackQuery):
    """Confirm the anime creation"""
    user_id = callback_query.from_user.id
    data = upload_details.get(user_id)
    
    if not data or "new_anime_name" not in data:
        await callback_query.message.reply_text("No anime creation data found")
        return

    try:
        anime_name = data["new_anime_name"]
        
        # Show processing message
        await callback_query.message.edit_text(f"<i>Processing {ANIME} creation and adding to database...</i>", parse_mode=ParseMode.HTML, reply_markup=None)
        
        # Get database connection
        db = get_database()
        
        # For anime, we don't need to insert into a separate table since anime names are stored in the characters table
        # But we can log the creation and show success message
        # Note: In a real implementation, you might want to create a separate anime table
        
        success_message = (
            f"✅ <b>{ANIME} Created Successfully!</b>\n\n"
            f"⛩️ <b>Name:</b> {anime_name}\n\n"
            f"<b>You can now use this {ANIME} when uploading characters!</b>\n\n"
            f"<i>Note: {ANIME} names are stored with characters in the database.</i>"
        )
        
        await callback_query.message.edit_text(success_message, parse_mode=ParseMode.HTML, reply_markup=None)
        
        # Log the creation to the log channel
        user_name = callback_query.from_user.first_name
        if callback_query.from_user.last_name:
            user_name += f" {callback_query.from_user.last_name}"
        
        log_text = (
            f"<b>✨ New {ANIME} Created by {callback_query.from_user.mention}!!</b>\n\n"
            f"⛩️ <b>Name:</b> {anime_name}\n"
            f"👤 <b>Created By:</b> {user_name} (ID: {user_id})"
        )
        
        await client.send_message(chat_id=LOG_CHANNEL, text=log_text, parse_mode=ParseMode.HTML)
        
        # Clean up user state and upload details
        if user_id in upload_details:
            del upload_details[user_id]
        if user_id in user_states:
            del user_states[user_id]
            
    except Exception as e:
        await callback_query.message.reply_text(f"Error during anime creation: {str(e)}")

async def rename_anime_handler(client, callback: CallbackQuery):
    """Handle renaming anime"""
    user_id = callback.from_user.id
    
    # Set user state to waiting for anime selection for rename
    user_states[user_id] = "waiting_for_rename_anime_selection"
    
    # Show inline query button for anime selection
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔍 Search {ANIME}s", switch_inline_query_current_chat=".anime ")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    text = f"Please select the {ANIME} you want to rename.\n\n"
    text += f"<b>🔍 Search existing {ANIME}s:</b>\n"
 
    
    await callback.message.edit_text(text, reply_markup=btn, parse_mode=ParseMode.HTML)

async def edit_character_handler(client, callback: CallbackQuery):
    """Handle editing character"""
    user_id = callback.from_user.id
    
    # Set user state to waiting for character selection
    user_states[user_id] = "waiting_for_edit_character_selection"
    
    # Show inline query button for character selection
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔍 Search {WAIFU}s", switch_inline_query_current_chat=".character ")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    text = f"Please select the {WAIFU} you want to edit.\n\n"
    text += f"<b>🔍 Search existing {WAIFU}s:</b>\n"
    
    await callback.message.edit_text(text, reply_markup=btn, parse_mode=ParseMode.HTML)

async def handle_edit_character_id_input(client: Client, message: Message):
    """Handle character ID input for editing"""
    user_id = message.from_user.id
    
    # Check if user is in edit character selection state
    if user_id not in user_states:
        return False
    if user_states[user_id] != "waiting_for_edit_character_selection":
        return False
    
    try:
        character_text = message.text.strip()
        
        # Check if this is an inline query result (contains character name and ID)
        if "🆔 ID:" in character_text:
            # Extract character name and ID from inline query result
            parts = character_text.split("🆔 ID:")
            character_name = parts[0].strip()
            character_id = parts[1].strip()
            
            if not character_id.isdigit():
                await message.reply_text("❌ Invalid character ID from selection.")
                return True
        else:
            # This is a direct text input - treat as character ID
            character_id = character_text
            
            if not character_id.isdigit():
                await message.reply_text("❌ Please send a valid numeric character ID or use the search function.")
                return True
        
        # Get database connection
        db = get_database()
        
        # Fetch character data
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Try both character_id and id fields
                result = await conn.fetchrow(
                    "SELECT character_id, name, anime, rarity, img_url, is_video FROM characters WHERE character_id = $1 OR id = $1",
                    int(character_id)
                )
        else:  # MongoDB
            result = await db.characters.find_one({"$or": [{"_id": int(character_id)}, {"character_id": int(character_id)}]})
        
        if not result:
            await message.reply_text(f"❌ {WAIFU} with ID {character_id} not found.")
            return True
        
        # Store character data for editing
        if user_id not in upload_details:
            upload_details[user_id] = {}
        
        upload_details[user_id]["edit_character"] = {
            "character_id": int(character_id),
            "name": result.get('name') or result.get('_id'),
            "anime": result.get('anime'),
            "rarity": result.get('rarity'),
            "img_url": result.get('img_url'),
            "is_video": result.get('is_video', False)
        }
        
        # Update user state to waiting for edit choice
        user_states[user_id] = "waiting_for_edit_choice"
        
        # Show edit options
        edit_text = (
            f"<b>✏️ Edit {WAIFU}</b>\n\n"
            f"🆔 <b>Pokémon ID:</b> {character_id}\n"
            f"🎀 <b>Name:</b> {upload_details[user_id]['edit_character']['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {upload_details[user_id]['edit_character']['anime']}\n"
            f"⭐ <b>Rarity:</b> {upload_details[user_id]['edit_character']['rarity']}\n\n"
            f"<b>What would you like to edit?</b>"
        )
        
        edit_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎀 Edit Name", callback_data="edit_name")],
            [InlineKeyboardButton(f"⛩️ Edit {ANIME}", callback_data="edit_anime")],
            [InlineKeyboardButton("⭐ Edit Rarity", callback_data="edit_rarity")],
            [InlineKeyboardButton("🖼️ Edit Image", callback_data="edit_image")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        
        await message.reply_text(edit_text, reply_markup=edit_buttons, parse_mode=ParseMode.HTML)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_edit_choice(client: Client, callback_query: CallbackQuery):
    """Handle edit choice selection"""
    user_id = callback_query.from_user.id
    
    if user_id not in upload_details or "edit_character" not in upload_details[user_id]:
        await callback_query.message.reply_text("❌ No character data found for editing.")
        return
    
    edit_type = callback_query.data
    character_data = upload_details[user_id]["edit_character"]
    
    if edit_type == "edit_name":
        user_states[user_id] = "waiting_for_edit_name"
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        await callback_query.message.edit_text(
            f"Current name: <b>{character_data['name']}</b>\n\nPlease send the new name:",
            reply_markup=btn,
            parse_mode=ParseMode.HTML
        )
    
    elif edit_type == "edit_anime":
        user_states[user_id] = "waiting_for_edit_anime"
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        await callback_query.message.edit_text(
            f"Current {ANIME}: <b>{character_data['anime']}</b>\n\nPlease send the new {ANIME} name:",
            reply_markup=btn,
            parse_mode=ParseMode.HTML
        )
    
    elif edit_type == "edit_rarity":
        user_states[user_id] = "waiting_for_edit_rarity"
        # Create rarity buttons using real rarities from database
        rarity_buttons = []
        for rarity_name, rarity_level in sorted(RARITIES.items(), key=lambda x: x[1]):
            emoji = RARITY_EMOJIS.get(rarity_name, "⭐")
            rarity_buttons.append([InlineKeyboardButton(f"{emoji} {rarity_name}", callback_data=f"edit_rarity_{rarity_name}")])
        
        rarity_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_upload")])
        rarity_keyboard = InlineKeyboardMarkup(rarity_buttons)
        
        await callback_query.message.edit_text(
            f"Current rarity: <b>{character_data['rarity']}</b>\n\nChoose the new rarity:",
            reply_markup=rarity_keyboard,
            parse_mode=ParseMode.HTML
        )
    
    elif edit_type == "edit_image":
        user_states[user_id] = "waiting_for_edit_image"
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        await callback_query.message.edit_text(
            f"Current image: {character_data['img_url']}\n\nPlease send the new image or video:",
            reply_markup=btn
        )

async def handle_edit_name_input(client: Client, message: Message):
    """Handle edit name input"""
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id] != "waiting_for_edit_name":
        return False
    
    try:
        new_name = message.text.strip()
        if not new_name or len(new_name) < 2:
            await message.reply_text("❌ Name must be at least 2 characters long.")
            return True
        
        upload_details[user_id]["edit_character"]["name"] = new_name
        user_states[user_id] = "waiting_for_edit_confirmation"
        
        await show_edit_confirmation(client, message, user_id)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_edit_anime_input(client: Client, message: Message):
    """Handle edit anime input"""
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id] != "waiting_for_edit_anime":
        return False
    
    try:
        new_anime = message.text.strip()
        if not new_anime or len(new_anime) < 2:
            await message.reply_text(f"❌ {ANIME} name must be at least 2 characters long.")
            return True
        
        upload_details[user_id]["edit_character"]["anime"] = new_anime
        user_states[user_id] = "waiting_for_edit_confirmation"
        
        await show_edit_confirmation(client, message, user_id)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_edit_rarity_selection(client: Client, callback_query: CallbackQuery):
    """Handle edit rarity selection"""
    user_id = callback_query.from_user.id
    
    if user_id not in user_states or user_states[user_id] != "waiting_for_edit_rarity":
        return
    
    try:
        rarity_key = callback_query.data.split("_")[2]  # edit_rarity_RARITY_NAME
        upload_details[user_id]["edit_character"]["rarity"] = rarity_key
        user_states[user_id] = "waiting_for_edit_confirmation"
        
        await show_edit_confirmation(client, callback_query.message, user_id)
        
    except Exception as e:
        await callback_query.message.reply_text(f"Error: {str(e)}")

async def handle_edit_image_upload(client: Client, message: Message):
    """Handle edit image upload"""
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id] != "waiting_for_edit_image":
        return False
    
    try:
        # Determine media type and get file_id
        if message.photo:
            media_type = "image"
            file_id = message.photo.file_id
            is_video = False
        elif message.video:
            media_type = "video"
            file_id = message.video.file_id
            is_video = True
        else:
            await message.reply_text("Please send a valid image or video file.")
            return True
        
        # Show processing message
        processing_msg = await message.reply_text(
            f"<i>Processing your {media_type} upload, please wait...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Upload based on media type
        if is_video:
            img_url = await upload_video_to_cloudinary(file_id, client)
        else:
            img_url = await upload_to_imgbb(file_id, client)
        
        if not img_url:
            await processing_msg.edit_text("Upload failed. Please try again.")
            return True
        
        # Update character data
        upload_details[user_id]["edit_character"]["img_url"] = img_url
        upload_details[user_id]["edit_character"]["is_video"] = is_video
        user_states[user_id] = "waiting_for_edit_confirmation"
        
        await show_edit_confirmation(client, message, user_id)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def show_edit_confirmation(client: Client, message_or_callback, user_id):
    """Show edit confirmation"""
    character_data = upload_details[user_id]["edit_character"]
    
    confirmation_text = (
        f"<b>✏️ Edit Confirmation</b>\n\n"
        f"🆔 <b>Pokémon ID:</b> {character_data['character_id']}\n"
        f"🎀 <b>Name:</b> {character_data['name']}\n"
        f"⛩️ <b>{ANIME}:</b> {character_data['anime']}\n"
        f"⭐ <b>Rarity:</b> {character_data['rarity']}\n"
        f"🖼️ <b>Image:</b> {character_data['img_url']}\n\n"
        f"<b>Please confirm your changes:</b>"
    )
    
    confirm_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm Edit", callback_data="confirm_edit")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    if hasattr(message_or_callback, 'reply_text'):
        await message_or_callback.reply_text(confirmation_text, reply_markup=confirm_buttons, parse_mode=ParseMode.HTML)
    else:
        await message_or_callback.edit_text(confirmation_text, reply_markup=confirm_buttons, parse_mode=ParseMode.HTML)

async def confirm_edit_handler(client: Client, callback_query: CallbackQuery):
    """Confirm the character edit"""
    user_id = callback_query.from_user.id
    data = upload_details.get(user_id, {}).get("edit_character")
    
    if not data:
        await callback_query.message.reply_text("No edit data found")
        return

    try:
        # Show processing message
        await callback_query.message.edit_text(f"<i>Processing edit and updating database...</i>", reply_markup=None, parse_mode=ParseMode.HTML)
        
        # Get database connection
        db = get_database()
        
        # Update character in database
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE characters 
                    SET name = $1, anime = $2, rarity = $3, img_url = $4, is_video = $5
                    WHERE character_id = $6
                    """,
                    data['name'],
                    data['anime'],
                    data['rarity'],
                    data['img_url'],
                    data['is_video'],
                    data['character_id']
                )
        else:  # MongoDB
            await db.characters.update_one(
                {"_id": data['character_id']},
                {
                    "$set": {
                        "name": data['name'],
                        "anime": data['anime'],
                        "rarity": data['rarity'],
                        "img_url": data['img_url'],
                        "is_video": data['is_video']
                    }
                }
            )
        
        # Show success message
        media_type_text = "Video Character" if data.get('is_video') else "Character"
        await callback_query.message.edit_text(
            f"✅ {WAIFU} successfully updated!\n\n"
            f"🆔 <b>Character ID:</b> {data['character_id']}\n"
            f"🎀 <b>Name:</b> {data['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {data['anime']}\n"
            f"⭐ <b>Rarity:</b> {data['rarity']}\n"
            f"🖼️ <b>Type:</b> {media_type_text}",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )
        
        # Clean up user state and upload details
        if user_id in upload_details:
            del upload_details[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        # Prepare log message
        text = f"<b>✏️ {WAIFU} Edited by {callback_query.from_user.mention}!!</b>\n\n"
        text += f"🆔 <b>Character ID:</b> {data['character_id']}\n"
        text += f"🎀 <b>Name :</b> {data['name']}\n"
        text += f"⛩️ <b>{ANIME} :</b> {data['anime']}\n"
        text += f"⭐ <b>Rarity</b> : {data['rarity']}\n"
        text += f"📹 <b>Type</b> : {media_type_text}\n"
        text += f"👤 <b>Edited By:</b> {callback_query.from_user.mention} (ID: {user_id})\n\n"
        
        # Send to log channel
        if data.get('is_video'):
            await client.send_video(chat_id=LOG_CHANNEL, video=data['img_url'], caption=text, parse_mode=ParseMode.HTML)
        else:
            await client.send_photo(chat_id=LOG_CHANNEL, photo=data['img_url'], caption=text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        error_msg = f"Error during edit: {str(e)}"
        print(f"Edit error: {error_msg}")
        await callback_query.message.edit_text(f"❌ {error_msg}", reply_markup=None)

async def delete_character_handler(client, callback: CallbackQuery):
    """Handle deleting character"""
    user_id = callback.from_user.id
    
    # Set user state to waiting for character selection for deletion
    user_states[user_id] = "waiting_for_delete_character_selection"
    
    # Show inline query button for character selection
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔍 Search {WAIFU}s", switch_inline_query_current_chat=".character ")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    text = f"Please select the {WAIFU} you want to delete.\n\n"
    text += f"<b>🔍 Search existing {WAIFU}s:</b>\n"
    text += f"• Click the 'Search {WAIFU}s' button below\n"
    
    await callback.message.edit_text(text, reply_markup=btn, parse_mode=ParseMode.HTML)

async def reset_character_handler(client, callback: CallbackQuery):
    """Handle resetting character"""
    user_id = callback.from_user.id
    
    # Set user state to waiting for character selection for reset
    user_states[user_id] = "waiting_for_reset_character_selection"
    
    # Show inline query button for character selection
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔍 Search {WAIFU}s", switch_inline_query_current_chat=".character ")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
    ])
    
    text = f"Please select the {WAIFU} you want to reset.\n\n"
    text += f"<b>🔍 Search existing {WAIFU}s:</b>\n"
    text += f"• Click the 'Search {WAIFU}s' button below\n"
    
    await callback.message.edit_text(text, reply_markup=btn, parse_mode=ParseMode.HTML)

async def handle_anime_inline_query(client: Client, inline_query: InlineQuery):
    """Handle inline query for anime search"""
    query = inline_query.query.strip()
    
    # Only handle anime queries
    if not query.startswith('.anime'):
        await inline_query.answer([], cache_time=1)
        return
    
    # Extract search term
    search_term = query.replace('.anime', '').strip()
    
    try:
        db = get_database()
        
        # Get unique anime names from existing characters
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                if search_term:
                    result = await conn.fetch(
                        "SELECT DISTINCT anime FROM characters WHERE anime IS NOT NULL AND anime != '' AND anime ILIKE $1 ORDER BY anime LIMIT 20",
                        f"%{search_term}%"
                    )
                else:
                    result = await conn.fetch(
                        "SELECT DISTINCT anime FROM characters WHERE anime IS NOT NULL AND anime != '' ORDER BY anime LIMIT 20"
                    )
                unique_animes = [row['anime'] for row in result]
        else:  # MongoDB
            if search_term:
                pipeline = [
                    {"$match": {"anime": {"$exists": True, "$ne": None, "$ne": "", "$regex": search_term, "$options": "i"}}},
                    {"$group": {"_id": "$anime"}},
                    {"$sort": {"_id": 1}},
                    {"$limit": 20}
                ]
            else:
                pipeline = [
                    {"$match": {"anime": {"$exists": True, "$ne": None, "$ne": ""}}},
                    {"$group": {"_id": "$anime"}},
                    {"$sort": {"_id": 1}},
                    {"$limit": 20}
                ]
            cursor = db.characters.aggregate(pipeline)
            unique_animes = [doc['_id'] async for doc in cursor]
        
        # Create inline query results
        results = []
        for anime_name in unique_animes:
            results.append(
                InlineQueryResultArticle(
                    id=f"anime_{anime_name}",
                    title=anime_name,
                    description=f"Select this {ANIME} for your character",
                    input_message_content=InputTextMessageContent(
                        message_text=f"{anime_name} 🆔 ID: {hash(anime_name) % 10000}"
                    )
                )
            )
        
        # Add option to create new anime if no results or if searching
        if not results or search_term:
            results.append(
                InlineQueryResultArticle(
                    id="create_new_anime",
                    title=f"➕ Create New {ANIME}: {search_term if search_term else 'Enter name'}" if search_term else f"➕ Create New {ANIME}",
                    description=f"Create a new {ANIME} with this name",
                    input_message_content=InputTextMessageContent(
                        message_text=search_term if search_term else f"New {ANIME} name"
                    )
                )
            )
        
        await inline_query.answer(results, cache_time=300)
        
    except Exception as e:
        print(f"Error in anime inline query: {e}")
        await inline_query.answer([], cache_time=1)

async def handle_character_inline_query(client: Client, inline_query: InlineQuery):
    """Handle inline query for character search"""
    query = inline_query.query.strip()
    
    # Only handle character queries
    if not query.startswith('.character'):
        await inline_query.answer([], cache_time=1)
        return
    
    # Extract search term
    search_term = query.replace('.character', '').strip()
    
    try:
        db = get_database()
        
        # Get characters from database with image URLs
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                if search_term:
                    result = await conn.fetch(
                        "SELECT character_id, name, anime, rarity, img_url, is_video FROM characters WHERE name ILIKE $1 OR anime ILIKE $1 ORDER BY name LIMIT 20",
                        f"%{search_term}%"
                    )
                else:
                    result = await conn.fetch(
                        "SELECT character_id, name, anime, rarity, img_url, is_video FROM characters ORDER BY name LIMIT 50"
                    )
                characters = [{"character_id": row['character_id'], "name": row['name'], "anime": row['anime'], "rarity": row['rarity'], "img_url": row['img_url'], "is_video": row['is_video']} for row in result]
        else:  # MongoDB
            if search_term:
                cursor = db.characters.find(
                    {"$or": [{"name": {"$regex": search_term, "$options": "i"}}, {"anime": {"$regex": search_term, "$options": "i"}}]},
                    {"_id": 1, "name": 1, "anime": 1, "rarity": 1, "img_url": 1, "is_video": 1}
                ).limit(50)
            else:
                cursor = db.characters.find({}, {"_id": 1, "name": 1, "anime": 1, "rarity": 1, "img_url": 1, "is_video": 1}).limit(50)
            characters = [{"character_id": doc['_id'], "name": doc['name'], "anime": doc['anime'], "rarity": doc['rarity'], "img_url": doc.get('img_url'), "is_video": doc.get('is_video', False)} async for doc in cursor]
        
        # Create inline query results as text articles for character selection
        results = []
        for char in characters:
            rarity_emoji = RARITY_EMOJIS.get(char['rarity'], "⭐")
            media_type = "Video" if char.get('is_video') else "Image"
            
            # Create text message for character selection
            message_text = f"{char['name']} 🆔 ID: {char['character_id']}"
            
            results.append(
                InlineQueryResultArticle(
                    id=f"character_{char['character_id']}",
                    title=f"{char['name']} ({char['anime']})",
                    description=f"{rarity_emoji} {char['rarity']} • ID: {char['character_id']} • {media_type}",
                    input_message_content=InputTextMessageContent(
                        message_text=message_text
                    )
                )
            )
        
        await inline_query.answer(results, cache_time=300)
        
    except Exception as e:
        print(f"Error in character inline query: {e}")
        await inline_query.answer([], cache_time=1)

async def handle_rename_anime_input(client: Client, message: Message):
    """Handle anime input for renaming"""
    user_id = message.from_user.id
    
    # Check if user is in rename anime selection state
    if user_id not in user_states:
        return False
    if user_states[user_id] != "waiting_for_rename_anime_selection":
        return False
    
    try:
        anime_text = message.text.strip()
        
        # Check if this is an inline query result (contains anime name and ID)
        if "🆔 ID:" in anime_text:
            # Extract anime name and ID from inline query result
            parts = anime_text.split("🆔 ID:")
            anime_name = parts[0].strip()
            anime_id = parts[1].strip()
            
            # Store the anime name (not the ID, since we want the name)
            old_anime_name = anime_name
        else:
            # This is a direct text input - treat as anime name
            old_anime_name = anime_text
        
        # Store anime data for rename confirmation
        if user_id not in upload_details:
            upload_details[user_id] = {}
        
        upload_details[user_id]["rename_anime"] = {
            "old_name": old_anime_name
        }
        
        # Update user state to waiting for new anime name
        user_states[user_id] = "waiting_for_new_anime_name"
        
        # Show prompt for new anime name
        rename_text = (
            f"<b>✏️ Rename {ANIME}</b>\n\n"
            f"⛩️ <b>Current {ANIME} Name:</b> {old_anime_name}\n\n"
            f"<b>Please send the new {ANIME} name:</b>"
        )
        
        rename_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        
        await message.reply_text(rename_text, reply_markup=rename_buttons, parse_mode=ParseMode.HTML)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_new_anime_name_input(client: Client, message: Message):
    """Handle new anime name input for rename"""
    user_id = message.from_user.id
    
    # Check if user is in new anime name input state
    if user_id not in user_states:
        return False
    if user_states[user_id] != "waiting_for_new_anime_name":
        return False
    
    try:
        new_anime_name = message.text.strip()
        
        if not new_anime_name or len(new_anime_name) < 2:
            await message.reply_text(f"❌ {ANIME} name must be at least 2 characters long.")
            return True
        
        # Get the old anime name from stored data
        if user_id not in upload_details or "rename_anime" not in upload_details[user_id]:
            await message.reply_text("❌ No anime data found for renaming.")
            return True
        
        old_anime_name = upload_details[user_id]["rename_anime"]["old_name"]
        upload_details[user_id]["rename_anime"]["new_name"] = new_anime_name
        
        # Update user state to waiting for rename confirmation
        user_states[user_id] = "waiting_for_rename_confirmation"
        
        # Show rename confirmation
        rename_text = (
            f"<b>✏️ Rename {ANIME} Confirmation</b>\n\n"
            f"⛩️ <b>Old {ANIME} Name:</b> {old_anime_name}\n"
            f"⛩️ <b>New {ANIME} Name:</b> {new_anime_name}\n\n"
            f"<b>⚠️ This will update all characters with the old {ANIME} name!</b>\n\n"
            f"<b>Please confirm the rename:</b>"
        )
        
        rename_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Rename", callback_data="confirm_rename_anime")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        
        await message.reply_text(rename_text, reply_markup=rename_buttons, parse_mode=ParseMode.HTML)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_reset_character_id_input(client: Client, message: Message):
    """Handle character ID input for reset"""
    user_id = message.from_user.id
    
    # Check if user is in reset character selection state
    if user_id not in user_states:
        return False
    if user_states[user_id] != "waiting_for_reset_character_selection":
        return False
    
    try:
        character_text = message.text.strip()
        
        # Check if this is an inline query result (contains character name and ID)
        if "🆔 ID:" in character_text:
            # Extract character name and ID from inline query result
            parts = character_text.split("🆔 ID:")
            character_name = parts[0].strip()
            character_id = parts[1].strip()
            
            if not character_id.isdigit():
                await message.reply_text("❌ Invalid character ID from selection.")
                return True
        else:
            # This is a direct text input - treat as character ID
            character_id = character_text
            
            if not character_id.isdigit():
                await message.reply_text("❌ Please send a valid numeric character ID or use the search function.")
                return True
        
        # Get database connection
        db = get_database()
        
        # Fetch character data
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Try both character_id and id fields
                result = await conn.fetchrow(
                    "SELECT character_id, name, anime, rarity, img_url, is_video FROM characters WHERE character_id = $1 OR id = $1",
                    int(character_id)
                )
        else:  # MongoDB
            result = await db.characters.find_one({"$or": [{"_id": int(character_id)}, {"character_id": int(character_id)}]})
        
        if not result:
            await message.reply_text(f"❌ {WAIFU} with ID {character_id} not found.")
            return True
        
        # Store character data for reset confirmation
        if user_id not in upload_details:
            upload_details[user_id] = {}
        
        upload_details[user_id]["reset_character"] = {
            "character_id": int(character_id),
            "name": result.get('name') or result.get('_id'),
            "anime": result.get('anime'),
            "rarity": result.get('rarity'),
            "img_url": result.get('img_url'),
            "is_video": result.get('is_video', False)
        }
        
        # Update user state to waiting for reset confirmation
        user_states[user_id] = "waiting_for_reset_confirmation"
        
        # Show reset confirmation
        character_data = upload_details[user_id]["reset_character"]
        rarity_emoji = RARITY_EMOJIS.get(character_data['rarity'], "⭐")
        media_type = "Video" if character_data.get('is_video') else "Image"
        
        reset_text = (
            f"<b>🔄 Reset {WAIFU} Confirmation</b>\n\n"
            f"🆔 <b>Character ID:</b> {character_id}\n"
            f"🎀 <b>Name:</b> {character_data['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {character_data['anime']}\n"
            f"{rarity_emoji} <b>Rarity:</b> {character_data['rarity']}\n"
            f"<b>⚠️ Are you sure you want to reset this {WAIFU}?</b>"
        )
        
        reset_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Confirm Reset", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        
        await message.reply_text(reset_text, reply_markup=reset_buttons, parse_mode=ParseMode.HTML)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def handle_delete_character_id_input(client: Client, message: Message):
    """Handle character ID input for deletion"""
    user_id = message.from_user.id
    
    # Check if user is in delete character selection state
    if user_id not in user_states:
        return False
    if user_states[user_id] != "waiting_for_delete_character_selection":
        return False
    
    try:
        character_text = message.text.strip()
        
        # Check if this is an inline query result (contains character name and ID)
        if "🆔 ID:" in character_text:
            # Extract character name and ID from inline query result
            parts = character_text.split("🆔 ID:")
            character_name = parts[0].strip()
            character_id = parts[1].strip()
            
            if not character_id.isdigit():
                await message.reply_text("❌ Invalid character ID from selection.")
                return True
        else:
            # This is a direct text input - treat as character ID
            character_id = character_text
            
            if not character_id.isdigit():
                await message.reply_text("❌ Please send a valid numeric character ID or use the search function.")
                return True
        
        # Get database connection
        db = get_database()
        
        # Fetch character data
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Try both character_id and id fields
                result = await conn.fetchrow(
                    "SELECT character_id, name, anime, rarity, img_url, is_video FROM characters WHERE character_id = $1 OR id = $1",
                    int(character_id)
                )
        else:  # MongoDB
            result = await db.characters.find_one({"$or": [{"_id": int(character_id)}, {"character_id": int(character_id)}]})
        
        if not result:
            await message.reply_text(f"❌ {WAIFU} with ID {character_id} not found.")
            return True
        
        # Store character data for deletion confirmation
        if user_id not in upload_details:
            upload_details[user_id] = {}
        
        upload_details[user_id]["delete_character"] = {
            "character_id": int(character_id),
            "name": result.get('name') or result.get('_id'),
            "anime": result.get('anime'),
            "rarity": result.get('rarity'),
            "img_url": result.get('img_url'),
            "is_video": result.get('is_video', False)
        }
        
        # Update user state to waiting for delete confirmation
        user_states[user_id] = "waiting_for_delete_confirmation"
        
        # Show delete confirmation
        character_data = upload_details[user_id]["delete_character"]
        rarity_emoji = RARITY_EMOJIS.get(character_data['rarity'], "⭐")
        media_type = "Video" if character_data.get('is_video') else "Image"
        
        delete_text = (
            f"<b>🗑️ Delete {WAIFU} Confirmation</b>\n\n"
            f"🆔 <b>Character ID:</b> {character_id}\n"
            f"🎀 <b>Name:</b> {character_data['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {character_data['anime']}\n"
            f"{rarity_emoji} <b>Rarity:</b> {character_data['rarity']}\n"
            f"📹 <b>Type:</b> {media_type}\n\n"
            f"<b>⚠️ Are you sure you want to delete this {WAIFU}?</b>\n"
            f"<b>This action cannot be undone!</b>"
        )
        
        delete_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Confirm Delete", callback_data="confirm_delete")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_upload")]
        ])
        
        await message.reply_text(delete_text, reply_markup=delete_buttons, parse_mode=ParseMode.HTML)
        return True
        
    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
        return True

async def confirm_delete_handler(client: Client, callback_query: CallbackQuery):
    """Confirm the character deletion"""
    user_id = callback_query.from_user.id
    data = upload_details.get(user_id, {}).get("delete_character")
    
    if not data:
        await callback_query.message.reply_text("No delete data found")
        return

    try:
        # Show processing message
        await callback_query.message.edit_text(f"<i>Processing deletion and removing from database...</i>", reply_markup=None, parse_mode=ParseMode.HTML)
        
        # Get database connection
        db = get_database()
        
        # Delete character from database
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # First check if character exists
                result = await conn.fetchrow(
                    "SELECT character_id FROM characters WHERE character_id = $1",
                    data['character_id']
                )
                
                if not result:
                    await callback_query.message.edit_text(f"❌ {WAIFU} not found in database.", reply_markup=None)
                    return
                
                # Delete the character
                await conn.execute(
                    "DELETE FROM characters WHERE character_id = $1",
                    data['character_id']
                )
        else:  # MongoDB
            # First check if character exists
            result = await db.characters.find_one({"_id": data['character_id']})
            
            if not result:
                await callback_query.message.edit_text(f"❌ {WAIFU} not found in database.", reply_markup=None)
                return
            
            # Delete the character
            await db.characters.delete_one({"_id": data['character_id']})
        
        # Show success message
        media_type_text = "Video Character" if data.get('is_video') else "Character"
        await callback_query.message.edit_text(
            f"✅ {WAIFU} successfully deleted!\n\n"
            f"🆔 <b>Character ID:</b> {data['character_id']}\n"
            f"🎀 <b>Name:</b> {data['name']}\n"
            f"⛩️ <b>{ANIME}:</b> {data['anime']}\n"
            f"⭐ <b>Rarity:</b> {data['rarity']}\n"
            f"🖼️ <b>Type:</b> {media_type_text}\n\n"
            f"<b>The {WAIFU} has been permanently removed from the database.</b>",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )
        
        # Clean up user state and upload details
        if user_id in upload_details:
            del upload_details[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        # Prepare log message
        text = f"<b>🗑️ {WAIFU} Deleted by {callback_query.from_user.mention}!!</b>\n\n"
        text += f"🆔 <b>Character ID:</b> {data['character_id']}\n"
        text += f"🎀 <b>Name :</b> {data['name']}\n"
        text += f"⛩️ <b>{ANIME} :</b> {data['anime']}\n"
        text += f"⭐ <b>Rarity</b> : {data['rarity']}\n"
        text += f"📹 <b>Type</b> : {media_type_text}\n"
        text += f"👤 <b>Deleted By:</b> {callback_query.from_user.mention} (ID: {user_id})\n\n"
        text += f"<b>⚠️ This {WAIFU} has been permanently removed!</b>"
        
        # Send to log channel
        await client.send_message(chat_id=LOG_CHANNEL, text=text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        error_msg = f"Error during deletion: {str(e)}"
        print(f"Delete error: {error_msg}")
        await callback_query.message.edit_text(f"❌ {error_msg}", reply_markup=None)

async def confirm_reset_handler(client: Client, callback_query: CallbackQuery):
    """Confirm the character reset"""
    user_id = callback_query.from_user.id
    data = upload_details.get(user_id, {}).get("reset_character")
    
    if not data:
        await callback_query.message.reply_text("No reset data found")
        return

    try:
        # Show processing message
        await callback_query.message.edit_text(f"<i>Processing reset and removing from all collections...</i>", reply_markup=None, parse_mode=ParseMode.HTML)
        
        # Get database connection
        db = get_database()
        
        # Remove character from all user collections
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # First check if character exists
                result = await conn.fetchrow(
                    "SELECT character_id FROM characters WHERE character_id = $1",
                    data['character_id']
                )
                
                if not result:
                    await callback_query.message.edit_text(f"❌ {WAIFU} not found in database.", reply_markup=None)
                    return
                
                # Get initial count of users who have this character
                initial_count = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM users WHERE $1 = ANY(characters)",
                    data['character_id']
                )
                initial_users = initial_count['count'] if initial_count else 0
                
                print(f"[RESET DEBUG] Character {data['character_id']} found in {initial_users} users initially")
                
                if initial_users > 0:
                    # Remove character from all users' characters arrays
                    # This removes ALL instances of the character from all users
                    updated_count = await conn.execute(
                        "UPDATE users SET characters = array_remove(characters, $1) WHERE $1 = ANY(characters)",
                        data['character_id']
                    )
                    
                    print(f"[RESET DEBUG] First removal affected {updated_count} users")
                    
                    # Get the number of users who still have this character
                    users_with_character = await conn.fetchrow(
                        "SELECT COUNT(*) as count FROM users WHERE $1 = ANY(characters)",
                        data['character_id']
                    )
                    remaining_users = users_with_character['count'] if users_with_character else 0
                    
                    print(f"[RESET DEBUG] After first removal: {remaining_users} users still have character")
                    
                    # Double-check: remove any remaining instances (in case of duplicates)
                    iteration = 1
                    while remaining_users > 0 and iteration <= 5:  # Limit iterations to prevent infinite loop
                        await conn.execute(
                            "UPDATE users SET characters = array_remove(characters, $1) WHERE $1 = ANY(characters)",
                            data['character_id']
                        )
                        
                        users_with_character = await conn.fetchrow(
                            "SELECT COUNT(*) as count FROM users WHERE $1 = ANY(characters)",
                            data['character_id']
                        )
                        remaining_users = users_with_character['count'] if users_with_character else 0
                        
                        print(f"[RESET DEBUG] Iteration {iteration}: {remaining_users} users still have character")
                        iteration += 1
                        
                        if iteration > 5:
                            print(f"[RESET WARNING] Reached maximum iterations for character {data['character_id']}")
                            break
                else:
                    print(f"[RESET DEBUG] Character {data['character_id']} not found in any user collections")
        else:  # MongoDB
            # First check if character exists
            result = await db.characters.find_one({"_id": data['character_id']})
            
            if not result:
                await callback_query.message.edit_text(f"❌ {WAIFU} not found in database.", reply_markup=None)
                return
            
            # Remove from all user collections
            deleted_count = await db.user_characters.delete_many({"character_id": data['character_id']})
            deleted_count = deleted_count.deleted_count
        
        # Show success message
        media_type_text = "Video Character" if data.get('is_video') else "Character"
        
        # Get the final count of users who still have this character (should be 0)
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                final_check = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM users WHERE $1 = ANY(characters)",
                    data['character_id']
                )
                final_count = final_check['count'] if final_check else 0
        else:  # MongoDB
            final_count = 0
        
        # Create detailed reset summary
        reset_summary = f"✅ {WAIFU} successfully reset!\n\n"
        reset_summary += f"🆔 <b>Character ID:</b> {data['character_id']}\n"
        reset_summary += f"🎀 <b>Name:</b> {data['name']}\n"
        reset_summary += f"⛩️ <b>{ANIME}:</b> {data['anime']}\n"
        reset_summary += f"⭐ <b>Rarity:</b> {data['rarity']}\n"
        reset_summary += f"🖼️ <b>Type:</b> {media_type_text}\n\n"
        reset_summary += f"<b>🔄 Reset Summary:</b>\n"
        
        if hasattr(db, 'pool'):  # PostgreSQL
            reset_summary += f"• Initially found in: {initial_users} users\n"
            reset_summary += f"• Final check: {final_count} users still have this character\n"
        else:
            reset_summary += f"• Removed from all user collections\n"
        
        reset_summary += f"• {WAIFU} is now available for collection again\n"
        reset_summary += f"• Users can collect it through drops, store, etc."
        
        await callback_query.message.edit_text(
            reset_summary,
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )
        
        # Clean up user state and upload details
        if user_id in upload_details:
            del upload_details[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        # Prepare log message
        text = f"<b>🔄 {WAIFU} Reset by {callback_query.from_user.mention}!!</b>\n\n"
        text += f"🆔 <b>Character ID:</b> {data['character_id']}\n"
        text += f"🎀 <b>Name :</b> {data['name']}\n"
        text += f"⛩️ <b>{ANIME} :</b> {data['anime']}\n"
        text += f"⭐ <b>Rarity</b> : {data['rarity']}\n"
        text += f"📹 <b>Type</b> : {media_type_text}\n"
        text += f"👤 <b>Reset By:</b> {callback_query.from_user.mention} (ID: {user_id})\n\n"
        text += f"<b>🔄 This {WAIFU} is now available for collection again!</b>"
        
        # Send to log channel
        await client.send_message(chat_id=LOG_CHANNEL, text=text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        error_msg = f"Error during reset: {str(e)}"
        print(f"Reset error: {error_msg}")
        await callback_query.message.edit_text(f"❌ {error_msg}", reply_markup=None)

async def confirm_rename_anime_handler(client: Client, callback_query: CallbackQuery):
    """Confirm the anime rename"""
    user_id = callback_query.from_user.id
    data = upload_details.get(user_id, {}).get("rename_anime")
    
    if not data:
        await callback_query.message.reply_text("No rename data found")
        return

    try:
        old_name = data["old_name"]
        new_name = data["new_name"]
        
        # Show processing message
        await callback_query.message.edit_text(f"<i>Processing rename and updating database...</i>", reply_markup=None, parse_mode=ParseMode.HTML)
        
        # Get database connection
        db = get_database()
        
        # Update all characters with the old anime name
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # First check if old anime exists
                result = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM characters WHERE anime = $1",
                    old_name
                )
                
                if not result or result['count'] == 0:
                    await callback_query.message.edit_text(f"❌ No characters found with {ANIME} name '{old_name}'.", reply_markup=None)
                    return
                
                # Update all characters with the old anime name
                updated_count = await conn.execute(
                    "UPDATE characters SET anime = $1 WHERE anime = $2",
                    new_name, old_name
                )
        else:  # MongoDB
            # First check if old anime exists
            count = await db.characters.count_documents({"anime": old_name})
            
            if count == 0:
                await callback_query.message.edit_text(f"❌ No characters found with {ANIME} name '{old_name}'.", reply_markup=None)
                return
            
            # Update all characters with the old anime name
            result = await db.characters.update_many(
                {"anime": old_name},
                {"$set": {"anime": new_name}}
            )
            updated_count = result.modified_count
        
        # Show success message
        await callback_query.message.edit_text(
            f"✅ {ANIME} successfully renamed!\n\n"
            f"⛩️ <b>Old {ANIME} Name:</b> {old_name}\n"
            f"⛩️ <b>New {ANIME} Name:</b> {new_name}\n"
            f"📊 <b>Characters Updated:</b> {updated_count}\n\n"
            f"<b>All characters with the old {ANIME} name have been updated!</b>",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )
        
        # Clean up user state and upload details
        if user_id in upload_details:
            del upload_details[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        # Prepare log message
        text = f"<b>✏️ {ANIME} Renamed by {callback_query.from_user.mention}!!</b>\n\n"
        text += f"⛩️ <b>Old {ANIME} Name:</b> {old_name}\n"
        text += f"⛩️ <b>New {ANIME} Name:</b> {new_name}\n"
        text += f"📊 <b>Characters Updated:</b> {updated_count}\n"
        text += f"👤 <b>Renamed By:</b> {callback_query.from_user.mention} (ID: {user_id})\n\n"
        text += f"<b>All characters with the old {ANIME} name have been updated!</b>"
        
        # Send to log channel
        await client.send_message(chat_id=LOG_CHANNEL, text=text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        error_msg = f"Error during rename: {str(e)}"
        print(f"Rename error: {error_msg}")
        await callback_query.message.edit_text(f"❌ {error_msg}", reply_markup=None)

def register_upload_handlers(app: Client):
    """Register all upload-related handlers"""
    # Admin panel message handler - works with exact emoji text
    app.add_handler(filters.regex("⚙ Admin Panel ⚙") & filters.private, handle_admin_panel)
    
    # Also add a command-based way to access admin panel
    app.add_handler(filters.command("admin", prefixes=["/", ".", "!"]) & filters.private, handle_admin_panel)
    
    # Media upload handler
    app.add_handler(filters.photo | filters.video & filters.private, handle_media_upload)
    
    # Text message handlers for conversation flow
    app.add_handler(filters.text & filters.private, handle_name_input)
    app.add_handler(filters.text & filters.private, handle_anime_input)
    app.add_handler(filters.text & filters.private, handle_anime_name_input)
    app.add_handler(filters.text & filters.private, handle_edit_character_id_input)
    app.add_handler(filters.text & filters.private, handle_edit_name_input)
    app.add_handler(filters.text & filters.private, handle_edit_anime_input)
    app.add_handler(filters.text & filters.private, handle_delete_character_id_input)
    app.add_handler(filters.text & filters.private, handle_reset_character_id_input)
    app.add_handler(filters.text & filters.private, handle_rename_anime_input)
    
    # Inline query handlers
    app.add_handler(filters.create(lambda _, __, inline_query: inline_query.query.startswith('.anime')), handle_anime_inline_query)
    app.add_handler(filters.create(lambda _, __, inline_query: inline_query.query.startswith('.character')), handle_character_inline_query)
    
    # Callback query handlers using the correct filter syntax
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "add_waifu"), start_character_upload)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data.startswith("glob_")), handle_rarity_selection)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "glob_confirm"), confirm_upload_handler)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "close_upload"), close_upload_handler)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "xxx"), close_admin_panel)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "add_anime"), add_anime_handler)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "rename_anime"), rename_anime_handler)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "edit_character"), edit_character_handler)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "delete_character"), delete_character_handler)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_anime_creation"), confirm_anime_creation_handler)
    
    # Edit character callback handlers
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data in ["edit_name", "edit_anime", "edit_rarity", "edit_image"]), handle_edit_choice)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data.startswith("edit_rarity_")), handle_edit_rarity_selection)
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_edit"), confirm_edit_handler)
    
    # Delete character callback handlers
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_delete"), confirm_delete_handler)
    
    # Reset character callback handlers
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_reset"), confirm_reset_handler)
    
    # Rename anime callback handlers
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_rename_anime"), confirm_rename_anime_handler)
    
    # Media handlers for edit image
    app.add_handler(filters.photo & filters.private, handle_edit_image_upload)
    app.add_handler(filters.video & filters.private, handle_edit_image_upload)
 
    app.add_handler(filters.create(lambda _, __, callback_query: callback_query.data == "create_anime"), create_anime_from_upload_handler)


