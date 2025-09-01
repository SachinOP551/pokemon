#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safari Zone Module for Pokemon Bot
Allows users to enter Safari Zone, catch Pokemon with Safari Balls
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType

from .decorators import check_banned
from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS
from .logging_utils import send_token_log

# Safari Zone constants
SAFARI_COST = 10  # 10 tokens to enter
SAFARI_BALLS = 30    # 30 Safari Balls per session
# Removed SAFARI_SESSION_DURATION - sessions now have no time limit

# Safari Zone rarities (Rare to Limited Edition)
SAFARI_RARITIES = ["Legendary", "Exclusive", "Elite", "Limited Edition"]

# Catch rates for different rarities (percentage)
CATCH_RATES = {
    "Legendary": 25,
    "Exclusive": 18,
    "Elite": 12,
    "Limited Edition": 8
}

# Active Safari Zone sessions
active_safari_sessions: Dict[int, Dict] = {}

# Safari Zone locks to prevent race conditions
safari_locks: Dict[int, asyncio.Lock] = {}

# Battle locks to prevent multiple engagements
battle_locks: Dict[int, asyncio.Lock] = {}

@check_banned
async def safari_command(client: Client, message: Message):
    """Handle /safari command - Show Safari Zone information"""
    # Check if command is used in bot DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "💡 <b>Please send this command in a private chat with the bot.</b>"
        )
        return
    
    user_id = message.from_user.id
    
    # Initialize lock for user if not exists
    if user_id not in safari_locks:
        safari_locks[user_id] = asyncio.Lock()
    
    async with safari_locks[user_id]:
        db = get_database()
        
        # Get user data
        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "❌ <b>You need to register first! Use /start to create an account.</b>"
            )
            return
        
        # Check if user already has an active Safari session
        if user_id in active_safari_sessions:
            session = active_safari_sessions[user_id]
            await message.reply_text(
                f"🎯 <b>You are currently in Safari Zone!</b>\n\n"
                f"🎾 <b>Safari Balls left:</b> {session['balls_left']}\n"
                f"📈 <b>Pokemon caught:</b> {len(session['pokemon_caught'])}\n\n"
                f"💡 <i>Use /hunt to find Pokemon or /exit to leave Safari Zone!</i>"
            )
            return
        
        # Check daily limit (once per day)
        last_safari = user.get('last_safari')
        if last_safari:
            if isinstance(last_safari, str):
                last_safari_dt = datetime.fromisoformat(last_safari)
            else:
                last_safari_dt = last_safari
            
            # Check if it's been 24 hours since last Safari
            next_safari = last_safari_dt + timedelta(days=1)
            if datetime.now() < next_safari:
                time_left = next_safari - datetime.now()
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                await message.reply_text(
                    f"❌ <b>You've already used Safari Zone today!</b>\n\n"
                    f"⏰ <b>Next Safari available in:</b> {hours}h {minutes}m\n\n"
                    f"💡 <i>Safari Zone can only be used once per day.</i>"
                )
                return
        
        # Show Safari Zone information
        wallet = user.get('wallet', 0)
        info_text = (
            f"🌿 <b>Safari Zone Information</b>\n\n"
            f"💰 <b>Entry Cost:</b> {SAFARI_COST:,} tokens\n"
            f"🎾 <b>Safari Balls:</b> {SAFARI_BALLS} balls per session\n"
            f"⏰ <b>Session Duration:</b> No time limit\n"
            f"🔄 <b>Daily Limit:</b> Once per day\n\n"
            f"🎯 <b>Available Pokemon:</b>\n"
            f"• Legendary\n"
            f"• Exclusive\n"
            f"• Elite\n"
            f"• Limited Edition\n\n"
            f"💳 <b>Your Balance:</b> {wallet:,} tokens\n\n"
        )
        
        if wallet >= SAFARI_COST:
            info_text += "✅ <b>You have enough tokens to enter Safari Zone!</b>\n\n💡 <i>Use /enter to start your Safari adventure!</i>"
        else:
            info_text += f"❌ <b>You need {SAFARI_COST - wallet:,} more tokens to enter Safari Zone!</b>\n\n💡 <i>Earn more tokens by playing games or collecting Pokemon!</i>"
        
        await message.reply_text(info_text)

