"""
SELL MODULE

Policy: Never remove or alter 'collected' entries from collection_history when a character is sold or transferred. Only append new entries for 'sold', 'gift', etc. This ensures daily/total collection stats are always accurate.
"""
import asyncio
from collections import Counter
from datetime import datetime, timedelta
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from modules.decorators import is_owner
from modules.postgres_database import get_database, get_rarity_emoji

from .decorators import check_banned
from .trade import action_manager





# Character selling prices
SELL_PRICES = {
    "Common": 6000,
    "Medium": 7400,
    "Rare": 9800,
    "Legendary": 14600,
    "Exclusive": 100000,
    "Elite": 180000,
    "Limited Edition": 460000,
    "Ultimate": 780000,
    "Supreme": 5000000,
    "Ethereal":  720000,
    "Mythic": 322000,
    "Zenith": 357000,
    "Premium": 5000000
}

# Async locks for sell confirmations
_sell_locks = {}

# Session storage for sell confirmation
_temp_data = {}

# Session storage for masssell confirmation
_masssell_temp = {}

# Processing flags to prevent spam clicks
_processing_sells = set()

# Global sell price event state
SELL_PRICE_EVENT = {"multiplier": 1.0, "end_time": None}

# Add your main group ID here
MAIN_GROUP_ID = -1002558794123  # Change this to your actual group ID

def get_sell_multiplier():
    now = datetime.utcnow()
    if SELL_PRICE_EVENT["end_time"] and now < SELL_PRICE_EVENT["end_time"]:
        return SELL_PRICE_EVENT["multiplier"]
    # Expired or not set
    SELL_PRICE_EVENT["multiplier"] = 1.0
    SELL_PRICE_EVENT["end_time"] = None
    return 1.0

