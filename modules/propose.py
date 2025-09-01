import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import os
import random
import time

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import OWNER_ID
from modules.postgres_database import (
    RARITIES,
    RARITY_EMOJIS,
    get_database,
    get_rarity_display,
    get_rarity_emoji,
)
from modules.postgres_database import get_database

from .decorators import is_og, is_owner
from .decorators import check_banned

# Default propose weights and locked rarities
DEFAULT_PROPOSE_WEIGHTS = {
    "Common": 15,
    "Medium": 15,
    "Rare": 15,
    "Legendary": 15,
    "Exclusive": 10,
    "Elite": 0,
    "Limited Edition": 0,
    "Ultimate": 0,
    "Supreme": 0,
    "Premium": 0,
    "Zenith": 5,
    "Mythic": 5,
    "Ethereal": 2
}
DEFAULT_LOCKED = ["Premium", "Limited Edition", "Ultimate", "Supreme", "Mega Evolution"]

# Add per-user locks to prevent propose spam
user_locks = defaultdict(asyncio.Lock)

# Special configuration: user with boosted propose privileges
SPECIAL_PROPOSE_USER_ID = 7950419313  # 100% acceptance, 60% chance for Zenith/Mythic/Elite

def should_get_special_rarities(user_id: int) -> bool:
    """Check if user should get special rarities (owner or special users)"""
    special_user_ids = [OWNER_ID, 6919874630]  # Owner and the new special user
    return user_id in special_user_ids