@check_banned
async def enter_command(client: Client, message: Message):
    """Handle /enter command - Enter Safari Zone and pay fees"""
    # Check if command is used in bot DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "💡 <b>Please send this command in a private chat with the bot.</b>"
        )
        return
    
    user_id = message.from_user.id
    
    # Initialize lock for user if not exists
    if user_id not in safari_locks:
        safari_locks[user_id] = asyncio.Lock()
    
    async with safari_locks[user_id]:
        db = get_database()
        
        # Get user data
        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "❌ <b>You need to register first! Use /start to create an account.</b>"
            )
            return
        
        # Check if user already has an active Safari session
        if user_id in active_safari_sessions:
            session = active_safari_sessions[user_id]
            await message.reply_text(
                f"🎯 <b>You are already in Safari Zone!</b>\n\n"
                f"🎾 <b>Safari Balls left:</b> {session['balls_left']}\n"
                f"📈 <b>Pokemon caught:</b> {len(session['pokemon_caught'])}\n\n"
                f"💡 <i>Use /hunt to find Pokemon or /exit to leave Safari Zone!</i>"
            )
            return
        
        # Check daily limit (once per day)
        last_safari = user.get('last_safari')
        if last_safari:
            if isinstance(last_safari, str):
                last_safari_dt = datetime.fromisoformat(last_safari)
            else:
                last_safari_dt = last_safari
            
            # Check if it's been 24 hours since last Safari
            next_safari = last_safari_dt + timedelta(days=1)
            if datetime.now() < next_safari:
                time_left = next_safari - datetime.now()
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                await message.reply_text(
                    f"❌ <b>You've already used Safari Zone today!</b>\n\n"
                    f"⏰ <b>Next Safari available in:</b> {hours}h {minutes}m\n\n"
                    f"💡 <i>Safari Zone can only be used once per day.</i>"
                )
                return
        
        # Check if user has enough tokens
        wallet = user.get('wallet', 0)
        if wallet < SAFARI_COST:
            await message.reply_text(
                f"❌ <b>Insufficient tokens to enter Safari Zone!</b>\n\n"
                f"💰 <b>Required:</b> {SAFARI_COST:,} tokens\n"
                f"💳 <b>Your balance:</b> {wallet:,} tokens\n\n"
                f"💡 <i>Earn more tokens by playing games or collecting Pokemon!</i>"
            )
            return
        
        # Deduct tokens and start Safari session
        new_wallet = wallet - SAFARI_COST
        await db.update_user(user_id, {'wallet': new_wallet})
        
        # Create Safari session (no time limit)
        active_safari_sessions[user_id] = {
            'start_time': datetime.now(),
            'balls_left': SAFARI_BALLS,
            'pokemon_caught': [],
            'current_pokemon': None,
            'in_battle': False,
            'last_message_id': None
        }
        
        # Update last Safari time
        await db.update_user(user_id, {'last_safari': datetime.now()})
        
        # Log the transaction
        await send_token_log(client, message.from_user, None, SAFARI_COST, action="safari_zone_entry")
        
        # Show entry success message
        entry_text = (
            f"🎯 <b>Welcome to Safari Zone!</b>\n\n"
            f"💰 <b>Entry fee paid:</b> {SAFARI_COST:,} tokens\n"
            f"🎾 <b>Safari Balls:</b> {SAFARI_BALLS}\n"
            f"⏰ <b>Session Duration:</b> No time limit\n\n"
            f"💡 <i>Use /hunt to start hunting for Pokemon or /exit to leave!</i>"
        )
        
        await message.reply_text(entry_text)
        
        # Start session timer
        asyncio.create_task(safari_session_timer(client, user_id))

@check_banned
async def exit_command(client: Client, message: Message):
    """Handle /exit command - Exit Safari Zone"""
    # Check if command is used in bot DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "💡 <b>Please send this command in a private chat with the bot.</b>"
        )
        return
    
    user_id = message.from_user.id
    
    # Check if user has an active Safari session
    if user_id not in active_safari_sessions:
        await message.reply_text(
            "❌ <b>You are not in Safari Zone!</b>\n\n"
            f"💡 <i>Use /safari to see information and /enter to start your Safari adventure!</i>"
        )
        return
    
    # End the Safari session
    await end_safari_session(client, user_id, "User exited")
    await message.reply_text("🚪 <b>You have exited Safari Zone!</b>")

