from pyrogram import Client, filters
from pyrogram.types import Message
from modules.postgres_database import get_database
from modules.sell import SELL_PRICES, get_sell_multiplier
from modules.trade import action_manager
from datetime import datetime
from modules.decorators import check_banned
import asyncio
import random
import logging

# Async locks for fusion operations
_fusion_locks = {}

# Fusion configuration
FUSION_CONFIG = {
    "elite_chance": 0.3,  # 30% chance to get elite card
    "token_chance": 0.7,  # 70% chance to get tokens
    "min_exclusive_rarity": "Exclusive",  # Only exclusive rarity can be fused
    "min_characters_required": 2  # Minimum characters needed for fusion
}

@check_banned
async def fusion_info_command(client: Client, message: Message):
    """Show fusion rules and statistics"""
    info_text = (
        f"<b>🔮 Fusion System</b>\n\n"
        f"<b>Requirements:</b>\n"
        f"• Both characters must be <b>{FUSION_CONFIG['min_exclusive_rarity']}</b> rarity\n"
        f"• You must own both characters\n"
        f"• Characters must be different\n"
        f"• Minimum {FUSION_CONFIG['min_characters_required']} characters required\n\n"
        f"<b>Results:</b>\n"
        f"• <b>{FUSION_CONFIG['elite_chance']*100:.0f}%</b> chance to get an <b>Elite</b> card\n"
        f"• <b>{FUSION_CONFIG['token_chance']*100:.0f}%</b> chance to get <b>tokens</b>\n\n"
        f"<b>Usage:</b>\n"
        f"<code>/fuse &lt;char_id1&gt; &lt;char_id2&gt;</code>\n\n"
        f"<b>Example:</b>\n"
        f"<code>/fuse 123 456</code>\n\n"
        f"<b>Note:</b> Fusion is irreversible! Characters will be permanently removed from your collection."
    )
    await message.reply_text(info_text)