@check_banned
async def propose_command(client: Client, message: Message):
    """Handle character proposal"""
    user_id = message.from_user.id
    async with user_locks[user_id]:
        try:
            db = get_database()
            # Get user data
            user = await db.get_user(user_id)
            if not user:
                await message.reply_text(
                    "<b>❌ ʏᴏᴜ ᴍᴜsᴛ ʙᴇ ʀᴇɢɪsᴛᴇʀᴇᴅ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ!</b>"
                )
                return
            # Get propose settings
            settings = await db.get_propose_settings()
            if not settings:
                settings = {
                    'locked_rarities': DEFAULT_LOCKED.copy(),
                    'propose_cooldown': 100,  # seconds
                    'propose_cost': 20000,    # tokens
                    'acceptance_rate': 50,    # percentage
                    'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy()
                }
                await db.update_propose_settings(settings)
            # Defensive check before deduction (prevents race conditions)
            user = await db.get_user(user_id)
            last_propose = user.get('last_propose')
            cooldown_triggered = False
            if last_propose:
                try:
                    last_propose_dt = datetime.fromisoformat(last_propose)
                    next_propose = last_propose_dt + timedelta(seconds=settings['propose_cooldown'])
                    if datetime.now() < next_propose:
                        cooldown_triggered = True
                except Exception:
                    # If parsing fails, treat as if user never proposed before
                    pass
            if cooldown_triggered:
                # Calculate remaining cooldown
                remaining = (next_propose - datetime.now()).total_seconds()
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                # Do not update last_propose here; only update after a valid proposal
                await message.reply_text(
                    f"<b>⏳ ᴄᴏᴏʟᴅᴏᴡɴ ʀᴇᴍᴀɪɴɪɴɢ:</b> <code>{minutes}m {seconds}s</code>"
                )
                return
            current_wallet = user.get('wallet', 0)
            if current_wallet < settings['propose_cost']:
                needed = settings['propose_cost'] - current_wallet
                await message.reply_text(
                    f"<b>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴛᴏᴋᴇɴs!</b>\n"
                    f"You need <code>{settings['propose_cost']}</code> tokens, but you have <code>{current_wallet}</code>.\n"
                    f"You need <code>{needed}</code> more tokens."
                )
                return
            # Special handling for owner and special users
            is_special_user = should_get_special_rarities(user_id)
            is_special_weight_user = (user_id == SPECIAL_PROPOSE_USER_ID)
            character = None
            
            if is_special_user:
                # For owner and special users, prioritize Supreme/Ultimate/Limited Edition
                special_rarities = ['Supreme', 'Ultimate', 'Premium']
                character = await db.get_random_character_by_rarities(special_rarities)
                if not character:
                    # Fallback 1: Try any high rarity characters
                    high_rarities = ['Supreme', 'Ultimate', 'Premium', 'Limited Edition', 'Elite']
                    character = await db.get_random_character_by_rarities(high_rarities)
                if not character:
                    # Fallback 2: Try any unlocked characters
                    character = await db.get_random_character(settings.get('locked_rarities', DEFAULT_LOCKED))
                if not character:
                    # Fallback 3: Try any character at all (last resort)
                    character = await db.get_random_character([])
            else:
                # Weighted random rarity selection for non-owners
                weights = settings.get('propose_weights', DEFAULT_PROPOSE_WEIGHTS)
                locked = set(settings.get('locked_rarities', DEFAULT_LOCKED))
                available_rarities = [r for r, w in weights.items() if w > 0 and r not in locked]
                
                if not available_rarities:
                    # Fallback: If no rarities available by weights, try any unlocked rarity
                    available_rarities = [r for r in RARITIES.keys() if r not in locked]
                
                if not available_rarities:
                    # Ultimate fallback: try any character EXCEPT special rarities (never give special rarities to normal users)
                    # For normal users, we must NEVER give special rarities, so we use the locked rarities list
                    # which includes all the special rarities that normal users shouldn't get
                    character = await db.get_random_character(settings.get('locked_rarities', DEFAULT_LOCKED))
                else:
                    # For the special weighted user, give a 60% chance to pick from Zenith/Mythic/Elite
                    if is_special_weight_user and character is None:
                        if random.randint(1, 100) <= 60:
                            boosted_rarities = ['Zenith', 'Mythic', 'Elite']
                            # Ensure boosted rarities are not locked
                            boosted_rarities = [r for r in boosted_rarities if r not in locked]
                            if boosted_rarities:
                                character = await db.get_random_character_by_rarities(boosted_rarities)
                    if character is None:
                        # Use weighted random selection without multiplying sequences
                        total_weight = sum(weights.get(r, 1) for r in available_rarities)
                        if total_weight <= 0:
                            # If weights are invalid, use equal weights
                            total_weight = len(available_rarities)
                        
                        # Pick a random number and find the corresponding rarity
                        rand_val = random.uniform(0, total_weight)
                        current_weight = 0
                        
                        for rarity in available_rarities:
                            weight = weights.get(rarity, 1) if total_weight > len(available_rarities) else 1
                            current_weight += weight
                            if rand_val <= current_weight:
                                selected_rarity = rarity
                                break
                        else:
                            # Fallback to random choice if something goes wrong
                            selected_rarity = random.choice(available_rarities)
                        
                        # Try to get character by selected rarity
                        character = await db.get_random_character_by_rarities([selected_rarity])
                        
                        # Fallback chain if specific rarity fails
                        if not character:
                            # Fallback 1: Try any unlocked rarity (excluding special rarities)
                            character = await db.get_random_character(settings.get('locked_rarities', DEFAULT_LOCKED))
                        if not character:
                            # Fallback 2: Try any character EXCEPT special rarities (never give special rarities to normal users)
                            # For normal users, we must NEVER give special rarities, so we use the locked rarities list
                            # which includes all the special rarities that normal users shouldn't get
                            character = await db.get_random_character(settings.get('locked_rarities', DEFAULT_LOCKED))
            
            # Final check - if we still don't have a character, something is wrong with the database
            if not character:
                await message.reply_text(
                    "<b>❌ ᴅᴀᴛᴀʙᴀsᴇ ᴇʀʀᴏʀ!</b>\n"
                    "No characters found in the database. Please contact an administrator."
                )
                return
            # Calculate acceptance chance
            rarity_rates = settings.get('rarity_rates', {})
            if character['rarity'] in rarity_rates:
                rarity_rate = rarity_rates[character['rarity']]
            else:
                rarity_rate = settings['acceptance_rate']
            if is_special_user and character['rarity'] in ['Supreme', 'Ultimate', 'Premium']:
                is_accepted = True
            elif is_special_weight_user:
                # Force 100% acceptance for the special weighted user
                is_accepted = True
            else:
                is_accepted = random.randint(1, 100) <= rarity_rate
            if is_accepted:
                await db.add_character_to_user(user_id, character['character_id'], source='propose')
                rarity_emoji = get_rarity_emoji(character['rarity'])
                caption = (
                    f"<b>🎉 ʏᴏᴜ sᴜᴄᴄᴇssғᴜʟʟʏ ᴘʀᴏᴘᴏsᴇᴅ {rarity_emoji} "
                    f"{character['name']}!</b>\n"
                )
                # Log transaction
                await db.log_user_transaction(user_id, "propose", {
                    "character_id": character['character_id'],
                    "name": character['name'],
                    "rarity": character['rarity'],
                    "date": datetime.now().strftime('%Y-%m-%d')
                })
                is_video = character.get('is_video', False)
                try:
                    if character.get('img_url'):
                        if is_video:
                            await message.reply_video(
                                video=character['img_url'],
                                caption=caption
                            )
                        else:
                            await message.reply_photo(
                                photo=character['img_url'],
                                caption=caption
                            )
                    elif character.get('file_id'):
                        if is_video:
                            await message.reply_video(
                                video=character['file_id'],
                                caption=caption
                            )
                        else:
                            await message.reply_photo(
                                photo=character['file_id'],
                                caption=caption
                            )
                    else:
                        await message.reply_text(caption)
                except Exception as e:
                    print(f"Error sending media in propose_command: {e}")
                    await message.reply_text(caption)
            else:
                fail_text = (
                    "<b>❌ Your proposal was rejected. Good luck next time.</b>"
                )
                try:
                    await message.reply_text(fail_text)
                except Exception as e:
                    print(f"Error sending rejection in propose_command: {e}")
            # Only now, after a valid proposal attempt, deduct tokens and set cooldown
            new_wallet = current_wallet - settings['propose_cost']
            await db.update_user(user_id, {
                'wallet': new_wallet,
                'last_propose': datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Error in propose_command: {e}")
            try:
                await message.reply_text("<b>❌ An error occurred while processing your proposal.</b>")
            except Exception:
                pass

async def proposelock_command(client: Client, message: Message):
    """Show propose rarity lock interface"""
    user_id = message.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    
    # Get current settings
    settings = await db.get_propose_settings()
    if not settings:
        settings = {
            'locked_rarities': DEFAULT_LOCKED.copy(),
            'propose_cooldown': 100,
            'propose_cost': 20000,
            'acceptance_rate': 50,
            'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy()
        }
        await db.update_propose_settings(settings)
    
    # Create message showing locked rarities
    message_text = "<b>🔒 ᴘʀᴏᴘᴏsᴇ ʀᴀʀɪᴛʏ ʟᴏᴄᴋs</b>\n\n"
    message_text += "<b>ʟᴏᴄᴋᴇᴅ ʀᴀʀɪᴛɪᴇs:</b>\n"
    if settings.get('locked_rarities'):
        for rarity in settings['locked_rarities']:
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            message_text += f"• {emoji} {rarity}\n"
    else:
        message_text += "• No rarities locked\n"
    
    # Create keyboard with rarity toggle buttons
    keyboard = []
    for rarity, _ in RARITIES.items():
        emoji = RARITY_EMOJIS.get(rarity, "❓")
        is_locked = rarity in settings.get('locked_rarities', DEFAULT_LOCKED)
        status = "🔒" if is_locked else "🔓"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {emoji} {rarity}",
                callback_data=f"propose_toggle_{rarity}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        message_text,
        reply_markup=reply_markup
    )

async def setcooldown_command(client: Client, message: Message):
    """Set propose cooldown"""
    user_id = message.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    
    # Check if value is provided
    if not message.text.split()[1:]:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴄᴏᴏʟᴅᴏᴡɴ ᴠᴀʟᴜᴇ!</b>\n"
            "<b>ᴜsᴀɢᴇ:</b> `/setcooldown <seconds>`"
        )
        return
    
    try:
        value = int(message.text.split()[1])
        if not 10 <= value <= 3600:
            await message.reply_text(
                "<b>❌ ᴄᴏᴏʟᴅᴏᴡɴ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 10 ᴀɴᴅ 3600 sᴇᴄᴏɴᴅs!</b>"
            )
            return
        
        # Get current settings
        settings = await db.get_propose_settings()
        if not settings:
            settings = {
                'locked_rarities': DEFAULT_LOCKED.copy(),
                'propose_cooldown': 100,
                'propose_cost': 20000,
                'acceptance_rate': 50,
                'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy(),
                'rarity_rates': {}
            }
        
        # Update settings
        settings['propose_cooldown'] = value
        await db.update_propose_settings(settings)
        
        await message.reply_text(
            f"<b>✅ ᴘʀᴏᴘᴏsᴇ ᴄᴏᴏʟᴅᴏᴡɴ sᴇᴛ ᴛᴏ {value} sᴇᴄᴏɴᴅs!</b>"
        )
        
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!</b>"
        )