@check_banned
async def hunt_command(client: Client, message: Message):
    """Handle /hunt command - Hunt Pokemon in Safari Zone (only when in session)"""
    # Check if command is used in bot DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "💡 <b>Please send this command in a private chat with the bot.</b>"
        )
        return
    
    user_id = message.from_user.id
    
    # Initialize lock for user if not exists
    if user_id not in safari_locks:
        safari_locks[user_id] = asyncio.Lock()
    
    async with safari_locks[user_id]:
        db = get_database()
        
        # Get user data
        user = await db.get_user(user_id)
        if not user:
            await message.reply_text(
                "❌ <b>You need to register first! Use /start to create an account.</b>"
            )
            return
        
        # Check if user has an active Safari session
        if user_id not in active_safari_sessions:
            await message.reply_text(
                "❌ <b>You need to enter Safari Zone first!</b>\n\n"
                f"💡 <i>Use /safari to see information and /enter to start your Safari adventure!</i>"
            )
            return
        
        session = active_safari_sessions[user_id]
        
        # Check if user is already in battle
        if session.get('in_battle', False):
            await message.reply_text(
                "⚔️ <b>You are already in a battle!</b>\n\n"
                "💡 <i>Finish your current battle before hunting for a new Pokemon.</i>"
            )
            return
        
        # Start hunting - spawn a Pokemon
        await hunt_pokemon(client, message, user_id)

async def hunt_pokemon(client: Client, message: Message, user_id: int):
    """Hunt for a Pokemon in Safari Zone"""
    if user_id not in active_safari_sessions:
        await message.reply_text("❌ <b>No active Safari session found!</b>")
        return
    
    session = active_safari_sessions[user_id]
    
    # Removed session expiration check - sessions have no time limit
    
    # Spawn a new Pokemon
    pokemon = await spawn_safari_pokemon(user_id)
    if not pokemon:
        await message.reply_text("❌ <b>Failed to spawn Pokemon in Safari Zone!</b>")
        return
    
    # Create Pokemon appearance message
    rarity_emoji = get_rarity_emoji(pokemon['rarity'])
    
    appearance_text = f"A Wild <b>{pokemon['name']}</b> ({rarity_emoji}) has appeared!"
    
    # Create keyboard with Engage button (include Pokemon ID for validation)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Engage", callback_data=f"hunt_engage_{user_id}_{pokemon['character_id']}")]
    ])
    
    # Send the Pokemon appearance message with image
    try:
        # Try to send with image first
        if pokemon.get('img_url'):
            try:
                # Always send a new photo message, don't try to edit
                await message.reply_photo(pokemon['img_url'], caption=appearance_text, reply_markup=keyboard)
                return
            except Exception as img_error:
                print(f"Error sending Pokemon image: {img_error}")
                # Fall back to text only
        
        # Fallback to text only
        if hasattr(message, 'edit_text'):
            await message.edit_text(appearance_text, reply_markup=keyboard)
        else:
            await message.reply_text(appearance_text, reply_markup=keyboard)
    except Exception as e:
        print(f"Error editing hunt message: {e}")
        await message.reply_text(appearance_text, reply_markup=keyboard)

async def show_battle_interface(client: Client, message: Message, user_id: int):
    """Show the battle interface when user engages with Pokemon"""
    if user_id not in active_safari_sessions:
        await message.reply_text("❌ <b>No active Safari session found!</b>")
        return
    
    session = active_safari_sessions[user_id]
    current_pokemon = session['current_pokemon']
    
    if not current_pokemon:
        await message.reply_text("❌ <b>No Pokemon to battle!</b>")
        return
    
    # Create battle interface message
    rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
    
    battle_text = (
        f"Wild <b>{current_pokemon['name']}</b> [{current_pokemon['anime']} - {rarity_emoji} {current_pokemon['rarity']}]\n"
        f"Safari Balls: {session['balls_left']}"
    )
    
    # Create keyboard with battle options
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎾 Throw Ball", callback_data=f"hunt_throw_{user_id}"),
            InlineKeyboardButton("🏃 Run", callback_data=f"hunt_run_{user_id}")
        ]
    ])
    
    # Send the battle interface (text only)
    try:
        if hasattr(message, 'edit_text'):
            await message.edit_text(battle_text, reply_markup=keyboard)
        else:
            await message.reply_text(battle_text, reply_markup=keyboard)
    except Exception as e:
        print(f"Error editing battle message: {e}")
        await message.reply_text(battle_text, reply_markup=keyboard)

