from datetime import datetime
from typing import List, Dict, Optional
import re
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from modules.postgres_database import get_database, get_postgres_pool
from modules.decorators import auto_register_user

# Team management system for Pokemon collector bot
MAX_TEAM_SIZE = 6

# Banned types/categories that cannot be added to a team
BANNED_TYPES = {
    "goat",
    "trio",
    "duo",
    "regional champion",
    "world champion",
    "team",
    "team leader",
    "rivals",
    "none",
    "unknown",
}

class TeamManager:
    """Manages Pokemon teams for users"""
    
    @staticmethod
    async def ensure_team_table():
        """Create teams table if it doesn't exist"""
        pool = get_postgres_pool()
        if not pool:
            return False
            
        try:
            async with pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS teams (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        team_name VARCHAR(50) DEFAULT 'My Team',
                        pokemon_ids INTEGER[] DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    );
                    
                    -- Create index for faster lookups
                    CREATE INDEX IF NOT EXISTS idx_teams_user_id ON teams(user_id);
                    CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(user_id, is_active);
                ''')
                return True
        except Exception as e:
            print(f"Error creating teams table: {e}")
            return False

    @staticmethod
    async def get_user_team(user_id: int) -> Optional[Dict]:
        """Get user's active team"""
        pool = get_postgres_pool()
        if not pool:
            return None
            
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT id, team_name, pokemon_ids, created_at, updated_at
                    FROM teams 
                    WHERE user_id = $1 AND is_active = TRUE
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''', user_id)
                
                if row:
                    return {
                        'id': row['id'],
                        'team_name': row['team_name'],
                        'pokemon_ids': row['pokemon_ids'] or [],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return None
        except Exception as e:
            print(f"Error getting user team: {e}")
            return None

    @staticmethod
    async def create_or_update_team(user_id: int, pokemon_ids: List[int], team_name: str = "My Team") -> bool:
        """Create new team or update existing one"""
        print(f"DEBUG: create_or_update_team called for user {user_id}")
        print(f"DEBUG: New pokemon_ids order: {pokemon_ids}")
        
        pool = get_postgres_pool()
        if not pool:
            return False
            
        try:
            async with pool.acquire() as conn:
                # Check if user has an active team
                existing = await conn.fetchrow('''
                    SELECT id FROM teams WHERE user_id = $1 AND is_active = TRUE
                ''', user_id)
                
                if existing:
                    # Update existing team
                    print(f"DEBUG: Updating existing team with IDs: {pokemon_ids}")
                    await conn.execute('''
                        UPDATE teams 
                        SET pokemon_ids = $1, team_name = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $3 AND is_active = TRUE
                    ''', pokemon_ids, team_name, user_id)
                else:
                    # Create new team
                    print(f"DEBUG: Creating new team with IDs: {pokemon_ids}")
                    await conn.execute('''
                        INSERT INTO teams (user_id, team_name, pokemon_ids)
                        VALUES ($1, $2, $3)
                    ''', user_id, team_name, pokemon_ids)
                
                # Verify the update
                updated_team = await conn.fetchrow('''
                    SELECT pokemon_ids FROM teams WHERE user_id = $1 AND is_active = TRUE
                ''', user_id)
                if updated_team:
                    print(f"DEBUG: Team updated successfully. New DB order: {updated_team['pokemon_ids']}")
                else:
                    print("DEBUG: Failed to verify team update")
                
                return True
        except Exception as e:
            print(f"Error creating/updating team: {e}")
            return False

    @staticmethod
    async def add_pokemon_to_team(user_id: int, pokemon_id: int) -> tuple[bool, str]:
        """Add a Pokemon to user's team"""
        # First ensure table exists
        await TeamManager.ensure_team_table()
        
        # Validate ownership defensively (don't rely only on command-level checks)
        if not await TeamManager.user_owns_pokemon(user_id, pokemon_id):
            pokemon_name = await TeamManager.get_pokemon_name(pokemon_id)
            return False, f"❌ You don't own {pokemon_name}!"

        # Fetch Pokemon info for validations (type and rarity)
        pokemon_info = await TeamManager.get_pokemon_info(pokemon_id)
        pokemon_name_for_msgs = pokemon_info.get('name') or await TeamManager.get_pokemon_name(pokemon_id)
        ptype_raw = (pokemon_info.get('type') or '').strip()
        # Normalize and split multi-types on common separators
        type_tokens = [t.strip().lower() for part in re.split(r"[|/,+]", ptype_raw) for t in [part] if t.strip()] if ptype_raw else []
        # If any token is banned, reject
        if any(t in BANNED_TYPES for t in type_tokens) or (not type_tokens and 'unknown' in BANNED_TYPES):
            return False, f"❌ {pokemon_name_for_msgs} cannot be added to teams."

        # Get current team
        team = await TeamManager.get_user_team(user_id)
        
        if not team:
            # Create new team with this Pokemon
            success = await TeamManager.create_or_update_team(user_id, [pokemon_id])
            if success:
                # Get Pokemon name for better message
                pokemon_name = pokemon_name_for_msgs
                return True, f"✅ Team created with {pokemon_name}!"
            else:
                return False, "Failed to create team"
        
        current_pokemon = team['pokemon_ids']
        
        # Check if Pokemon is already in team
        if pokemon_id in current_pokemon:
            pokemon_name = pokemon_name_for_msgs
            return False, f"❌ {pokemon_name} is already in your team!"
        
        # Check team size limit
        if len(current_pokemon) >= MAX_TEAM_SIZE:
            return False, f"❌ Team is full! Maximum {MAX_TEAM_SIZE} Pokemon allowed."

        # Enforce maximum 3 Pokemon per rarity in team
        try:
            candidate_rarity = (pokemon_info.get('rarity') or '').strip()
            pool = get_postgres_pool()
            if pool and candidate_rarity:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        '''SELECT rarity FROM characters WHERE character_id = ANY($1::int[])''',
                        current_pokemon
                    )
                    rarity_counts = {}
                    for r in rows:
                        rstr = (r['rarity'] or '').strip()
                        rarity_counts[rstr] = rarity_counts.get(rstr, 0) + 1
                    if rarity_counts.get(candidate_rarity, 0) >= 3:
                        return False, f"❌ You can have at most 3 Pokemon of {candidate_rarity} rarity in your team."
        except Exception:
            # If counting fails, do not block; proceed gracefully
            pass
        
        # Add Pokemon to team
        current_pokemon.append(pokemon_id)
        success = await TeamManager.create_or_update_team(user_id, current_pokemon, team['team_name'])
        if success:
            pokemon_name = pokemon_name_for_msgs
            return True, f"✅ {pokemon_name} added to your team!"
        else:
            return False, "Failed to add Pokemon to team"

    @staticmethod
    async def remove_pokemon_from_team(user_id: int, pokemon_id: int) -> tuple[bool, str]:
        """Remove a Pokemon from user's team"""
        team = await TeamManager.get_user_team(user_id)
        
        if not team:
            return False, "❌ You don't have an active team!"
        
        current_pokemon = team['pokemon_ids']
        
        if pokemon_id not in current_pokemon:
            pokemon_name = await TeamManager.get_pokemon_name(pokemon_id)
            return False, f"❌ {pokemon_name} is not in your team!"
        
        # Remove Pokemon from team
        current_pokemon.remove(pokemon_id)
        success = await TeamManager.create_or_update_team(user_id, current_pokemon, team['team_name'])
        if success:
            pokemon_name = await TeamManager.get_pokemon_name(pokemon_id)
            return True, f"✅ {pokemon_name} removed from your team!"
        else:
            return False, "Failed to remove Pokemon from team"

    @staticmethod
    async def get_team_details(user_id: int) -> Optional[Dict]:
        """Get detailed information about user's team including Pokemon details"""
        print(f"DEBUG: get_team_details called for user {user_id}")
        db = get_database()
        team = await TeamManager.get_user_team(user_id)
        
        if team:
            print(f"DEBUG: Retrieved team pokemon_ids from DB: {team['pokemon_ids']}")
        
        if not team or not team['pokemon_ids']:
            return None
        
        try:
            # Filter out any pokemon that the user no longer owns
            try:
                user_collection = await db.get_user_collection(user_id)
                owned_ids = {p.get('character_id') for p in user_collection}
            except Exception:
                owned_ids = set()

            original_ids = list(team['pokemon_ids'])
            print(f"DEBUG: Original IDs from team: {original_ids}")
            valid_ids = [pid for pid in original_ids if pid in owned_ids]
            print(f"DEBUG: Valid IDs after ownership check: {valid_ids}")

            # If stored team has unowned pokemon, auto-correct it in DB
            if valid_ids != original_ids:
                print(f"DEBUG: Auto-correcting team due to unowned Pokemon")
                await TeamManager.create_or_update_team(user_id, valid_ids, team['team_name'])

            if not valid_ids:
                return {
                    'team_name': team['team_name'],
                    'pokemon_count': 0,
                    'pokemon_details': [],
                    'created_at': team['created_at'],
                    'updated_at': datetime.utcnow()
                }

            # Get Pokemon details from characters table for valid ids only
            pool = get_postgres_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT character_id, name, rarity, anime, img_url, file_id, is_video, type
                    FROM characters 
                    WHERE character_id = ANY($1::int[])
                ''', valid_ids)
                
                # Create a lookup dictionary for Pokemon details
                pokemon_lookup = {}
                for row in rows:
                    pokemon_lookup[row['character_id']] = {
                        'character_id': row['character_id'],
                        'name': row['name'],
                        'rarity': row['rarity'],
                        'anime': row['anime'],
                        'img_url': row['img_url'],
                        'file_id': row['file_id'],
                        'is_video': row['is_video'],
                        'type': row['type']
                    }
                
                # Build pokemon_details in the correct order based on valid_ids
                pokemon_details = []
                for pokemon_id in valid_ids:
                    if pokemon_id in pokemon_lookup:
                        pokemon_details.append(pokemon_lookup[pokemon_id])
                
                print(f"DEBUG: Final pokemon_details order: {[p['character_id'] for p in pokemon_details]}")
                
                return {
                    'team_name': team['team_name'],
                    'pokemon_count': len(pokemon_details),
                    'pokemon_details': pokemon_details,
                    'created_at': team['created_at'],
                    'updated_at': team['updated_at']
                }
        except Exception as e:
            print(f"Error getting team details: {e}")
            return None

    @staticmethod
    async def user_owns_pokemon(user_id: int, pokemon_id: int) -> bool:
        """Check if user owns a specific Pokemon"""
        db = get_database()
        try:
            user_collection = await db.get_user_collection(user_id)
            for pokemon in user_collection:
                if pokemon.get('character_id') == pokemon_id:
                    return True
            return False
        except Exception as e:
            print(f"Error checking Pokemon ownership: {e}")
            return False

    @staticmethod
    async def get_pokemon_name(pokemon_id: int) -> str:
        """Get Pokemon name by ID"""
        try:
            pool = get_postgres_pool()
            if not pool:
                return "Unknown Pokemon"
                
            async with pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT name FROM characters WHERE character_id = $1
                ''', pokemon_id)
                
                if row:
                    return row['name']
                else:
                    return "Unknown Pokemon"
        except Exception as e:
            print(f"Error getting Pokemon name: {e}")
            return "Unknown Pokemon"

    @staticmethod
    async def get_pokemon_info(pokemon_id: int) -> Dict:
        """Get Pokemon info (name, rarity, type) by ID"""
        try:
            pool = get_postgres_pool()
            if not pool:
                return {"name": "Unknown Pokemon", "rarity": "", "type": ""}
            async with pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT name, rarity, type FROM characters WHERE character_id = $1
                ''', pokemon_id)
                if row:
                    return {"name": row['name'], "rarity": row['rarity'], "type": row['type']}
                return {"name": "Unknown Pokemon", "rarity": "", "type": ""}
        except Exception as e:
            print(f"Error getting Pokemon info: {e}")
            return {"name": "Unknown Pokemon", "rarity": "", "type": ""}
    
    @staticmethod
    async def swap_pokemon_positions(user_id: int, position1: int, position2: int) -> tuple[bool, str]:
        """Swap two Pokemon positions in the team"""
        team = await TeamManager.get_user_team(user_id)
        
        if not team:
            return False, "❌ You don't have an active team!"
        
        current_pokemon = team['pokemon_ids']
        team_size = len(current_pokemon)
        
        # Validate positions (1-based to 0-based conversion)
        pos1_idx = position1 - 1
        pos2_idx = position2 - 1
        
        if pos1_idx < 0 or pos1_idx >= team_size:
            return False, f"❌ Position {position1} is invalid! Your team has {team_size} Pokemon."
        
        if pos2_idx < 0 or pos2_idx >= team_size:
            return False, f"❌ Position {position2} is invalid! Your team has {team_size} Pokemon."
        
        if pos1_idx == pos2_idx:
            return False, "❌ You can't swap a Pokemon with itself!"
        
        # Get Pokemon names for confirmation message
        pokemon1_name = await TeamManager.get_pokemon_name(current_pokemon[pos1_idx])
        pokemon2_name = await TeamManager.get_pokemon_name(current_pokemon[pos2_idx])
        
        # Perform the swap
        print(f"DEBUG: Before swap - Pokemon IDs: {current_pokemon}")
        print(f"DEBUG: Swapping positions {position1} ({pos1_idx}) and {position2} ({pos2_idx})")
        print(f"DEBUG: Pokemon at pos {position1}: {current_pokemon[pos1_idx]}")
        print(f"DEBUG: Pokemon at pos {position2}: {current_pokemon[pos2_idx]}")
        
        current_pokemon[pos1_idx], current_pokemon[pos2_idx] = current_pokemon[pos2_idx], current_pokemon[pos1_idx]
        
        print(f"DEBUG: After swap - Pokemon IDs: {current_pokemon}")
        
        # Update the team
        success = await TeamManager.create_or_update_team(user_id, current_pokemon, team['team_name'])
        
        if success:
            return True, f"✅ Successfully swapped positions!\n🔄 {pokemon1_name} (Position {position1}) ↔ {pokemon2_name} (Position {position2})"
        else:
            return False, "❌ Failed to update team positions. Please try again."
    
    @staticmethod
    async def move_pokemon_to_position(user_id: int, from_position: int, to_position: int) -> tuple[bool, str]:
        """Move a Pokemon from one position to another, shifting others"""
        team = await TeamManager.get_user_team(user_id)
        
        if not team:
            return False, "❌ You don't have an active team!"
        
        current_pokemon = team['pokemon_ids']
        team_size = len(current_pokemon)
        
        # Validate positions (1-based to 0-based conversion)
        from_idx = from_position - 1
        to_idx = to_position - 1
        
        if from_idx < 0 or from_idx >= team_size:
            return False, f"❌ Position {from_position} is invalid! Your team has {team_size} Pokemon."
        
        if to_idx < 0 or to_idx >= team_size:
            return False, f"❌ Position {to_position} is invalid! Your team has {team_size} Pokemon."
        
        if from_idx == to_idx:
            return False, "❌ Pokemon is already in that position!"
        
        # Get Pokemon name for confirmation
        pokemon_name = await TeamManager.get_pokemon_name(current_pokemon[from_idx])
        
        # Remove Pokemon from original position and insert at new position
        print(f"DEBUG: Before move - Pokemon IDs: {current_pokemon}")
        print(f"DEBUG: Moving from position {from_position} ({from_idx}) to position {to_position} ({to_idx})")
        print(f"DEBUG: Pokemon to move: {current_pokemon[from_idx]}")
        
        pokemon_to_move = current_pokemon.pop(from_idx)
        current_pokemon.insert(to_idx, pokemon_to_move)
        
        print(f"DEBUG: After move - Pokemon IDs: {current_pokemon}")
        
        # Update the team
        success = await TeamManager.create_or_update_team(user_id, current_pokemon, team['team_name'])
        
        if success:
            return True, f"✅ Successfully moved {pokemon_name} from position {from_position} to position {to_position}!"
        else:
            return False, "❌ Failed to update team positions. Please try again."


# Command handlers
@auto_register_user
async def team_command(client: Client, message: Message):
    """Handle /team command - show current team or team management options"""
    user_id = message.from_user.id
    
    # Ensure team table exists
    await TeamManager.ensure_team_table()
    
    team_details = await TeamManager.get_team_details(user_id)
    
    if not team_details:
        # No team exists, show minimal hint
        await message.reply_text(
            "❌ <b>You don't have any team yet.</b>\n\n"
            "Form a team now using <code>/addteam &lt;id&gt;</code> (example: <code>/addteam 123</code>)."
        )
        return
    
    # Show current team (minimal view)
    team_text = f"<b>🏆 {team_details['team_name']}</b>\n\n"
    team_text += f"<b>Team Size:</b> {team_details['pokemon_count']}/{MAX_TEAM_SIZE}\n\n"
    
    if team_details['pokemon_details']:
        team_text += "<b>Your Team:</b>\n"
        for i, pokemon in enumerate(team_details['pokemon_details'], 1):
            rarity_emoji = get_rarity_emoji(pokemon['rarity'])
            pokemon_type = format_pokemon_type(pokemon.get('type', 'Unknown'))
            team_text += f"{i}. {rarity_emoji} <b>{pokemon['name']}</b> (ID: {pokemon['character_id']})\n"
            team_text += f"   └ {pokemon['anime']} • {pokemon_type}\n"
    else:
        team_text += "📝 <i>No Pokemon in your team yet</i>\n"
    
    team_text += f"\n⏰ <i>Last updated: {team_details['updated_at'].strftime('%Y-%m-%d %H:%M')}</i>"
    
    # Add edit button for teams with Pokemon
    if team_details['pokemon_details']:
        keyboard = [[InlineKeyboardButton("📝 Edit Team", callback_data=f"edit_team_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(team_text, reply_markup=reply_markup)
    else:
        await message.reply_text(team_text)

@auto_register_user
async def addteam_command(client: Client, message: Message):
    """Handle /addteam command - add Pokemon to team by ID"""
    user_id = message.from_user.id
    
    # Parse Pokemon ID from command
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<b>Usage:</b> <code>/addteam [pokemon_id]</code>\n\n"
            "<b>Example:</b> <code>/addteam 123</code>\n\n"
            "Use <code>/mycollection</code> to see your Pokemon IDs."
        )
        return
    
    try:
        pokemon_id = int(parts[1])
    except ValueError:
        await message.reply_text("❌ Please provide a valid Pokemon ID (number).")
        return
    
    # Check if user owns this Pokemon
    if not await TeamManager.user_owns_pokemon(user_id, pokemon_id):
        pokemon_name = await TeamManager.get_pokemon_name(pokemon_id)
        await message.reply_text(f"❌ You don't own {pokemon_name}! Use <code>/mycollection</code> to see your Pokemon.")
        return
    
    # Add Pokemon to team
    success, msg = await TeamManager.add_pokemon_to_team(user_id, pokemon_id)
    
    if success:
        await message.reply_text(msg)
    else:
        await message.reply_text(msg)

@auto_register_user
async def removeteam_command(client: Client, message: Message):
    """Handle /removeteam command - remove Pokemon from team by ID"""
    user_id = message.from_user.id
    
    # Parse Pokemon ID from command
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<b>Usage:</b> <code>/removeteam [pokemon_id]</code>\n\n"
            "<b>Example:</b> <code>/removeteam 123</code>\n\n"
            "Use <code>/team</code> to see your current team."
        )
        return
    
    try:
        pokemon_id = int(parts[1])
    except ValueError:
        await message.reply_text("❌ Please provide a valid Pokemon ID (number).")
        return
    
    # Remove Pokemon from team
    success, msg = await TeamManager.remove_pokemon_from_team(user_id, pokemon_id)
    
    if success:
        await message.reply_text(msg)
    else:
        await message.reply_text(msg)

@auto_register_user
async def editteam_command(client: Client, message: Message):
    """Handle /editteam command - edit team positions interactively"""
    user_id = message.from_user.id
    
    # Ensure team table exists
    await TeamManager.ensure_team_table()
    
    # Get current team
    team_details = await TeamManager.get_team_details(user_id)
    
    if not team_details or not team_details['pokemon_details']:
        await message.reply_text(
            "❌ <b>You don't have any team yet.</b>\n\n"
            "Create a team first using <code>/addteam &lt;id&gt;</code>."
        )
        return
    
    # Show interactive team edit interface
    await show_team_edit_ui(client, message, user_id)

@auto_register_user
async def swapteam_command(client: Client, message: Message):
    """Handle /swapteam command - swap two Pokemon positions"""
    user_id = message.from_user.id
    
    # Parse positions from command
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text(
            "<b>Usage:</b> <code>/swapteam [position1] [position2]</code>\n\n"
            "<b>Example:</b> <code>/swapteam 1 3</code>\n\n"
            "This will swap the Pokemon in position 1 with the Pokemon in position 3.\n\n"
            "Use <code>/team</code> to see your current team positions."
        )
        return
    
    try:
        position1 = int(parts[1])
        position2 = int(parts[2])
    except ValueError:
        await message.reply_text("❌ Please provide valid position numbers.")
        return
    
    # Swap Pokemon positions
    success, msg = await TeamManager.swap_pokemon_positions(user_id, position1, position2)
    await message.reply_text(msg)

@auto_register_user
async def moveteam_command(client: Client, message: Message):
    """Handle /moveteam command - move Pokemon to a different position"""
    user_id = message.from_user.id
    
    # Parse positions from command
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text(
            "<b>Usage:</b> <code>/moveteam [from_position] [to_position]</code>\n\n"
            "<b>Example:</b> <code>/moveteam 2 1</code>\n\n"
            "This will move the Pokemon from position 2 to position 1 (shifting others).\n\n"
            "Use <code>/team</code> to see your current team positions."
        )
        return
    
    try:
        from_position = int(parts[1])
        to_position = int(parts[2])
    except ValueError:
        await message.reply_text("❌ Please provide valid position numbers.")
        return
    
    # Move Pokemon position
    success, msg = await TeamManager.move_pokemon_to_position(user_id, from_position, to_position)
    await message.reply_text(msg)

# Access control helper
async def check_team_edit_access(callback_query: CallbackQuery) -> bool:
    """Check if user has access to edit team (simple version)"""
    callback_user_id = callback_query.from_user.id
    team = await TeamManager.get_user_team(callback_user_id)
    
    if not team or not team.get('pokemon_ids'):
        await callback_query.answer("❌ Access denied! You don't have a team to edit.", show_alert=True)
        return False
    
    return True

async def check_team_edit_access_with_id(callback_query: CallbackQuery, callback_data: str) -> bool:
    """Check if user has access to edit team with user ID verification"""
    callback_user_id = callback_query.from_user.id
    
    # Extract owner user ID from callback data
    try:
        owner_user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await callback_query.answer("❌ Access denied! Invalid team data.", show_alert=True)
        return False
    
    # Check if callback user matches team owner
    if callback_user_id != owner_user_id:
        await callback_query.answer("❌ Access denied! You can only edit your own team.", show_alert=True)
        return False
    
    return True

# Interactive team edit UI
async def show_team_edit_ui(client: Client, message: Message, user_id: int):
    """Show interactive team editing interface"""
    team_details = await TeamManager.get_team_details(user_id)
    
    if not team_details or not team_details['pokemon_details']:
        await message.reply_text("❌ Your team is empty!")
        return
    
    # Create team display text with numbered positions
    team_text = f"<b>📝 Edit {team_details['team_name']}</b>\n\n"
    team_text += f"<b>Team Size:</b> {team_details['pokemon_count']}/{MAX_TEAM_SIZE}\n\n"
    team_text += "<b>Current Team Order:</b>\n"
    
    for i, pokemon in enumerate(team_details['pokemon_details'], 1):
        rarity_emoji = get_rarity_emoji(pokemon['rarity'])
        pokemon_type = format_pokemon_type(pokemon.get('type', 'Unknown'))
        team_text += f"<b>{i}.</b> {rarity_emoji} <b>{pokemon['name']}</b> (ID: {pokemon['character_id']})\n"
        team_text += f"    └ {pokemon['anime']} • {pokemon_type}\n"
    
    team_text += "\n📝 <b>Edit Options:</b>\n"
    team_text += "• <b>Swap:</b> Exchange positions of two Pokemon\n"
    team_text += "• <b>Move:</b> Move a Pokemon to a different position\n"
    team_text += "• <b>Commands:</b> Use /swapteam or /moveteam for quick edits"
    
    # Create inline keyboard for editing options
    keyboard = []
    
    # Add swap buttons (2x3 grid for positions)
    keyboard.append([InlineKeyboardButton("🔄 Quick Swap Positions", callback_data="team_edit_swap_menu")])
    keyboard.append([InlineKeyboardButton("➡️ Move Pokemon Position", callback_data="team_edit_move_menu")])
    keyboard.append([InlineKeyboardButton("🔄 Reverse Team Order", callback_data="team_edit_reverse")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Team", callback_data="back_to_team")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(team_text, reply_markup=reply_markup)

# Callback handlers
async def team_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle team-related callback queries"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "create_team":
        await callback_query.message.edit_text(
            "<b>🏆 Create Your Team</b>\n\n"
            "To add Pokemon to your team, use the command:\n"
            "<code>/addteam [pokemon_id]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/addteam 123</code>\n\n"
            "You can add up to 6 Pokemon to your team.\n"
            f"Use <code>/mycollection</code> to see your Pokemon and their IDs.\n\n<b>Limits:</b> Up to {MAX_TEAM_SIZE} total, max 2 per rarity.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_team")]
            ])
        )
    
    elif data == "add_to_team":
        await callback_query.message.edit_text(
            "<b>➕ Add Pokemon to Team</b>\n\n"
            "Use the command: <code>/addteam [pokemon_id]</code>\n\n"
            "<b>Example:</b> <code>/addteam 456</code>\n\n"
            "💡 <b>Tips:</b>\n"
            "• Use <code>/mycollection</code> to see your Pokemon IDs\n"
            "• You can only add Pokemon you own\n"
            f"• Maximum team size: {MAX_TEAM_SIZE} Pokemon\n"
            "• Max 3 Pokemon per rarity\n"
            "• Certain special categories are banned (e.g., GOAT, Trio, Duo, etc.)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_team")]
            ])
        )
    
    elif data == "remove_from_team":
        team_details = await TeamManager.get_team_details(user_id)
        if not team_details or not team_details['pokemon_details']:
            await callback_query.answer("Your team is empty!", show_alert=True)
            return
        
        text = "<b>➖ Remove Pokemon from Team</b>\n\n"
        text += "Use the command: <code>/removeteam [pokemon_id]</code>\n\n"
        text += "<b>Your current team:</b>\n"
        
        for pokemon in team_details['pokemon_details']:
            rarity_emoji = get_rarity_emoji(pokemon['rarity'])
            text += f"• ID {pokemon['character_id']}: {rarity_emoji} {pokemon['name']}\n"
        
        text += f"\n<b>Example:</b> <code>/removeteam {team_details['pokemon_details'][0]['character_id']}</code>"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_team")]
            ])
        )
    
    elif data == "clear_team":
        await callback_query.message.edit_text(
            "<b>🔄 Clear Team</b>\n\n"
            "Are you sure you want to remove all Pokemon from your team?\n"
            "This action cannot be undone!",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Clear", callback_data="confirm_clear_team"),
                    InlineKeyboardButton("❌ Cancel", callback_data="back_to_team")
                ]
            ])
        )
    
    elif data == "confirm_clear_team":
        success = await TeamManager.create_or_update_team(user_id, [])
        if success:
            await callback_query.message.edit_text(
                "✅ <b>Team Cleared Successfully!</b>\n\n"
                "All Pokemon have been removed from your team.\n"
                "Use <code>/addteam [id]</code> to add new Pokemon to your team.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Team", callback_data="back_to_team")]
                ])
            )
        else:
            await callback_query.answer("❌ Failed to clear team! Please try again.", show_alert=True)
    
    elif data == "team_help":
        await callback_query.message.edit_text(
            "<b>📖 Team System Help</b>\n\n"
            "<b>Commands:</b>\n"
            "• <code>/team</code> - View your current team\n"
            "• <code>/addteam [id]</code> - Add Pokemon to team\n"
            "• <code>/removeteam [id]</code> - Remove Pokemon from team\n\n"
            "<b>Features:</b>\n"
            f"• Maximum {MAX_TEAM_SIZE} Pokemon per team\n"
            "• Only Pokemon you own can be added\n"
            "• Max 3 Pokemon per rarity\n"
            "• Certain special categories are banned (GOAT, Trio, Duo, Regional Champion, World Champion, Team, Team Leader, Rivals, None, Unknown)\n"
            "• Teams are saved automatically\n"
            "• Use teams for battles and organization\n\n"
            "<b>Getting Pokemon IDs:</b>\n"
            "Use <code>/mycollection</code> to see all your Pokemon with their IDs.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_team")]
            ])
        )
    
    elif data.startswith("edit_team_"):
        # Show team editing interface with access control
        callback_user_id = callback_query.from_user.id
        
        # Extract the team owner ID from callback data
        team_owner_id = int(data.split("_")[-1])
        
        # Check if the callback user is the team owner
        if callback_user_id != team_owner_id:
            await callback_query.answer("❌ Access denied! You can only edit your own team.", show_alert=True)
            return
        
        # Verify the user has a team
        team_details = await TeamManager.get_team_details(callback_user_id)
        
        if not team_details or not team_details['pokemon_details']:
            await callback_query.answer("❌ Your team is empty!", show_alert=True)
            return
        
        await show_team_edit_ui_callback(client, callback_query)
    
    elif data.startswith("team_edit_swap_menu_"):
        # Check access - user must be editing their own team
        if not await check_team_edit_access_with_id(callback_query, data):
            return
        await show_swap_menu(client, callback_query)
    
    elif data.startswith("team_edit_move_menu_"):
        # Check access - user must be editing their own team
        if not await check_team_edit_access_with_id(callback_query, data):
            return
        await show_move_menu(client, callback_query)
    
    elif data.startswith("team_edit_reverse_"):
        # Check access - user must be editing their own team
        if not await check_team_edit_access_with_id(callback_query, data):
            return
        user_id = callback_query.from_user.id
        team = await TeamManager.get_user_team(user_id)
        
        if team and team['pokemon_ids']:
            reversed_pokemon = list(reversed(team['pokemon_ids']))
            success = await TeamManager.create_or_update_team(user_id, reversed_pokemon, team['team_name'])
            
            if success:
                await callback_query.answer("✅ Team order reversed!", show_alert=True)
                await show_team_edit_ui_callback(client, callback_query)
            else:
                await callback_query.answer("❌ Failed to reverse team order!", show_alert=True)
        else:
            await callback_query.answer("❌ Your team is empty!", show_alert=True)
    
    elif data.startswith("swap_pos_"):
        if not await check_team_edit_access(callback_query):
            return
        await handle_swap_selection(client, callback_query)
    
    elif data.startswith("move_from_"):
        if not await check_team_edit_access(callback_query):
            return
        await handle_move_selection(client, callback_query)
    
    elif data.startswith("swap_exec_"):
        if not await check_team_edit_access(callback_query):
            return
        # Execute the swap: format is swap_exec_pos1_pos2
        parts = data.split("_")
        position1 = int(parts[2])
        position2 = int(parts[3])
        
        user_id = callback_query.from_user.id
        success, msg = await TeamManager.swap_pokemon_positions(user_id, position1, position2)
        
        if success:
            await callback_query.answer("✅ Pokemon positions swapped!", show_alert=True)
            await show_team_edit_ui_callback(client, callback_query)
        else:
            await callback_query.answer(f"❌ {msg}", show_alert=True)
    
    elif data.startswith("move_exec_"):
        if not await check_team_edit_access(callback_query):
            return
        # Execute the move: format is move_exec_from_to
        parts = data.split("_")
        from_position = int(parts[2])
        to_position = int(parts[3])
        
        user_id = callback_query.from_user.id
        success, msg = await TeamManager.move_pokemon_to_position(user_id, from_position, to_position)
        
        if success:
            await callback_query.answer("✅ Pokemon moved!", show_alert=True)
            await show_team_edit_ui_callback(client, callback_query)
        else:
            await callback_query.answer(f"❌ {msg}", show_alert=True)
    
    elif data == "back_to_team":
        # Refresh team display
        await team_command(client, callback_query.message)

def format_pokemon_type(pokemon_type: str) -> str:
    """Format Pokemon type for display"""
    if not pokemon_type or pokemon_type.lower() in ['unknown', 'none', '']:
        return "Unknown Type"
    
    # Handle multiple types separated by various delimiters
    import re
    types = [t.strip().title() for t in re.split(r'[|/,+]', pokemon_type) if t.strip()]
    
    if not types:
        return "Unknown Type"
    elif len(types) == 1:
        return types[0]
    else:
        return " / ".join(types[:2])  # Show max 2 types

def get_rarity_emoji(rarity: str) -> str:
    """Get emoji for rarity"""
    rarity_emojis = {
        "Common": "⚪️",
        "Medium": "🟢", 
        "Rare": "🟠",
        "Legendary": "🟡",
        "Exclusive": "🫧",
        "Elite": "💎",
        "Limited Edition": "🔮",
        "Ultimate": "🔱",
        "Premium": "🧿",
        "Supreme": "👑",
        "Mythic": "🔴",
        "Zenith": "💫",
        "Ethereal": "❄️",
        "Mega Evolution": "🧬"
    }
    return rarity_emojis.get(rarity, "❓")

async def show_team_edit_ui_callback(client: Client, callback_query: CallbackQuery):
    """Show team edit UI in callback context"""
    user_id = callback_query.from_user.id
    team_details = await TeamManager.get_team_details(user_id)
    
    if not team_details or not team_details['pokemon_details']:
        await callback_query.message.edit_text("❌ Your team is empty!")
        return
    
    # Create team display text
    team_text = f"<b>📝 Edit {team_details['team_name']}</b>\n\n"
    team_text += f"<b>Team Size:</b> {team_details['pokemon_count']}/{MAX_TEAM_SIZE}\n\n"
    team_text += "<b>Current Team Order:</b>\n"
    
    for i, pokemon in enumerate(team_details['pokemon_details'], 1):
        rarity_emoji = get_rarity_emoji(pokemon['rarity'])
        pokemon_type = format_pokemon_type(pokemon.get('type', 'Unknown'))
        team_text += f"<b>{i}.</b> {rarity_emoji} <b>{pokemon['name']}</b>\n"
        team_text += f"    └ {pokemon['anime']} • {pokemon_type}\n"
    
    team_text += "\n📝 <b>Choose an edit option:</b>"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Swap Pokemon Positions", callback_data=f"team_edit_swap_menu_{user_id}")],
        [InlineKeyboardButton("➡️ Move Pokemon Position", callback_data=f"team_edit_move_menu_{user_id}")],
        [InlineKeyboardButton("🔄 Reverse Team Order", callback_data=f"team_edit_reverse_{user_id}")],
        [InlineKeyboardButton("🔙 Back to Team", callback_data="back_to_team")]
    ]
    
    await callback_query.message.edit_text(team_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_swap_menu(client: Client, callback_query: CallbackQuery):
    """Show Pokemon selection menu for swapping"""
    user_id = callback_query.from_user.id
    team_details = await TeamManager.get_team_details(user_id)
    
    if not team_details or len(team_details['pokemon_details']) < 2:
        await callback_query.answer("❌ You need at least 2 Pokemon to swap!", show_alert=True)
        return
    
    text = "<b>🔄 Swap Pokemon Positions</b>\n\n"
    text += "Select the <b>first Pokemon</b> to swap:\n\n"
    
    for i, pokemon in enumerate(team_details['pokemon_details'], 1):
        rarity_emoji = get_rarity_emoji(pokemon['rarity'])
        text += f"<b>{i}.</b> {rarity_emoji} {pokemon['name']}\n"
    
    # Create position selection buttons
    keyboard = []
    row = []
    for i in range(len(team_details['pokemon_details'])):
        row.append(InlineKeyboardButton(f"Position {i+1}", callback_data=f"swap_pos_{i+1}"))
        if len(row) == 3:  # 3 buttons per row
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"edit_team_{user_id}")])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_move_menu(client: Client, callback_query: CallbackQuery):
    """Show Pokemon selection menu for moving"""
    user_id = callback_query.from_user.id
    team_details = await TeamManager.get_team_details(user_id)
    
    if not team_details or len(team_details['pokemon_details']) < 2:
        await callback_query.answer("❌ You need at least 2 Pokemon to move!", show_alert=True)
        return
    
    text = "<b>➡️ Move Pokemon Position</b>\n\n"
    text += "Select the Pokemon to move:\n\n"
    
    for i, pokemon in enumerate(team_details['pokemon_details'], 1):
        rarity_emoji = get_rarity_emoji(pokemon['rarity'])
        text += f"<b>{i}.</b> {rarity_emoji} {pokemon['name']}\n"
    
    # Create position selection buttons
    keyboard = []
    row = []
    for i in range(len(team_details['pokemon_details'])):
        row.append(InlineKeyboardButton(f"Position {i+1}", callback_data=f"move_from_{i+1}"))
        if len(row) == 3:  # 3 buttons per row
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"edit_team_{user_id}")])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_swap_selection(client: Client, callback_query: CallbackQuery):
    """Handle swap position selection"""
    # Extract position from callback data
    position1 = int(callback_query.data.split("_")[-1])
    
    # Store first position in callback data and show second position selection
    user_id = callback_query.from_user.id
    team_details = await TeamManager.get_team_details(user_id)
    
    text = f"<b>🔄 Swap Position {position1}</b>\n\n"
    text += f"Selected: Position {position1}\n"
    text += "\nNow select the <b>second position</b> to swap with:\n\n"
    
    for i, pokemon in enumerate(team_details['pokemon_details'], 1):
        rarity_emoji = get_rarity_emoji(pokemon['rarity'])
        status = " ← Selected" if i == position1 else ""
        text += f"<b>{i}.</b> {rarity_emoji} {pokemon['name']}{status}\n"
    
    # Create buttons for second position (excluding the first selected position)
    keyboard = []
    row = []
    for i in range(len(team_details['pokemon_details'])):
        if i + 1 != position1:  # Exclude the already selected position
            row.append(InlineKeyboardButton(f"Position {i+1}", callback_data=f"swap_exec_{position1}_{i+1}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="team_edit_swap_menu")])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_move_selection(client: Client, callback_query: CallbackQuery):
    """Handle move position selection"""
    # Extract position from callback data
    from_position = int(callback_query.data.split("_")[-1])
    
    user_id = callback_query.from_user.id
    team_details = await TeamManager.get_team_details(user_id)
    
    text = f"<b>➡️ Move from Position {from_position}</b>\n\n"
    text += f"Selected: Position {from_position}\n"
    text += "\nSelect the <b>new position</b>:\n\n"
    
    for i, pokemon in enumerate(team_details['pokemon_details'], 1):
        rarity_emoji = get_rarity_emoji(pokemon['rarity'])
        status = " ← Moving" if i == from_position else ""
        text += f"<b>{i}.</b> {rarity_emoji} {pokemon['name']}{status}\n"
    
    # Create buttons for target position (excluding the current position)
    keyboard = []
    row = []
    for i in range(len(team_details['pokemon_details'])):
        if i + 1 != from_position:
            row.append(InlineKeyboardButton(f"Position {i+1}", callback_data=f"move_exec_{from_position}_{i+1}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="team_edit_move_menu")])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

def setup_team_handlers(app: Client):
    """Register team callback handlers"""
    print("Registering team callback handlers...")
    
    # Extended callback handlers for team editing
    app.on_callback_query(filters.regex(r"^(create_team|add_to_team|remove_from_team|clear_team|confirm_clear_team|team_help|back_to_team)$"))(team_callback_handler)
    app.on_callback_query(filters.regex(r"^edit_team_\d+$"))(team_callback_handler)
    app.on_callback_query(filters.regex(r"^team_edit_(swap_menu|move_menu|reverse)_\d+$"))(team_callback_handler)
    app.on_callback_query(filters.regex(r"^(swap_pos_|move_from_|swap_exec_|move_exec_)\d+"))(team_callback_handler)
    
    print("Team callback handlers registered successfully!")