async def setcost_command(client: Client, message: Message):
    """Set propose cost"""
    user_id = message.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text(
            "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ ᴀɴᴅ ᴏɢs ᴏɴʟʏ!</b>"
        )
        return
    
    # Check if value is provided
    if not message.text.split()[1:]:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴄᴏsᴛ ᴠᴀʟᴜᴇ!</b>"
        )
        return
    
    try:
        value = int(message.text.split()[1])
        if not 1 <= value <= 100000:
            await message.reply_text(
                "<b>❌ ᴄᴏsᴛ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 100000 ᴛᴏᴋᴇɴs!</b>"
            )
            return
        
        # Get current settings
        settings = await db.get_propose_settings()
        if not settings:
            settings = {
                'locked_rarities': DEFAULT_LOCKED.copy(),
                'propose_cooldown': 100,
                'propose_cost': 20000,
                'acceptance_rate': 50,
                'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy(),
                'rarity_rates': {}
            }
        
        # Update settings
        settings['propose_cost'] = value
        await db.update_propose_settings(settings)
        
        await message.reply_text(
            f"<b>✅ ᴘʀᴏᴘᴏsᴇ ᴄᴏsᴛ sᴇᴛ ᴛᴏ {value} ᴛᴏᴋᴇɴs!</b>"
        )
        
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!</b>"
        )

