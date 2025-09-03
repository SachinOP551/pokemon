from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .decorators import check_banned
import os

# Import database based on configuration
from modules.postgres_database import get_database
import random

# Achievement milestones
ACHIEVEMENTS = [
    {"name": "1 Collection", "count": 1, "reward_chars": 1},
    {"name": "10 Collections", "count": 10, "reward_chars": 2},
    {"name": "50 Collections", "count": 50, "reward_chars": 3},
    {"name": "100 Collections", "count": 100, "reward_chars": 4},
    {"name": "250 Collections", "count": 250, "reward_chars": 5},
    {"name": "500 Collections", "count": 500, "reward_chars": 6},
    {"name": "1000 Collections", "count": 1000, "reward_chars": 7},
    {"name": "2500 Collections", "count": 2500, "reward_chars": 8},
    {"name": "5000 Collections", "count": 5000, "reward_chars": 9},
    {"name": "10000 Collections", "count": 10000, "reward_chars": 10}
]

@check_banned
async def achievement_command(client: Client, message: Message):
    """Handle /achievement command"""
    try:
        user_id = message.from_user.id
        db = get_database()
        
        # Ensure claimed_achievements column exists
        await db.ensure_claimed_achievements_column()
        
        # Get user data
        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "<b>❌ ʏᴏᴜ ᴍᴜsᴛ ʙᴇ ʀᴇɢɪsᴛᴇʀᴇᴅ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ!</b>"
            )
            return
        
        # Get user's collected characters count (all characters ever collected, including duplicates)
        import json
        collection_history = user.get('collection_history', [])
        if isinstance(collection_history, str):
            try:
                collection_history = json.loads(collection_history)
            except Exception:
                collection_history = []
        if collection_history is None:
            collection_history = []
        collected_count = 0
        for entry in collection_history:
            if isinstance(entry, dict) and entry.get('source') == 'collected':
                collected_count += 1
        unique_collection_count = collected_count
        
        # Get claimed achievements
        claimed_achievements = user.get('claimed_achievements', [])
        
        # Create keyboard with collection count button
        keyboard = [
            [InlineKeyboardButton(
                f"📊 Collection Count ({unique_collection_count})",
                callback_data="achievement_collection"
            )]
        ]
        
        await message.reply_text(
            f"<b>🏆 Here is your achievement list!</b>\n"
            f"Get rewards for your achievements by clicking the buttons below!!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        print(f"Error in achievement_command: {e}")
        await message.reply_text("<b>❌ An error occurred!</b>")

async def achievement_callback(client: Client, callback_query: CallbackQuery):
    """Handle achievement callback queries"""
    try:
        user_id = callback_query.from_user.id
        db = get_database()
        
        # Ensure claimed_achievements column exists
        await db.ensure_claimed_achievements_column()
        
        # Restrict access to the user who initiated the achievement command
        if callback_query.message.reply_to_message:
            initiator_id = callback_query.message.reply_to_message.from_user.id
            if user_id != initiator_id:
                await callback_query.answer("Access denied you can't access other user's achievement", show_alert=True)
                return
        elif callback_query.message and hasattr(callback_query.message, 'entities'):
            # Fallback: check if the first entity is a mention of the user
            # (This is a best-effort fallback, not always reliable)
            pass

        # Get user data
        import json
        user = await db.get_user(user_id)
        if not user:
            await callback_query.answer("❌ User not found!", show_alert=True)
            return
        # Get user's collected characters count (all characters ever collected, including duplicates)
        collection_history = user.get('collection_history', [])
        if isinstance(collection_history, str):
            try:
                collection_history = json.loads(collection_history)
            except Exception:
                collection_history = []
        if collection_history is None:
            collection_history = []
        collected_count = 0
        for entry in collection_history:
            if isinstance(entry, dict) and entry.get('source') == 'collected':
                collected_count += 1
        unique_collection_count = collected_count
        # Get claimed achievements
        claimed_achievements = user.get('claimed_achievements', [])
        if isinstance(claimed_achievements, str):
            import json
            try:
                claimed_achievements = json.loads(claimed_achievements)
            except Exception:
                claimed_achievements = []
        if claimed_achievements is None:
            claimed_achievements = []
        
        # Parse callback data
        action = callback_query.data.split('_')[1]
        
        if action == "collection":
            # Show collection achievements
            user_name = user.get('first_name', 'User')
            message_text = f"<b>{user_name}, Here is your achievement list!</b>\n\n"
            
            # Create keyboard with achievement buttons
            keyboard = []
            for achievement in ACHIEVEMENTS:
                is_claimed = achievement['name'] in claimed_achievements
                is_available = unique_collection_count >= achievement['count']
                
                if is_claimed:
                    button_text = f"✅ {achievement['name']} (Claimed)"
                    callback_data = "achievement_claimed"
                elif is_available:
                    button_text = f"🎁 {achievement['name']} - Claim {achievement['reward_chars']} chars"
                    callback_data = f"achievement_claim_{achievement['count']}"
                else:
                    button_text = f"🔒 {achievement['name']}"
                    callback_data = "achievement_locked"
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            # Add back button
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="achievement_back")])
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif action == "claim":
            # Handle achievement claim
            achievement_count = int(callback_query.data.split('_')[2])
            achievement = next((a for a in ACHIEVEMENTS if a['count'] == achievement_count), None)
            
            if not achievement:
                await callback_query.answer("❌ Achievement not found!", show_alert=True)
                return
            
            if achievement['name'] in claimed_achievements:
                await callback_query.answer("❌ Already claimed!", show_alert=True)
                return
            
            # Give reward characters (excluding Supreme and Premium)
            if achievement['count'] == 5000:
                # 2 Ethereal, 1 Ultimate, 3 Zenith, rest random
                reward_characters = []
                ethereal = await db.get_random_character_by_rarities(['Ethereal'])
                if ethereal:
                    reward_characters.append(ethereal)
                ethereal2 = await db.get_random_character_by_rarities(['Ethereal'])
                if ethereal2:
                    reward_characters.append(ethereal2)
                ultimate = await db.get_random_character_by_rarities(['Ultimate'])
                if ultimate:
                    reward_characters.append(ultimate)
                for _ in range(3):
                    zenith = await db.get_random_character_by_rarities(['Zenith'])
                    if zenith:
                        reward_characters.append(zenith)
                # Fill the rest with random eligible
                needed = achievement['reward_chars'] - len(reward_characters)
                excluded_rarities = ['Supreme', 'Premium', 'Limited Edition', 'Ethereal', 'Ultimate', 'Zenith', 'Mega Evolution']
                if needed > 0:
                    rest = await db.get_random_character_by_rarities_excluding(excluded_rarities, needed)
                    reward_characters.extend(rest)
            elif achievement['count'] == 10000:
                # 2 Ultimate, 1 Ethereal, 2 Zenith, rest random
                reward_characters = []
                for _ in range(2):
                    ultimate = await db.get_random_character_by_rarities(['Ultimate'])
                    if ultimate:
                        reward_characters.append(ultimate)
                ethereal = await db.get_random_character_by_rarities(['Ethereal'])
                if ethereal:
                    reward_characters.append(ethereal)
                for _ in range(2):
                    zenith = await db.get_random_character_by_rarities(['Zenith'])
                    if zenith:
                        reward_characters.append(zenith)
                needed = achievement['reward_chars'] - len(reward_characters)
                excluded_rarities = ['Supreme', 'Premium', 'Limited Edition', 'Ethereal', 'Ultimate', 'Zenith', 'Mega Evolution']
                if needed > 0:
                    rest = await db.get_random_character_by_rarities_excluding(excluded_rarities, needed)
                    reward_characters.extend(rest)
            else:
                excluded_rarities = ['Ultimate', 'Supreme', 'Premium', 'Limited Edition', 'Mega Evolution']
                reward_characters = await db.get_random_character_by_rarities_excluding(
                    excluded_rarities, achievement['reward_chars']
                )
            
            if not reward_characters:
                await callback_query.answer("❌ No characters available for reward!", show_alert=True)
                return
            
            # Add characters to user
            character_names = []
            for char in reward_characters:
                await db.add_character_to_user(user_id, char['character_id'], source='achievement')
                character_names.append(char['name'])
            
            # Mark achievement as claimed
            claimed_achievements.append(achievement['name'])
            import json
            await db.update_user(user_id, {'claimed_achievements': json.dumps(claimed_achievements)})
            
            # Send success message
            user_name = user.get('first_name', 'User')
            reward_text = f"<b>🎉 {user_name} got character with id : {reward_characters[0]['character_id']} by clicking claim button!</b>"
            
            if len(reward_characters) > 1:
                reward_text = f"<b>🎉 {user_name} got {len(reward_characters)} characters by claiming {achievement['name']}!</b>\n"
                for char in reward_characters:
                    reward_text += f"• {char['name']} (ID: {char['character_id']})\n"
            
            await callback_query.edit_message_text(reward_text)
            
        elif action == "claimed":
            await callback_query.answer("✅ Already claimed!", show_alert=True)
            
        elif action == "locked":
            await callback_query.answer("🔒 Achievement not yet unlocked!", show_alert=True)
            
        elif action == "back":
            # Go back to main achievement menu
            keyboard = [
                [InlineKeyboardButton(
                    f"📊 Collection Count ({unique_collection_count})",
                    callback_data="achievement_collection"
                )]
            ]
            
            await callback_query.edit_message_text(
                f"<b>🏆 Here is your achievement list!</b>\n"
                f"Get rewards for your achievements by clicking the buttons below!!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        print(f"Error in achievement_callback: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

def setup_achievement_handlers(app: Client):
    """Setup achievement command handlers"""
    app.on_message(filters.command("achievement"))(achievement_command)
    app.on_callback_query(filters.regex(r"^achievement_"))(achievement_callback) 