async def spawn_safari_pokemon(user_id: int) -> Optional[Dict]:
    """Spawn a random Pokemon for Safari Zone (Rare to Limited Edition)"""
    if user_id not in active_safari_sessions:
        return None
    
    try:
        db = get_database()
        
        # Get random character from Safari rarities, excluding Team and Trainer regions
        character = await db.get_random_character_by_rarities(SAFARI_RARITIES)
        
        # Filter out Team and Trainer regions
        max_attempts = 50  # Prevent infinite loop
        attempts = 0
        
        while character and attempts < max_attempts:
            # Check if character is from excluded regions
            anime = character.get('anime', '').lower()
            if 'team' not in anime and 'trainer' not in anime:
                active_safari_sessions[user_id]['current_pokemon'] = character
                return character
            
            # Try to get another character
            character = await db.get_random_character_by_rarities(SAFARI_RARITIES)
            attempts += 1
        
        # If no suitable character found from Safari rarities, try fallback
        if not character:
            character = await db.get_random_character()
            attempts = 0
            
            while character and attempts < max_attempts:
                anime = character.get('anime', '').lower()
                if 'team' not in anime and 'trainer' not in anime:
                    active_safari_sessions[user_id]['current_pokemon'] = character
                    return character
                
                character = await db.get_random_character()
                attempts += 1
        
        return None
        
    except Exception as e:
        print(f"Error spawning Safari Pokemon: {e}")
        return None

async def safari_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle Safari Zone callback queries"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if not data.startswith(("safari_", "hunt_")):
        return
    
    # Check if user has active session
    if user_id not in active_safari_sessions:
        await callback_query.answer("❌ No active Safari session!", show_alert=True)
        return
    
    session = active_safari_sessions[user_id]
    
    # Removed session expiration check - sessions have no time limit
    
    # Handle new hunt callbacks
    if data.startswith(f"hunt_engage_{user_id}_"):
        # Extract Pokemon ID from callback data
        try:
            pokemon_id = int(data.split("_")[-1])
            await handle_hunt_engage(client, callback_query, user_id, pokemon_id)
        except (ValueError, IndexError):
            await callback_query.answer("😔 This Pokemon has fled!", show_alert=True)
    elif data == f"hunt_throw_{user_id}":
        await handle_hunt_throw(client, callback_query, user_id)
    elif data == f"hunt_run_{user_id}":
        await handle_hunt_run(client, callback_query, user_id)
    # Handle old safari callbacks for compatibility
    elif data == f"safari_catch_{user_id}":
        await handle_safari_catch(client, callback_query, user_id)
    elif data == f"safari_run_{user_id}":
        await handle_safari_run(client, callback_query, user_id)
    elif data == f"safari_stats_{user_id}":
        await handle_safari_stats(client, callback_query, user_id)
    elif data == f"safari_exit_{user_id}":
        await handle_safari_exit(client, callback_query, user_id)
    # Handle old engage buttons - show Pokemon fled message
    elif data.startswith("safari_engage_") or data.startswith("engage_"):
        await callback_query.answer("😔 This Pokemon has fled!", show_alert=True)

async def handle_hunt_engage(client: Client, callback_query: CallbackQuery, user_id: int, pokemon_id: int):
    """Handle engaging with a Pokemon"""
    # Initialize battle lock for user if not exists
    if user_id not in battle_locks:
        battle_locks[user_id] = asyncio.Lock()
    
    async with battle_locks[user_id]:
        session = active_safari_sessions[user_id]
        
        # Check if already in battle
        if session.get('in_battle', False):
            await callback_query.answer("⚔️ You are already in a battle!", show_alert=True)
            return
        
        current_pokemon = session['current_pokemon']
        
        # Check if the Pokemon ID matches the current Pokemon
        if not current_pokemon or current_pokemon.get('character_id') != pokemon_id:
            await callback_query.answer("😔 This Pokemon has fled!", show_alert=True)
            return
        
        # Set battle state
        session['in_battle'] = True
        
        # Create battle interface message
        rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
        
        battle_text = (
            f"Wild <b>{current_pokemon['name']}</b> [{current_pokemon['anime']} - {rarity_emoji} {current_pokemon['rarity']}]\n"
            f"Safari Balls: {session['balls_left']}"
        )
        
        # Create keyboard with battle options
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎾 Throw Ball", callback_data=f"hunt_throw_{user_id}"),
                InlineKeyboardButton("🏃 Run", callback_data=f"hunt_run_{user_id}")
            ]
        ])
        
        # Send the battle interface as a new message
        battle_message = await callback_query.message.reply_text(battle_text, reply_markup=keyboard)
        session['last_message_id'] = battle_message.id
        
        await callback_query.answer("⚔️ Engaging with Pokemon!", show_alert=False)