async def setacceptance_command(client: Client, message: Message):
    """Set propose acceptance rate"""
    user_id = message.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text(
            "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ ᴀɴᴅ ᴏɢs ᴏɴʟʏ!</b>"
        )
        return
    
    # Check if value is provided
    if not message.text.split()[1:]:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀɴ ᴀᴄᴄᴇᴘᴛᴀɴᴄᴇ ʀᴀᴛᴇ!</b>\n"
            "<b>ᴜsᴀɢᴇ:</b> `/setacceptance <percentage>`"
        )
        return
    
    try:
        value = int(message.text.split()[1])
        if not 1 <= value <= 100:
            await message.reply_text(
                "<b>❌ ᴀᴄᴄᴇᴘᴛᴀɴᴄᴇ ʀᴀᴛᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 100!</b>"
            )
            return
        
        # Get current settings
        settings = await db.get_propose_settings()
        if not settings:
            settings = {
                'locked_rarities': DEFAULT_LOCKED.copy(),
                'propose_cooldown': 100,
                'propose_cost': 20000,
                'acceptance_rate': 50,
                'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy(),
                'rarity_rates': {}
            }
        
        # Update settings
        settings['acceptance_rate'] = value
        await db.update_propose_settings(settings)
        
        await message.reply_text(
            f"<b>✅ ᴘʀᴏᴘᴏsᴇ ᴀᴄᴄᴇᴘᴛᴀɴᴄᴇ ʀᴀᴛᴇ sᴇᴛ ᴛᴏ {value}%!</b>"
        )
        
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!</b>"
        )