@check_banned
async def sell_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    if await action_manager.is_user_busy(db, user_id):
        action_type = await action_manager.get_user_action(db, user_id)
        # If it's a sell/masssell action, but no session data, auto-clear and allow new sell
        if isinstance(action_type, str) and action_type.lower().strip() in ['sell', 'masssell']:
            if (action_type == 'sell' and user_id not in _temp_data) or (action_type == 'masssell' and user_id not in _masssell_temp):
                # Stale action, clear it
                await action_manager.clear_user_action(db, user_id)
            else:
                keyboard = [[InlineKeyboardButton("❌ Cancel Last Sell", callback_data="cancel_last_sell")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await message.reply_text(
                    f"❌ {action_manager.get_action_message(action_type)}",
                    reply_markup=reply_markup
                )
                return
        elif isinstance(action_type, str) and action_type:
            await message.reply_text(
                f"❌ {action_manager.get_action_message(action_type)}"
            )
            return
        # If action_type is None/empty, treat as no action (do not block)
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text(
            "❌ Please provide a character ID!\nUsage: /sell <id>"
        )
        return
    try:
        character_id = int(args[1])
    except ValueError:
        await message.reply_text(
            "❌ Please provide a valid character ID!"
        )
        return
    character = await db.get_character(character_id)
    user_data = await db.get_user(user_id)
    if not character:
        await message.reply_text(
            "❌ Character not found!"
        )
        return
    if character_id not in user_data.get('characters', []):
        await message.reply_text(
            "❌ You don't own this character!"
        )
        return
    sell_price = SELL_PRICES.get(character['rarity'], 0)
    multiplier = get_sell_multiplier()
    if multiplier > 1.0:
        sell_price = int(sell_price * multiplier)
        event_notice = f"\n\n🔥 <b>Sell Price Event Active!</b>\nAll sell prices are {multiplier}x!"
    else:
        event_notice = ""
    _temp_data[user_id] = {
        "character_id": character_id,
        "price": sell_price,
        "name": character['name'],
        "rarity": character['rarity'],
        "initiator_id": user_id  # Store initiator
    }
    await action_manager.set_user_action(db, user_id, 'sell', {
        'character_id': character_id,
        'price': sell_price
    })
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Sell", callback_data="sell_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="sell_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    formatted_price = f"{sell_price:,}"
    rarity_emoji = get_rarity_emoji(character['rarity'])
    caption = (
        f"{rarity_emoji} {character['name']}\n"
        f"Price: {formatted_price} Tokens\n"
        f"Are you sure you want to sell this Character?" + event_notice
    )
    photo = character.get('img_url', character.get('file_id'))
    if photo:
        await message.reply_photo(
            photo=photo,
            caption=caption,
            reply_markup=reply_markup
        )
    else:
        await message.reply_text(
            caption,
            reply_markup=reply_markup
        )

@check_banned
async def handle_sell_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    # Restrict button use to initiator only
    if user_id not in _temp_data or _temp_data[user_id].get('initiator_id') != user_id:
        await callback_query.answer("❌ Access Denied: Only the user who initiated this sell can use these buttons.", show_alert=True)
        return
    
    # Get or create lock for this user
    if user_id not in _sell_locks:
        _sell_locks[user_id] = asyncio.Lock()
    lock = _sell_locks[user_id]
    
    if callback_query.data == "cancel_last_sell":
        async with lock:
            await action_manager.clear_user_action(db, user_id)
            if user_id in _temp_data:
                del _temp_data[user_id]
            if user_id in _masssell_temp:
                del _masssell_temp[user_id]
            await callback_query.edit_message_text("❌ Last sell or masssell action cancelled!")
            # Clean up lock
            if user_id in _sell_locks:
                del _sell_locks[user_id]
        return
    
    if user_id not in _temp_data:
        await callback_query.edit_message_caption(
            "❌ Session expired! Please try again!"
        )
        return
    
    if callback_query.data == "sell_cancel":
        async with lock:
            await callback_query.edit_message_caption(
                "❌ Selling cancelled!"
            )
            await action_manager.clear_user_action(db, user_id)
            del _temp_data[user_id]
            # Clean up lock
            if user_id in _sell_locks:
                del _sell_locks[user_id]
        return
    
    if callback_query.data == "sell_confirm":
        # Set processing flag IMMEDIATELY to prevent spam clicks
        # NOTE: Never remove or alter 'collected' entries from collection_history on sell!
        # Only append a new 'sold' entry. This ensures daily top and stats are correct.
        if user_id in _processing_sells:
            await callback_query.answer("Please wait, your sell is being processed...", show_alert=True)
            return
        _processing_sells.add(user_id)
        
        try:
            # Check if user data exists in temp_data
            if user_id not in _temp_data:
                await callback_query.edit_message_caption(
                    "❌ Session expired! Please try again!"
                )
                await action_manager.clear_user_action(db, user_id)
                _processing_sells.discard(user_id)  # Clean up processing flag
                return
            
            async with lock:
                try:
                    # Double-check session data exists after acquiring lock
                    if user_id not in _temp_data:
                        await callback_query.edit_message_caption(
                            "❌ Session expired! Please try again!"
                        )
                        await action_manager.clear_user_action(db, user_id)
                        # Clean up lock and processing flag
                        if user_id in _sell_locks:
                            del _sell_locks[user_id]
                        _processing_sells.discard(user_id)
                        return
                    
                    char_data = _temp_data[user_id]
                    # Fetch only needed fields
                    user_data = await db.get_user(user_id)
                    if not user_data:
                        raise Exception("User not found")
                    if char_data['character_id'] not in user_data.get('characters', []):
                        await callback_query.edit_message_caption(
                            "❌ You no longer own this character!"
                        )
                        await action_manager.clear_user_action(db, user_id)
                        del _temp_data[user_id]
                        # Clean up lock and processing flag
                        if user_id in _sell_locks:
                            del _sell_locks[user_id]
                        _processing_sells.discard(user_id)
                        return
                    # Remove only one instance of the character
                    characters = user_data.get('characters', [])
                    char_id = char_data['character_id']
                    if char_id in characters:
                        characters.remove(char_id)
                    
                    # Add sold entry to collection history
                    sold_entry = {
                        'character_id': char_id,
                        'sold_at': datetime.now().isoformat(),
                        'source': 'sold'
                    }
                    
                    # Atomic wallet update and collection history update
                    # Use atomic update for Postgres
                    if hasattr(db, 'update_user_atomic'):
                        await db.update_user_atomic(user_id, characters, char_data['price'], [sold_entry])
                    else:
                        # Fallback for Mongo
                        await db.users.update_one(
                            {'user_id': user_id},
                            {
                                '$set': {'characters': characters},
                                '$inc': {'wallet': char_data['price']},
                                '$push': {'collection_history': sold_entry}
                            }
                        )
                    formatted_price = f"{char_data['price']:,}"
                    user_name = callback_query.from_user.first_name
                    await callback_query.edit_message_caption(
                        f"{user_name} has successfully sold this Character for {formatted_price} Tokens!"
                    )
                    # Log transaction
                    await db.log_user_transaction(user_id, "sell", {
                        "character_id": char_data['character_id'],
                        "name": char_data.get('name', ''),
                        "rarity": char_data.get('rarity', ''),
                        "price": char_data['price'],
                        "date": datetime.now().strftime('%Y-%m-%d')
                    })
                    await action_manager.clear_user_action(db, user_id)
                    del _temp_data[user_id]
                    # Clean up lock and processing flag
                    if user_id in _sell_locks:
                        del _sell_locks[user_id]
                    _processing_sells.discard(user_id)
                except Exception as e:
                    print(f"Error in sell confirmation for user {user_id}: {e}")
                    import traceback
                    print(f"Full traceback: {traceback.format_exc()}")
                    await callback_query.edit_message_caption(
                        "❌ An error occurred while selling the character!"
                    )
                    await action_manager.clear_user_action(db, user_id)
                    if user_id in _temp_data:
                        del _temp_data[user_id]
                    # Clean up lock and processing flag
                    if user_id in _sell_locks:
                        del _sell_locks[user_id]
                    _processing_sells.discard(user_id)
        except Exception as e:
            print(f"Error in sell confirmation for user {user_id}: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            await callback_query.edit_message_caption(
                "❌ An error occurred while selling the character!"
            )
            await action_manager.clear_user_action(db, user_id)
            if user_id in _temp_data:
                del _temp_data[user_id]
            # Clean up processing flag
            _processing_sells.discard(user_id)

@check_banned
async def masssell_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    # Clear any massgift session for this user
    try:
        from modules.trade import _massgift_temp
        if user_id in _massgift_temp:
            del _massgift_temp[user_id]
    except ImportError:
        pass
    if await action_manager.is_user_busy(db, user_id):
        action_type = await action_manager.get_user_action(db, user_id)
        await message.reply_text(f"❌ {action_manager.get_action_message(action_type)}")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ Please provide character IDs!\nUsage: /masssell <id1> <id2> ... (up to 998)")
        return
    try:
        char_ids = [int(x) for x in args[1:999]]  # Limit to 998
    except ValueError:
        await message.reply_text("❌ Please provide valid character IDs!")
        return
    user_data = await db.get_user(user_id)
    owned_characters = user_data.get('characters', []) if user_data else []
    owned_counts = Counter(owned_characters)
    requested_counts = Counter(char_ids)
    insufficient = [(str(cid), req_count) for cid, req_count in requested_counts.items() if owned_counts.get(cid, 0) < req_count]
    if insufficient:
        msg = "⚠️ Insufficient counts for: " + ", ".join(f"{cid} (needs {req_count})" for cid, req_count in insufficient)
        await message.reply_text(msg)
        return
    # Only keep character IDs the user owns, up to the number they own
    char_ids_to_sell = []
    temp_counts = Counter()
    for cid in char_ids:
        if owned_counts[cid] > temp_counts[cid]:
            char_ids_to_sell.append(cid)
            temp_counts[cid] += 1
    if not char_ids_to_sell:
        await message.reply_text("❌ None of these characters are valid or owned by you!")
        return
    # Batch fetch all character documents (PostgreSQL)
    if hasattr(db, 'get_characters_by_ids'):
        char_docs = await db.get_characters_by_ids(char_ids_to_sell)
    else:
        # Fallback for MongoDB (legacy, should not be used)
        char_docs = await db.characters.find({'character_id': {'$in': char_ids_to_sell}}).to_list(length=None)
    id_to_char = {c['character_id']: c for c in char_docs}
    # Count occurrences of each character
    char_counts = Counter(char_ids_to_sell)
    multiplier = get_sell_multiplier()
    total_tokens = 0
    summary_lines = []
    for cid, count in char_counts.items():
        char = id_to_char.get(cid)
        if not char:
            continue
        price = SELL_PRICES.get(char['rarity'], 100000) * count
        if multiplier > 1.0:
            price = int(price * multiplier)
        emoji = get_rarity_emoji(char['rarity'])
        summary_lines.append(f"🌙 {count}x {char['name']} [{emoji}]")
        total_tokens += price
    if multiplier > 1.0:
        event_notice = f"\n\n🔥 <b>Sell Price Event Active!</b>\nAll sell prices are {multiplier}x!"
    else:
        event_notice = ""
    _masssell_temp[user_id] = {
        'char_ids': char_ids_to_sell,
        'total_tokens': total_tokens,
        'lines': summary_lines,
        'initiator_id': user_id  # Store initiator
    }
    await action_manager.set_user_action(db, user_id, 'masssell', {'char_ids': char_ids_to_sell, 'total_tokens': total_tokens})
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Sell", callback_data="masssell_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="masssell_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = "<b>ℹ️ Are you sure you want to sell these characters?</b>\n\n"
    msg += '\n\n'.join(summary_lines)
    msg += f"\n\n<b>Total Tokens to Receive:</b> {total_tokens:,}{event_notice}\n\nAre you sure you want to sell these Characters?"
    await message.reply_text(msg, reply_markup=reply_markup)

@check_banned
async def handle_masssell_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    # Restrict button use to initiator only
    if user_id not in _masssell_temp or _masssell_temp[user_id].get('initiator_id') != user_id:
        await callback_query.answer("❌ Access Denied: Only the user who initiated this masssell can use these buttons.", show_alert=True)
        return
    
    # Get or create lock for this user
    if user_id not in _sell_locks:
        _sell_locks[user_id] = asyncio.Lock()
    lock = _sell_locks[user_id]
    
    # Always clear both masssell and massgift session data for this user after confirm/cancel
    def clear_all_mass_sessions():
        if user_id in _masssell_temp:
            del _masssell_temp[user_id]
        try:
            from modules.trade import _massgift_temp
            if user_id in _massgift_temp:
                del _massgift_temp[user_id]
        except ImportError:
            pass
    
    if callback_query.data == "masssell_cancel":
        await callback_query.edit_message_text("❌ Mass sell cancelled!")
        clear_all_mass_sessions()
        await action_manager.clear_user_action(db, user_id)
        # Clean up lock
        if user_id in _sell_locks:
            del _sell_locks[user_id]
        return
    elif callback_query.data == "masssell_confirm":
        # Set processing flag IMMEDIATELY to prevent spam clicks
        # NOTE: Never remove or alter 'collected' entries from collection_history on masssell!
        # Only append new 'sold' entries. This ensures daily top and stats are correct.
        if user_id in _processing_sells:
            await callback_query.answer("Please wait, your sell is being processed...", show_alert=True)
            return
        _processing_sells.add(user_id)
        try:
            # Check if user data exists in masssell_temp
            if user_id not in _masssell_temp:
                await callback_query.edit_message_text("❌ Session expired! Please try again!")
                clear_all_mass_sessions()
                await action_manager.clear_user_action(db, user_id)
                _processing_sells.discard(user_id)  # Clean up processing flag
                return
            async with lock:
                # Robust: Only allow confirmation if active_action is masssell
                # Fetch user_data and active_action inside the lock to ensure latest state
                user_data = await db.get_user(user_id)
                active_action = user_data.get('active_action') if user_data else None
                if not isinstance(active_action, dict):
                    active_action = {}
                
                if active_action.get('type') != 'masssell':
                    await callback_query.edit_message_text("❌ This masssell session is no longer valid (another action was started or confirmed).", disable_web_page_preview=True)
                    clear_all_mass_sessions()
                    await action_manager.clear_user_action(db, user_id)
                    # Clean up lock and processing flag
                    if user_id in _sell_locks:
                        del _sell_locks[user_id]
                    _processing_sells.discard(user_id)
                    return
                if user_id in _masssell_temp and _masssell_temp[user_id].get('completed'):
                    await callback_query.answer("This mass sell has already been processed.", show_alert=True)
                    _processing_sells.discard(user_id)
                    return
                if user_id not in _masssell_temp:
                    await callback_query.edit_message_text("❌ Session expired! Please try again!")
                    clear_all_mass_sessions()
                    # Clean up lock and processing flag
                    if user_id in _sell_locks:
                        del _sell_locks[user_id]
                    _processing_sells.discard(user_id)
                    return
                data = _masssell_temp[user_id]
                # Show processing answer immediately
                await callback_query.answer("Processing masssell...", show_alert=False)
                # Fetch only needed fields
                user_data = await db.get_user(user_id)
                owned_chars = user_data.get('characters', []) if user_data else []
                to_remove = list(data['char_ids'])
                new_chars = owned_chars.copy()
                for cid in to_remove:
                    if cid in new_chars:
                        new_chars.remove(cid)
                # If selling a lot, show processing message first
                if len(to_remove) > 50:
                    await callback_query.edit_message_text("⏳ Processing your mass sell... Please wait...")
                # Create sold entries for collection history
                sold_entries = []
                now = datetime.now()
                for cid in to_remove:
                    sold_entries.append({
                        'character_id': cid,
                        'sold_at': now.isoformat(),
                        'source': 'sold'
                    })
                # Atomic wallet update and collection history update
                # Use atomic update for Postgres
                if hasattr(db, 'update_user_atomic'):
                    await db.update_user_atomic(user_id, new_chars, data['total_tokens'], sold_entries)
                else:
                    # Fallback for Mongo
                    await db.users.update_one(
                        {'user_id': user_id},
                        {
                            '$set': {'characters': new_chars},
                            '$inc': {'wallet': data['total_tokens']},
                            '$push': {'collection_history': {'$each': sold_entries}}
                        }
                    )
                await callback_query.edit_message_text(f"✅ Successfully sold {len(to_remove)} characters for {data['total_tokens']:,} tokens!")
                await action_manager.clear_user_action(db, user_id)
                _masssell_temp[user_id]['completed'] = True
                clear_all_mass_sessions()
                # Clean up lock and processing flag
                if user_id in _sell_locks:
                    del _sell_locks[user_id]
                _processing_sells.discard(user_id)
        except Exception as e:
            print(f"Error in masssell confirmation for user {user_id}: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            await callback_query.edit_message_text("❌ An error occurred while mass selling!")
            await action_manager.clear_user_action(db, user_id)
            clear_all_mass_sessions()
            # Clean up processing flag
            _processing_sells.discard(user_id)

def setup_sell_handlers(app: Client):
    app.add_handler(filters.command("sell")(sell_command))
    app.add_handler(filters.command("masssell")(masssell_command))
    app.add_handler(filters.callback_query(lambda _, __, query: query.data and (query.data.startswith("sell_") or query.data == "cancel_last_sell"))(handle_sell_callback))
    app.add_handler(filters.callback_query(lambda _, __, query: query.data and query.data.startswith("masssell_"))(handle_masssell_callback))