async def handle_hunt_throw(client: Client, callback_query: CallbackQuery, user_id: int):
    """Handle throwing a Safari Ball"""
    # Initialize battle lock for user if not exists
    if user_id not in battle_locks:
        battle_locks[user_id] = asyncio.Lock()
    
    async with battle_locks[user_id]:
        session = active_safari_sessions[user_id]
        
        # Check if user has Safari Balls
        if session['balls_left'] <= 0:
            await callback_query.answer("❌ No Safari Balls left!", show_alert=True)
            return
        
        current_pokemon = session['current_pokemon']
        if not current_pokemon:
            await callback_query.answer("❌ No Pokemon to catch!", show_alert=True)
            return
        
        # Deduct Safari Ball
        session['balls_left'] -= 1
        
        # Calculate catch success
        catch_rate = CATCH_RATES.get(current_pokemon['rarity'], 15)
        catch_success = random.randint(1, 100) <= catch_rate
        
        # Show throwing animation
        await show_throwing_animation(client, callback_query, user_id, catch_success, current_pokemon)

async def show_throwing_animation(client: Client, callback_query: CallbackQuery, user_id: int, catch_success: bool, current_pokemon: dict):
    """Show the throwing animation with dots and stars"""
    session = active_safari_sessions[user_id]
    rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
    
    # Initial throw message
    throw_text = f"You used one Safari ball"
    
    try:
        await callback_query.edit_message_text(throw_text)
    except Exception as e:
        print(f"Error editing throw message: {e}")
        await callback_query.message.reply_text(throw_text)
    
    # Wait a moment
    await asyncio.sleep(1)
    
    # Show dots animation
    for i in range(3):
        dots = "•" * (i + 1)
        animation_text = f"You used one Safari ball\n{dots}"
        
        try:
            await callback_query.edit_message_text(animation_text)
        except Exception as e:
            print(f"Error editing animation message: {e}")
        
        await asyncio.sleep(0.8)
    
    if catch_success:
        # Show stars animation
        for i in range(3):
            stars = "☆" * (i + 1)
            stars_text = f"You used one Safari ball\n{stars}"
            
            try:
                await callback_query.edit_message_text(stars_text)
            except Exception as e:
                print(f"Error editing stars message: {e}")
            
            await asyncio.sleep(0.5)
        
        # Pokemon caught!
        db = get_database()
        await db.add_character_to_user(user_id, current_pokemon['character_id'], source='safari')
        
        # Add to caught list
        session['pokemon_caught'].append(current_pokemon)
        
        # Clear current Pokemon and reset battle state
        session['current_pokemon'] = None
        session['in_battle'] = False
        
        # Simple success message - edit the current message
        success_text = f"You caught a Wild <b>{current_pokemon['name']}</b>!"
        
        try:
            await callback_query.edit_message_text(success_text)
        except Exception as e:
            print(f"Error editing catch success message: {e}")
            await callback_query.message.reply_text(success_text)
        
        await callback_query.answer("🎉 Pokemon caught!", show_alert=False)
        
    else:
        # Pokemon escaped - check if it should flee
        break_free_messages = [
            "The Pokemon broke free!",
            "The Pokemon escaped from the Safari Ball!",
            "The Safari Ball missed its target!",
            "The Pokemon dodged the Safari Ball!"
        ]
        
        flee_messages = [
            "The Pokemon shook free and ran away!",
            "The Pokemon fled from the battle!",
            "The Pokemon disappeared into the wild!"
        ]
        
        rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
        
        # 30% chance for Pokemon to flee after failed catch attempt
        pokemon_fled = random.randint(1, 100) <= 30
        
        if pokemon_fled:
            # Pokemon fled - clear current Pokemon and hunt for new one
            session['current_pokemon'] = None
            session['in_battle'] = False
            
            # Use flee message - no interface buttons when Pokemon flees
            flee_text = random.choice(flee_messages)
            failed_text = f"😔 <b>{flee_text}</b>\n\nWild <b>{current_pokemon['name']}</b> [{current_pokemon['anime']} - {rarity_emoji} {current_pokemon['rarity']}]\nSafari Balls: {session['balls_left']}"
            
            # Store the target message for editing
            target_message = callback_query.message
            
            try:
                await callback_query.edit_message_text(failed_text)
            except Exception as e:
                print(f"Error editing catch failed message: {e}")
                # Send new message and try to delete the original one with buttons
                new_message = await callback_query.message.reply_text(failed_text)
                try:
                    await target_message.delete()
                except Exception as delete_error:
                    print(f"Error deleting original message: {delete_error}")
            
            await callback_query.answer("😔 Pokemon fled!", show_alert=False)
            
        else:
            # Pokemon didn't flee - show battle interface again
            break_free_text = random.choice(break_free_messages)
            failed_text = (
                f"😔 <b>{break_free_text}</b>\n\n"
                f"Wild <b>{current_pokemon['name']}</b> [{current_pokemon['anime']} - {rarity_emoji} {current_pokemon['rarity']}]\n"
                f"Safari Balls: {session['balls_left']}\n\n"
                f"💪 <i>Try again or run away!</i>"
            )
            
            # Store the target message for editing
            target_message = callback_query.message
            
            try:
                await callback_query.edit_message_text(failed_text, reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🎾 Throw Ball", callback_data=f"hunt_throw_{user_id}"),
                        InlineKeyboardButton("🏃 Run", callback_data=f"hunt_run_{user_id}")
                    ]
                ]))
            except Exception as e:
                print(f"Error editing catch failed message: {e}")
                # Send new message and try to delete the original one with buttons
                new_message = await callback_query.message.reply_text(failed_text, reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🎾 Throw Ball", callback_data=f"hunt_throw_{user_id}"),
                        InlineKeyboardButton("🏃 Run", callback_data=f"hunt_run_{user_id}")
                    ]
                ]))
                try:
                    await target_message.delete()
                except Exception as delete_error:
                    print(f"Error deleting original message: {delete_error}")
            
            await callback_query.answer("😔 Pokemon escaped!", show_alert=False)