async def propose_callback(client: Client, callback_query: CallbackQuery):
    """Handle propose settings callbacks"""
    query = callback_query
    user_id = query.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await query.answer("❌ You don't have permission!", show_alert=True)
        return
    
    # Parse callback data
    action, *args = query.data.split('_')
    
    if action == "propose":
        if args[0] == "toggle":
            # Toggle rarity lock
            rarity = '_'.join(args[1:])
            settings = await db.get_propose_settings()
            if not settings:
                settings = {
                    'locked_rarities': DEFAULT_LOCKED.copy(),
                    'propose_cooldown': 100,
                    'propose_cost': 20000,
                    'acceptance_rate': 50,
                    'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy(),
                    'rarity_rates': {}
                }
            
            locked_rarities = settings.get('locked_rarities', DEFAULT_LOCKED).copy()
            
            if rarity in locked_rarities:
                locked_rarities.remove(rarity)
            else:
                locked_rarities.append(rarity)
            
            # Update the settings with the new locked_rarities
            settings['locked_rarities'] = locked_rarities
            await db.update_propose_settings(settings)
            
            # Create new keyboard with updated button
            keyboard = []
            for r, _ in RARITIES.items():
                emoji = RARITY_EMOJIS.get(r, "❓")
                is_locked = r in locked_rarities
                status = "🔒" if is_locked else "🔓"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{status} {emoji} {r}",
                        callback_data=f"propose_toggle_{r}"
                    )
                ])
            
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            await query.answer(
                f"{'Locked' if rarity in locked_rarities else 'Unlocked'} {rarity} rarity",
                show_alert=True
            )

async def pconfig_command(client: Client, message: Message):
    """Show current propose configuration with details"""
    user_id = message.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    
    # Get current settings
    settings = await db.get_propose_settings()
    if not settings:
        settings = {
            'locked_rarities': DEFAULT_LOCKED.copy(),
            'propose_cooldown': 100,
            'propose_cost': 20000,
            'acceptance_rate': 50,
            'propose_weights': DEFAULT_PROPOSE_WEIGHTS.copy()
        }
        await db.update_propose_settings(settings)
    
    # Create message showing current settings
    config_text = "<b>⚙️ ᴘʀᴏᴘᴏsᴇ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ</b>\n\n"
    
    # Cooldown
    cooldown_minutes = settings['propose_cooldown'] // 60
    cooldown_seconds = settings['propose_cooldown'] % 60
    config_text += f"<b>⏰ ᴄᴏᴏʟᴅᴏᴡɴ:</b> `{settings['propose_cooldown']}` seconds"
    if cooldown_minutes > 0:
        config_text += f" (`{cooldown_minutes}m {cooldown_seconds}s`)"
    config_text += "\n"
    
    # Cost
    config_text += f"<b>💰 ᴄᴏsᴛ:</b> `{settings['propose_cost']}` tokens\n"
    
    # Acceptance rate
    config_text += f"<b>📊 ᴀᴄᴄᴇᴘᴛᴀɴᴄᴇ ʀᴀᴛᴇ:</b> `{settings['acceptance_rate']}%`\n"
    
    # Locked rarities
    config_text += "\n<b>🔒 ʟᴏᴄᴋᴇᴅ ʀᴀʀɪᴛɪᴇs:</b>\n"
    if settings.get('locked_rarities'):
        for rarity in settings['locked_rarities']:
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            config_text += f"• {emoji} {rarity}\n"
    else:
        config_text += "• No rarities locked\n"
    
    # Usage instructions
    config_text += "\n<b>📝 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
    config_text += "• `/pcooldown <seconds>` - Set cooldown (10-3600)\n"
    config_text += "• `/pcost <tokens>` - Set cost (1000-100000)\n"
    config_text += "• `/pacceptance <percentage>` - Set acceptance rate (1-100)\n"
    config_text += "• `/proposelock` - Manage rarity locks"
    
    await message.reply_text(
        config_text
    )