@check_banned
async def fuse_command(client: Client, message: Message):
    """Fuse two exclusive rarity characters for either elite card or tokens"""
    user_id = message.from_user.id
    db = get_database()
    
    # Get or create lock for this user
    if user_id not in _fusion_locks:
        _fusion_locks[user_id] = asyncio.Lock()
    lock = _fusion_locks[user_id]
    
    async with lock:
        try:
            # Check if user has any active action
            if await action_manager.is_user_busy(db, user_id):
                action_type = await action_manager.get_user_action(db, user_id)
                await message.reply_text(f"❌ {action_manager.get_action_message(action_type)}")
                return
            
            # Parse command arguments
            args = message.text.split()
            if len(args) < 3:
                await message.reply_text(
                    "❌ Usage: /fuse <char_id1> <char_id2>\n"
                    "Example: /fuse 123 456"
                )
                return
            
            try:
                char_id1 = int(args[1])
                char_id2 = int(args[2])
            except ValueError:
                await message.reply_text("❌ Please provide valid character IDs (numbers only)!")
                return
            
            # Check if same character
            if char_id1 == char_id2:
                await message.reply_text("❌ You must fuse two different characters!")
                return
            
            # Get user data
            user = await db.get_user(user_id)
            if not user:
                await message.reply_text("❌ User not found!")
                return
            
            owned = set(user.get('characters', []))
            if len(owned) < FUSION_CONFIG["min_characters_required"]:
                await message.reply_text(
                    f"❌ You need at least {FUSION_CONFIG['min_characters_required']} characters to perform fusion!"
                )
                return
            
            if char_id1 not in owned or char_id2 not in owned:
                await message.reply_text("❌ You do not own both characters!")
                return
            
            # Fetch both character documents
            char1 = await db.get_character(char_id1)
            char2 = await db.get_character(char_id2)
            
            if not char1 or not char2:
                await message.reply_text("❌ One or both characters not found!")
                return
            
            # Validate rarity requirements
            rarity1 = char1.get('rarity')
            rarity2 = char2.get('rarity')
            
            if rarity1 != FUSION_CONFIG["min_exclusive_rarity"] or rarity2 != FUSION_CONFIG["min_exclusive_rarity"]:
                await message.reply_text(
                    f"❌ Both characters must be {FUSION_CONFIG['min_exclusive_rarity']} rarity to fuse!\n"
                    f"Character 1: {char1['name']} ({rarity1})\n"
                    f"Character 2: {char2['name']} ({rarity2})\n\n"
                    f"Use /fusioninfo to see fusion rules."
                )
                return
            
            # Set user action to prevent other operations
            await action_manager.set_user_action(db, user_id, 'fusion', {
                'char_id1': char_id1,
                'char_id2': char_id2,
                'timestamp': datetime.utcnow().timestamp()
            })
            
            # Determine fusion result (elite card or tokens)
            result_type = "elite" if random.random() < FUSION_CONFIG["elite_chance"] else "tokens"
            
            # Remove characters from user's collection
            chars = list(user.get('characters', []))
            chars.remove(char_id1)
            chars.remove(char_id2)
            # Immediately update the user's collection in the database
            await db.update_user(user_id, {'characters': chars})
            now = datetime.utcnow()
            
            if result_type == "elite":
                # Get random Elite character
                elite = await db.get_random_character_by_rarities(["Elite"])
                if not elite:
                    # Fallback to tokens if no elite available
                    result_type = "tokens"
                    logging.warning(f"No Elite characters available for fusion, falling back to tokens for user {user_id}")
                else:
                    chars.append(elite['character_id'])
                    await db.update_user(user_id, {'characters': chars})
                    
                    # Log transaction
                    await db.log_user_transaction(user_id, "fusion_elite", {
                        "input_ids": [char_id1, char_id2],
                        "input_names": [char1['name'], char2['name']],
                        "result_id": elite['character_id'],
                        "result_name": elite['name'],
                        "result_rarity": elite['rarity'],
                        "date": now.strftime('%Y-%m-%d %H:%M')
                    })
                    
                    # Send success message
                    emoji = elite.get('emoji', '💎')
                    img = elite.get('img_url') or elite.get('file_id')
                    msg = (
                        f"<b>✨ Fusion Success!</b>\n\n"
                        f"You fused <b>{char1['name']}</b> and <b>{char2['name']}</b> (Exclusive + Exclusive)\n"
                        f"→ <b>{emoji} {elite['name']}</b> (Elite) added to your collection!"
                    )
                    
                    if img:
                        await message.reply_photo(img, caption=msg)
                    else:
                        await message.reply_text(msg)
                    
                    # Clear user action
                    await action_manager.clear_user_action(db, user_id)
                    return
            
            # Handle token result (either direct or fallback)
            if result_type == "tokens":
                price1 = SELL_PRICES.get(rarity1, 0)
                price2 = SELL_PRICES.get(rarity2, 0)
                multiplier = get_sell_multiplier()
                tokens = int((price1 + price2) * multiplier)
                
                wallet = user.get('wallet', 0) + tokens
                await db.update_user(user_id, {'characters': chars, 'wallet': wallet})
                
                # Log transaction
                await db.log_user_transaction(user_id, "fusion_tokens", {
                    "input_ids": [char_id1, char_id2],
                    "input_names": [char1['name'], char2['name']],
                    "input_rarities": [rarity1, rarity2],
                    "tokens": tokens,
                    "date": now.strftime('%Y-%m-%d %H:%M')
                })
                
                msg = (
                    f"<b>✨ Fusion Success!</b>\n\n"
                    f"You fused <b>{char1['name']}</b> ({rarity1}) and <b>{char2['name']}</b> ({rarity2})\n"
                    f"→ <b>{tokens:,} tokens</b> have been added to your wallet!"
                )
                await message.reply_text(msg)
                
                # Clear user action
                await action_manager.clear_user_action(db, user_id)
                return
                
        except Exception as e:
            logging.error(f"Error in fusion for user {user_id}: {str(e)}")
            await message.reply_text("❌ An error occurred during fusion. Please try again!")
            # Clear user action on error
            await action_manager.clear_user_action(db, user_id)
        finally:
            # Clean up lock
            if user_id in _fusion_locks:
                del _fusion_locks[user_id]

def setup_fusion_handlers(app: Client):
    app.add_handler(filters.command("fuse")(fuse_command))
    app.add_handler(filters.command("fusioninfo")(fusion_info_command)) 