async def handle_hunt_run(client: Client, callback_query: CallbackQuery, user_id: int):
    """Handle running away from current Pokemon"""
    # Initialize battle lock for user if not exists
    if user_id not in battle_locks:
        battle_locks[user_id] = asyncio.Lock()
    
    async with battle_locks[user_id]:
        session = active_safari_sessions[user_id]
        
        # Get current Pokemon info before clearing
        current_pokemon = session['current_pokemon']
        if current_pokemon:
            rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
            escape_text = f"You Escaped From Wild <b>{current_pokemon['name']}</b> ({rarity_emoji})"
            
            # Store the target message for editing
            target_message = callback_query.message
            
            try:
                await callback_query.edit_message_text(escape_text)
            except Exception as e:
                print(f"Error editing escape message: {e}")
                # Send new message and try to delete the original one with buttons
                new_message = await callback_query.message.reply_text(escape_text)
                try:
                    await target_message.delete()
                except Exception as delete_error:
                    print(f"Error deleting original message: {delete_error}")
        
        # Clear current Pokemon and reset battle state
        session['current_pokemon'] = None
        session['in_battle'] = False
        
        await callback_query.answer("🏃 Ran away!", show_alert=False)

async def handle_safari_catch(client: Client, callback_query: CallbackQuery, user_id: int):
    """Handle Safari Ball throw attempt"""
    session = active_safari_sessions[user_id]
    
    # Check if user has Safari Balls
    if session['balls_left'] <= 0:
        await callback_query.answer("❌ No Safari Balls left!", show_alert=True)
        return
    
    current_pokemon = session['current_pokemon']
    if not current_pokemon:
        await callback_query.answer("❌ No Pokemon to catch!", show_alert=True)
        return
    
    # Deduct Safari Ball
    session['balls_left'] -= 1
    
    # Calculate catch success
    catch_rate = CATCH_RATES.get(current_pokemon['rarity'], 15)
    catch_success = random.randint(1, 100) <= catch_rate
    
    if catch_success:
        # Pokemon caught!
        db = get_database()
        await db.add_character_to_user(user_id, current_pokemon['character_id'], source='safari')
        
        # Add to caught list
        session['pokemon_caught'].append(current_pokemon)
        
        # Clear current Pokemon and reset battle state
        session['current_pokemon'] = None
        session['in_battle'] = False
        
        # Simple success message - edit the current message
        success_text = f"You caught a Wild <b>{current_pokemon['name']}</b>!"
        
        try:
            await callback_query.edit_message_text(success_text)
        except Exception as e:
            print(f"Error editing catch success message: {e}")
            await callback_query.message.reply_text(success_text)
        await callback_query.answer("🎉 Pokemon caught!", show_alert=False)
        
    else:
        # Pokemon escaped - check if it should flee
        break_free_messages = [
            "The Pokemon broke free!",
            "The Pokemon escaped from the Safari Ball!",
            "The Safari Ball missed its target!",
            "The Pokemon dodged the Safari Ball!"
        ]
        
        flee_messages = [
            "The Pokemon shook free and ran away!",
            "The Pokemon fled from the battle!",
            "The Pokemon disappeared into the wild!"
        ]
        
        rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
        
        # 30% chance for Pokemon to flee after failed catch attempt
        pokemon_fled = random.randint(1, 100) <= 30
        
        if pokemon_fled:
            # Pokemon fled - clear current Pokemon and hunt for new one
            session['current_pokemon'] = None
            session['in_battle'] = False
            
            # Use flee message - no interface buttons when Pokemon flees
            flee_text = random.choice(flee_messages)
            failed_text = f"😔 <b>{flee_text}</b>\n\nWild <b>{current_pokemon['name']}</b> [{current_pokemon['anime']} - {rarity_emoji} {current_pokemon['rarity']}]\nSafari Balls: {session['balls_left']}"
            
            # Store the target message for editing
            target_message = callback_query.message
            
            try:
                await callback_query.edit_message_text(failed_text)
            except Exception as e:
                print(f"Error editing catch failed message: {e}")
                # Send new message and try to delete the original one with buttons
                new_message = await callback_query.message.reply_text(failed_text)
                try:
                    await target_message.delete()
                except Exception as delete_error:
                    print(f"Error deleting original message: {delete_error}")
            
            await callback_query.answer("😔 Pokemon fled!", show_alert=False)
            
        else:
            # Pokemon didn't flee - show battle interface again
            break_free_text = random.choice(break_free_messages)
            failed_text = (
                f"😔 <b>{break_free_text}</b>\n\n"
                f"👤 <b>Name:</b> {current_pokemon['name']}\n"
                f"{rarity_emoji} <b>Rarity:</b> {current_pokemon['rarity']}\n\n"
                f"🎾 <b>Safari Balls left:</b> {session['balls_left']}\n\n"
                f"💪 <i>Try again or run away to find another Pokemon!</i>"
            )
            
            # Store the target message for editing
            target_message = callback_query.message
            
            try:
                await callback_query.edit_message_text(failed_text)
            except Exception as e:
                print(f"Error editing catch failed message: {e}")
                # Send new message and try to delete the original one with buttons
                new_message = await callback_query.message.reply_text(failed_text)
                try:
                    await target_message.delete()
                except Exception as delete_error:
                    print(f"Error deleting original message: {delete_error}")
            
            await callback_query.answer("😔 Pokemon escaped!", show_alert=False)
            
            # Show interface again after a moment
            await asyncio.sleep(2)
            await show_battle_interface(client, callback_query.message, user_id)