async def prate_command(client: Client, message: Message):
    """Show or set rarity-specific propose rates"""
    user_id = message.from_user.id
    db = get_database()
    
    # Check if user is owner or OG
    if not (is_owner(user_id) or await is_og(db, user_id)):
        return
    
    # Get current settings
    settings = await db.get_propose_settings()
    rarity_rates = settings.get('rarity_rates', {})
    
    # If no arguments provided, show current rates
    if not message.text.split()[1:]:
        rate_text = "<b>📊 ᴄᴜʀʀᴇɴᴛ ᴘʀᴏᴘᴏsᴇ ʀᴀᴛᴇs:</b>\n\n"
        for rarity, rate in rarity_rates.items():
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            rate_text += f"• {emoji} {rarity}: `{rate}%`\n"
        
        rate_text += "\n<b>ᴛᴏ sᴇᴛ ʀᴀᴛᴇ:</b>\n`/prate <rarity> <percentage>`"
        await message.reply_text(
            rate_text
        )
        return
    
    # If arguments provided, set new rate
    if len(message.text.split()) != 3:
        await message.reply_text(
            "<b>❌ ɪɴᴠᴀʟɪᴅ ᴀʀɢᴜᴍᴇɴᴛs!</b>\n"
            "<b>ᴜsᴀɢᴇ:</b> `/prate <rarity> <percentage>`"
        )
        return
    
    rarity = message.text.split()[1]
    try:
        rate = int(message.text.split()[2])
        if not 1 <= rate <= 100:
            await message.reply_text(
                "<b>❌ ʀᴀᴛᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 100!</b>",
            )
            return
    except ValueError:
        await message.reply_text(
            "<b>❌ ɪɴᴠᴀʟɪᴅ ᴘᴇʀᴄᴇɴᴛᴀɢᴇ!</b>",
        )
        return
    
    # Check if rarity is valid
    if rarity not in RARITIES:
        await message.reply_text(
            "<b>❌ ɪɴᴠᴀʟɪᴅ ʀᴀʀɪᴛʏ!</b>\n"
            "<b>ᴠᴀʟɪᴅ ʀᴀʀɪᴛɪᴇs:</b>\n" + 
            "\n".join([f"• {r}" for r in RARITIES.keys()])
        )
        return
    
    # Update rate
    rarity_rates[rarity] = rate
    settings['rarity_rates'] = rarity_rates
    await db.update_propose_settings(settings)
    
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    await message.reply_text(
        f"<b>✅ {emoji} {rarity} ᴘʀᴏᴘᴏsᴇ ʀᴀᴛᴇ sᴇᴛ ᴛᴏ `{rate}%`!</b>"
    )

async def pweights_command(client: Client, message: Message):
    """Set or show propose weights per rarity (owner/OG only)"""
    user_id = message.from_user.id
    db = get_database()
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text("<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ ᴀɴᴅ ᴏɢs ᴏɴʟʏ!</b>")
        return
    settings = await db.get_propose_settings()
    weights = settings.get('propose_weights', DEFAULT_PROPOSE_WEIGHTS.copy())
    # Show current weights if no args
    args = message.text.split()
    if len(args) == 1:
        msg = "<b>🎲 ᴘʀᴏᴘᴏsᴇ ᴡᴇɪɢʜᴛs ʙʏ ʀᴀʀɪᴛʏ:</b>\n\n"
        for rarity, weight in weights.items():
            emoji = RARITY_EMOJIS.get(rarity, "❓")
            msg += f"• {emoji} {rarity}: <code>{weight}</code>\n"
        msg += "\n<b>ᴛᴏ sᴇᴛ:</b> <code>/pweights &lt;rarity&gt; &lt;weight&gt;</code>"
        await message.reply_text(msg)
        return
    if len(args) != 3:
        await message.reply_text("<b>❌ ᴜsᴀɢᴇ:</b> <code>/pweights &lt;rarity&gt; &lt;weight&gt;</code>")
        return
    rarity = args[1]
    try:
        weight = int(args[2])
        if weight < 0 or weight > 100:
            await message.reply_text("<b>❌ ᴡᴇɪɢʜᴛ ᴍᴜsᴛ ʙᴇ 0-100!</b>")
            return
    except ValueError:
        await message.reply_text("<b>❌ ᴡᴇɪɢʜᴛ ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ!</b>")
        return
    if rarity not in RARITIES:
        await message.reply_text("<b>❌ ɪɴᴠᴀʟɪᴅ ʀᴀʀɪᴛʏ!</b>")
        return
    weights[rarity] = weight
    settings['propose_weights'] = weights
    # If weight is 0, add to locked_rarities; else, remove from locked_rarities
    locked = set(settings.get('locked_rarities', DEFAULT_LOCKED))
    if weight == 0:
        locked.add(rarity)
    else:
        locked.discard(rarity)
    settings['locked_rarities'] = list(locked)
    await db.update_propose_settings(settings)
    await message.reply_text(f"<b>✅ ᴘʀᴏᴘᴏsᴇ ᴡᴇɪɢʜᴛ ғᴏʀ {rarity} sᴇᴛ ᴛᴏ {weight}!</b>")

