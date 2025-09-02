from pyrogram import Client, filters
from pyrogram.types import Message
from datetime import datetime, timedelta
import os

from .decorators import check_banned

# Hardcoded locked rarities for claim
LOCKED_RARITIES = [
    "Exclusive", "Elite", "Limited Edition", "Ultimate", "Supreme", "Premium", "Zenith", "Mythic", "Ethereal", "Erotic"
]
import asyncio
from config import OWNER_ID
import random
from modules.postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display

# Track users with a claim in progress
CLAIM_IN_PROGRESS = set()

@check_banned
async def claim_command(client: Client, message: Message):
    """Handle daily character claim"""
    user_id = message.from_user.id
    if user_id in CLAIM_IN_PROGRESS:
        await message.reply_text("<b>⏳ Your claim is already being processed, please wait.</b>")
        return
    CLAIM_IN_PROGRESS.add(user_id)
    try:
        db = get_database()
        # Get user data
        user = await db.get_user(user_id)
        if not user:
            # Create new user if doesn't exist
            user = {
                'user_id': user_id,
                'first_name': message.from_user.first_name,
                'username': message.from_user.username,
                'characters': [],
                'last_claim': None
            }
            await db.add_user(user)

        is_owner = user_id == OWNER_ID
        # Check if user has already claimed today (skip for owner)
        last_claim = user.get('last_claim')
        if last_claim and not is_owner:
            # Handle both string and datetime types
            if isinstance(last_claim, str):
                last_claim_dt = datetime.fromisoformat(last_claim)
            else:
                last_claim_dt = last_claim
            next_claim = last_claim_dt + timedelta(days=1)
            if datetime.now() < next_claim:
                time_left = next_claim - datetime.now()
                hours = time_left.seconds // 3600
                minutes = (time_left.seconds % 3600) // 60
                await message.reply_text(
                    f"<b>❌ ʏᴏᴜ'ᴠᴇ ᴀʟʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ʏᴏᴜʀ ᴅᴀɪʟʏ ᴘᴏᴋᴇᴍᴏɴ!</b>\n"
                    f"ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ: <b>{hours}h {minutes}m</b>",
                )
                return
        # Send animation
        animation_message = await message.reply_text("💫")
        await asyncio.sleep(3)
        await animation_message.delete()
        # Use hardcoded locked rarities for claim
        locked_rarities = LOCKED_RARITIES

        # Get random character
        if is_owner:
            # Weighted bias: Premium and Supreme much more likely
            weighted_rarities = (
                ["Premium"] * 40 +
                ["Supreme"] * 40 +
                ["Elite"] * 10 +
                ["Limited Edition"] * 5 +
                ["Ultimate"] * 5
            )
            chosen_rarity = random.choice(weighted_rarities)
            character = await db.get_random_character_by_rarities([chosen_rarity])
            # Fallback: try all high rarities if none found
            if not character:
                high_rarities = ["Premium", "Supreme", "Elite", "Limited Edition", "Ultimate"]
                character = await db.get_random_character_by_rarities(high_rarities)
            if not character:
                character = await db.get_random_character()
        else:
            # For regular users, respect locked rarities
            character = await db.get_random_character(locked_rarities)
        if not character:
            await message.reply_text(
                "<b>❌ ɴᴏ ᴘᴏᴋᴇᴍᴏɴs ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ᴛʜᴇ ᴅᴀᴛᴀʙᴀsᴇ!</b>",
            )
            return
        # Add character to user's collection
        await db.add_character_to_user(user_id, character['character_id'])
        # Update last claim time (skip for owner)
        if not is_owner:
            await db.update_user(user_id, {'last_claim': datetime.now()})
        # Get rarity emoji
        rarity_emoji = get_rarity_emoji(character['rarity'])
        # Create caption with success message
        caption = (
            f"<b>🌙 {message.from_user.first_name} You Got A New Pokémon!</b>\n\n"
            f"<b>👤 Name:</b> {character['name']}\n"
            f"<b>{rarity_emoji} Rarity:</b> {character['rarity']}\n"
            f"<b>⛩ Region:</b> {character['anime']}\n\n"
            f"<b>🆔:</b> <code>{character['character_id']}</code>"
        )
        # Edge case: video character
        is_video = character.get('is_video', False)
        try:
            if is_video:
                # Prefer img_url for video, fallback to file_id
                video_source = character.get('img_url') or character.get('file_id')
                await message.reply_video(
                    video=video_source,
                    caption=caption
                )
            else:
                await message.reply_photo(
                    photo=character['img_url'],
                    caption=caption
                )
        except Exception as media_error:
            print(f"Failed to send media: {media_error}")
            # Fallback: try text-only message
            await message.reply_text(
                f"{caption}\n\n<b>⚠️ ᴄᴏᴜʟᴅ ɴᴏᴛ ʟᴏᴀᴅ ᴘᴏᴋᴇᴍᴏɴ ᴍᴇᴅɪᴀ!</b>",
            )
    finally:
        CLAIM_IN_PROGRESS.discard(user_id)

def setup_claim_handlers(app: Client):
    """Setup claim command handler"""
    print("Registering claim command handler...")
    app.on_message(filters.command("claim"))(claim_command)
    print("Claim handler registered!")