async def handle_safari_run(client: Client, callback_query: CallbackQuery, user_id: int):
    """Handle running away from current Pokemon"""
    session = active_safari_sessions[user_id]
    
    # Get current Pokemon info before clearing
    current_pokemon = session['current_pokemon']
    if current_pokemon:
        rarity_emoji = get_rarity_emoji(current_pokemon['rarity'])
        escape_text = f"You Escaped From Wild <b>{current_pokemon['name']}</b> ({rarity_emoji})"
        
        # Store the target message for editing
        target_message = callback_query.message
        
        try:
            await callback_query.edit_message_text(escape_text)
        except Exception as e:
            print(f"Error editing escape message: {e}")
            # Send new message and try to delete the original one with buttons
            new_message = await callback_query.message.reply_text(escape_text)
            try:
                await target_message.delete()
            except Exception as delete_error:
                print(f"Error deleting original message: {delete_error}")
    
    # Clear current Pokemon
    session['current_pokemon'] = None
    
    await callback_query.answer("🏃 Ran away!", show_alert=False)

async def handle_safari_stats(client: Client, callback_query: CallbackQuery, user_id: int):
    """Show Safari Zone session statistics"""
    session = active_safari_sessions[user_id]
    
    # No time limit for Safari sessions
    minutes = 0
    seconds = 0
    
    # Count Pokemon by rarity
    rarity_counts = {}
    for pokemon in session['pokemon_caught']:
        rarity = pokemon['rarity']
        rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
    
    stats_text = (
        f"📊 <b>Safari Zone Statistics</b>\n\n"
        f"🎾 <b>Safari Balls left:</b> {session['balls_left']}\n"
        f"📈 <b>Total Pokemon caught:</b> {len(session['pokemon_caught'])}\n\n"
    )
    
    if rarity_counts:
        stats_text += "🎯 <b>Caught by rarity:</b>\n"
        for rarity, count in sorted(rarity_counts.items(), key=lambda x: RARITIES.get(x[0], 0), reverse=True):
            emoji = get_rarity_emoji(rarity)
            stats_text += f"{emoji} {rarity}: {count}\n"
    
    stats_text += "\n💡 <i>Keep exploring to catch more Pokemon!</i>"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Safari", callback_data=f"safari_back_{user_id}")]
    ])
    
    try:
        await callback_query.edit_message_text(stats_text, reply_markup=keyboard)
    except Exception as e:
        print(f"Error editing stats message: {e}")
        await callback_query.message.reply_text(stats_text, reply_markup=keyboard)
    await callback_query.answer()