def setup_propose_handlers(app: Client):
    """Setup propose command handlers"""
    app.on_message(filters.command("propose"))(propose_command)
    app.on_message(filters.command("proposelock"))(proposelock_command)
    app.on_message(filters.command("pcooldown"))(setcooldown_command)
    app.on_message(filters.command("pcost"))(setcost_command)
    app.on_message(filters.command("pacceptance"))(setacceptance_command)
    app.on_message(filters.command("pconfig"))(pconfig_command)
    app.on_message(filters.command("prate"))(prate_command)
    app.on_message(filters.command("pweights"))(pweights_command)
    app.on_message(filters.command("debugpropose"))(debug_propose_settings_command)
    app.on_message(filters.command("cleanuppropose"))(cleanup_propose_settings_command)

    app.on_callback_query(filters.regex(r"^propose_"))(propose_callback)

async def debug_propose_settings_command(client: Client, message: Message):
    """Debug propose settings - owner only"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ This command is restricted to the bot owner.")
        return
    
    try:
        db = get_database()
        async with db.pool.acquire() as conn:
            # Get all records from propose_settings table
            rows = await conn.fetch("SELECT * FROM propose_settings ORDER BY id")
            
            debug_text = "<b>🔍 ᴘʀᴏᴘᴏsᴇ sᴇᴛᴛɪɴɢs ᴅᴇʙᴜɢ</b>\n\n"
            
            if not rows:
                debug_text += "❌ No records found in propose_settings table"
            else:
                for row in rows:
                    debug_text += f"<b>📋 Record ID: {row['id']}</b>\n"
                    debug_text += f"• Cooldown: {row['propose_cooldown']}\n"
                    debug_text += f"• Cost: {row['propose_cost']}\n"
                    debug_text += f"• Acceptance Rate: {row['acceptance_rate']}\n"
                    debug_text += f"• Locked Rarities: {row['locked_rarities']}\n"
                    debug_text += f"• Updated At: {row['updated_at']}\n\n"
            
            # Also test the get_propose_settings method
            settings = await db.get_propose_settings()
            debug_text += f"<b>🔧 get_propose_settings() result:</b>\n"
            if settings:
                debug_text += f"• Cooldown: {settings.get('propose_cooldown', 'N/A')}\n"
                debug_text += f"• Cost: {settings.get('propose_cost', 'N/A')}\n"
                debug_text += f"• Acceptance Rate: {settings.get('acceptance_rate', 'N/A')}\n"
            else:
                debug_text += "❌ get_propose_settings() returned None"
        
        await message.reply_text(debug_text)
        
    except Exception as e:
        await message.reply_text(f"❌ Error debugging propose settings: {e}")

async def cleanup_propose_settings_command(client: Client, message: Message):
    """Clean up duplicate propose settings records - owner only"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ This command is restricted to the bot owner.")
        return
    
    try:
        db = get_database()
        async with db.pool.acquire() as conn:
            # Get all records
            rows = await conn.fetch("SELECT * FROM propose_settings ORDER BY id")
            
            if len(rows) <= 1:
                await message.reply_text("✅ No duplicate records found in propose_settings table.")
                return
            
            # Keep only the most recent record (highest ID)
            latest_record = rows[-1]
            records_to_delete = rows[:-1]
            
            # Delete all records except the latest one
            for record in records_to_delete:
                await conn.execute("DELETE FROM propose_settings WHERE id = $1", record['id'])
            
            await message.reply_text(
                f"✅ Cleaned up propose_settings table!\n"
                f"• Deleted {len(records_to_delete)} duplicate record(s)\n"
                f"• Kept record ID: {latest_record['id']}\n"
                f"• Latest cooldown: {latest_record['propose_cooldown']} seconds"
            )
        
    except Exception as e:
        await message.reply_text(f"❌ Error cleaning up propose settings: {e}")

async def ping_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ This command is restricted to the bot owner.")
        return
    start = time.monotonic()
    sent = await message.reply_text("Pinging...")
    end = time.monotonic()
    latency = int((end - start) * 1000)
    await sent.edit_text(f"🏓 Pong! <b>{latency} ms</b>")

