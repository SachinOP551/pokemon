from pyrogram import Client, filters
from pyrogram.types import Message
from .decorators import admin_only, is_owner, is_og, is_sudo
import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
import aiohttp
import asyncio
import cloudinary
import cloudinary.uploader
from modules.postgres_database import get_database

# Configure Cloudinary (replace with your credentials)
cloudinary.config(
    cloud_name="de96qtqav",
    api_key="755161292211756",
    api_secret="vO_1lOfhJQs3kI4C5v1E8fywYW8"
)

# Rarity data with emojis
RARITIES = {
    "Common": {"emoji": "⚪️", "level": 1},
    "Medium": {"emoji": "🟢", "level": 2},
    "Rare": {"emoji": "🟠", "level": 3},
    "Legendary": {"emoji": "🟡", "level": 4},
    "Exclusive": {"emoji": "🫧", "level": 5},
    "Elite": {"emoji": "💎", "level": 6},
    "Limited Edition": {"emoji": "🔮", "level": 7},
    "Ultimate": {"emoji": "🔱", "level": 8},
    "Supreme": {"emoji": "👑", "level": 9},
    "Mythic": {"emoji": "🔴", "level": 10},
    "Zenith": {"emoji": "💫", "level": 11},
    "Ethereal": {"emoji": "❄️", "level": 12},
    "Premium": {"emoji": "🧿", "level": 13},
}

# Helper for markdown v2 escaping (legacy, for migration)
def escape_markdown(text, version=2):
    if not text:
        return ''
    return str(text).replace('_', '\_').replace('*', '\*').replace('[', '\[').replace('`', '\`')

@admin_only
async def vadd_command(client: Client, message: Message):
    user_id = message.from_user.id
    # Must be a reply to a video
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply_text("<b>❌ Please reply to a video with /vadd &lt;name&gt; &lt;rarity&gt;.</b>")
        return
    # Parse arguments
    parts = message.text.split()[1:]  # remove command itself
    if len(parts) < 2:
        await message.reply_text("❌ Usage: /vadd <name> <rarity> (as a reply to a video)")
        return

    # Try to match the longest possible rarity from the end
    matched_rarity = None
    for i in range(1, min(3, len(parts)) + 1):  # check last 1, 2, or 3 words
        candidate = " ".join(parts[-i:]).strip()
        for r in RARITIES:
            if candidate.lower() == r.lower():
                matched_rarity = r
                name = " ".join(parts[:-i]).strip()
                break
        if matched_rarity:
            break

    if not matched_rarity or not name:
        await message.reply_text(f"❌ Invalid rarity! Choose one of: {' | '.join(RARITIES.keys())}")
        return
    # Validate name
    if len(name) < 2 or len(name) > 50:
        await message.reply_text("<b>❌ Name must be between 2 and 50 characters.</b>")
        return
    # Show processing message
    processing_msg = await message.reply_text("<i>Processing your video upload, please wait...</i>")
    # Download video file
    try:
        import asyncio
        file = await asyncio.wait_for(client.download_media(message.reply_to_message.video.file_id), timeout=120)
    except asyncio.TimeoutError:
        await processing_msg.edit_text("<b>❌ Timeout downloading video from Telegram (120 seconds exceeded).</b>")
        return
    except Exception as e:
        await processing_msg.edit_text("<b>❌ Failed to download video from Telegram.</b>")
        return
    # Upload to Cloudinary
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: cloudinary.uploader.upload(file, resource_type="video")
        )
        video_url = result["secure_url"]
    except Exception as e:
        await processing_msg.edit_text(f"<b>❌ Failed to upload video to Cloudinary. {e}</b>")
        return
    db = get_database()
    # Add to DB
    char_data = {
        "name": name,
        "rarity": matched_rarity,
        "file_id": message.reply_to_message.video.file_id,
        "img_url": video_url,
        "is_video": True,
        "added_by": user_id
    }
    inserted_id = await db.add_character(char_data)
    char = await db.characters.find_one({"_id": inserted_id})
    char_id = char.get("character_id", inserted_id)
    rarity_emoji = RARITIES[matched_rarity]["emoji"]
    caption = (
        f"<b>✅ Video character added!</b>\n\n"
        f"<b>🆔 ID:</b> <code>{char_id}</code>\n"
        f"<b>👤 Name:</b> {name}\n"
        f"<b>✨ Rarity:</b> {rarity_emoji} {matched_rarity}\n"
        f"<b>🌐 Video URL:</b> <a href='{video_url}'>cloudinary</a>"
    )
    await processing_msg.delete()
    await message.reply_video(
        video=video_url,
        caption=caption
    )

@admin_only
async def vedit_command(client: Client, message: Message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("❌ Usage: /vedit <id> [new_name] (as a reply to a new video to update video, or provide new_name to update name)")
        return
    char_id_str = parts[1]
    try:
        char_id = int(char_id_str)
    except ValueError:
        await message.reply_text("❌ Character ID must be a number.")
        return
    db = get_database()
    char = await db.characters.find_one({"character_id": char_id})
    if not char:
        await message.reply_text("❌ Character not found with the given ID.")
        return
    # Case 1: Edit video (reply to a video, only <id> provided)
    if message.reply_to_message and message.reply_to_message.video and len(parts) == 2:
        processing_msg = await message.reply_text("<i>Updating the video, please wait...</i>")
        try:
            import asyncio
            file = await asyncio.wait_for(client.download_media(message.reply_to_message.video.file_id), timeout=120)
        except asyncio.TimeoutError:
            await processing_msg.edit_text("<b>❌ Timeout downloading new video from Telegram (120 seconds exceeded).</b>")
            return
        except Exception as e:
            await processing_msg.edit_text("<b>❌ Failed to download new video from Telegram.</b>")
            return
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: cloudinary.uploader.upload(file, resource_type="video")
            )
            video_url = result["secure_url"]
        except Exception as e:
            await processing_msg.edit_text(f"<b>❌ Failed to upload new video to Cloudinary. {e}</b>")
            return
        await db.characters.update_one(
            {"_id": char["_id"]},
            {"$set": {"img_url": video_url, "file_id": message.reply_to_message.video.file_id}}
        )
        await processing_msg.delete()
        await message.reply_text(f"✅ Video updated for character <b>{char.get('name', char_id)}</b>! New video uploaded.")
        return
    # Case 2: Edit name (not a reply to a video, <id> and <new_name> provided)
    elif len(parts) >= 3:
        new_name = " ".join(parts[2:]).strip()
        if len(new_name) < 2 or len(new_name) > 50:
            await message.reply_text("<b>❌ Name must be between 2 and 50 characters.</b>")
            return
        await db.characters.update_one(
            {"_id": char["_id"]},
            {"$set": {"name": new_name}}
        )
        await message.reply_text(f"✅ Name updated for character <b>{char_id}</b>! New name: <b>{new_name}</b>.")
        return
    else:
        await message.reply_text("❌ Usage: /vedit <id> [new_name] (as a reply to a new video to update video, or provide new_name to update name)")
        return

# Register handler

def register_vid_handlers(app: Client):
    app.add_handler(filters.command("vadd") & filters.reply, vadd_command)
    app.add_handler(filters.command("vedit") & filters.reply, vedit_command)