async def handle_safari_exit(client: Client, callback_query: CallbackQuery, user_id: int):
    """Handle exiting Safari Zone"""
    await end_safari_session(client, user_id, "User exited")
    await callback_query.answer("🚪 Exited Safari Zone!", show_alert=False)

async def safari_back_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle back button from stats"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if data.startswith("safari_back_"):
        user_id = int(data.split("_")[-1])
        if user_id in active_safari_sessions:
            # Just show a message that they need to use /hunt to find Pokemon
            await callback_query.message.reply_text("🔍 Use /hunt to find a new Pokemon!")
            await callback_query.answer()

async def safari_session_timer(client: Client, user_id: int):
    """Timer task for Safari Zone session - now just monitors for session end"""
    try:
        while user_id in active_safari_sessions:
            session = active_safari_sessions[user_id]
            
            # Check if Safari balls are exhausted
            if session['balls_left'] <= 0:
                await end_safari_session(client, user_id, "Safari balls exhausted")
                break
            
            # Wait 30 seconds before checking again
            await asyncio.sleep(30)
            
    except Exception as e:
        print(f"Error in Safari session timer: {e}")
        # Clean up session on error
        if user_id in active_safari_sessions:
            del active_safari_sessions[user_id]

async def end_safari_session(client: Client, user_id: int, reason: str = "Session ended"):
    """End Safari Zone session and show summary"""
    if user_id not in active_safari_sessions:
        return
    
    session = active_safari_sessions[user_id]
    caught_pokemon = session['pokemon_caught']
    
    # Remove session
    del active_safari_sessions[user_id]
    
    # Create summary message
    if caught_pokemon:
        summary_text = (
            f"🏁 <b>Safari Zone Session Complete!</b>\n\n"
            f"📊 <b>Pokemon caught:</b> {len(caught_pokemon)}\n"
            f"🎾 <b>Safari Balls used:</b> {SAFARI_BALLS - session['balls_left']}\n"
            f"🔚 <b>Reason:</b> {reason}\n\n"
        )
        
        # Show caught Pokemon
        summary_text += "🎯 <b>Caught Pokemon:</b>\n"
        for pokemon in caught_pokemon:
            rarity_emoji = get_rarity_emoji(pokemon['rarity'])
            summary_text += f"{rarity_emoji} {pokemon['name']} ({pokemon['rarity']})\n"
        
        summary_text += (
            f"\n💡 <i>Great job! Come back tomorrow for another Safari adventure!</i>\n"
            f"⏰ <i>Next Safari available in 24 hours.</i>"
        )
    else:
        summary_text = (
            f"🏁 <b>Safari Zone Session Complete!</b>\n\n"
            f"😔 <b>No Pokemon were caught this time.</b>\n"
            f"🎾 <b>Safari Balls used:</b> {SAFARI_BALLS - session['balls_left']}\n"
            f"🔚 <b>Reason:</b> {reason}\n\n"
            f"💪 <i>Don't give up! Try again tomorrow!</i>\n"
            f"⏰ <i>Next Safari available in 24 hours.</i>"
        )
    
    # Try to send summary to user
    try:
        await client.send_message(user_id, summary_text)
    except Exception as e:
        print(f"Error sending Safari summary: {e}")

# Register callback handlers
def register_safari_handlers(app: Client):
    """Register Safari Zone callback handlers"""
    @app.on_callback_query(filters.regex(r"^(safari_|hunt_)(catch|run|stats|exit|engage|throw)_\d+(_\d+)?$"))
    async def safari_callback_wrapper(client: Client, callback_query: CallbackQuery):
        await safari_callback_handler(client, callback_query)
    
    @app.on_callback_query(filters.regex(r"^safari_back_\d+$"))
    async def safari_back_callback_wrapper(client: Client, callback_query: CallbackQuery):
        await safari_back_callback_handler(client, callback_query)
