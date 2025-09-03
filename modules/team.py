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
                    await conn.execute('''
                        UPDATE teams 
                        SET pokemon_ids = $1, team_name = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $3 AND is_active = TRUE
                    ''', pokemon_ids, team_name, user_id)
                else:
                    # Create new team
                    await conn.execute('''
                        INSERT INTO teams (user_id, team_name, pokemon_ids)
                        VALUES ($1, $2, $3)
                    ''', user_id, team_name, pokemon_ids)
                
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
        db = get_database()
        team = await TeamManager.get_user_team(user_id)
        
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
            valid_ids = [pid for pid in original_ids if pid in owned_ids]

            # If stored team has unowned pokemon, auto-correct it in DB
            if valid_ids != original_ids:
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
                    SELECT character_id, name, rarity, anime, img_url, file_id, is_video
                    FROM characters 
                    WHERE character_id = ANY($1::int[])
                    ORDER BY character_id
                ''', valid_ids)
                
                pokemon_details = []
                for row in rows:
                    pokemon_details.append({
                        'character_id': row['character_id'],
                        'name': row['name'],
                        'rarity': row['rarity'],
                        'anime': row['anime'],
                        'img_url': row['img_url'],
                        'file_id': row['file_id'],
                        'is_video': row['is_video']
                    })
                
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
            team_text += f"{i}. {rarity_emoji} <b>{pokemon['name']}</b>\n"
            team_text += f"   └ {pokemon['anime']} • {pokemon['rarity']}\n"
    else:
        team_text += "📝 <i>No Pokemon in your team yet</i>\n"
    
    team_text += f"\n⏰ <i>Last updated: {team_details['updated_at'].strftime('%Y-%m-%d %H:%M')}</i>"
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
    
    elif data == "back_to_team":
        # Refresh team display
        await team_command(client, callback_query.message)

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

def setup_team_handlers(app: Client):
    """Register team callback handlers"""
    print("Registering team callback handlers...")
    
    # Only callback handlers - command handlers are in main.py
    app.on_callback_query(filters.regex(r"^(create_team|add_to_team|remove_from_team|clear_team|confirm_clear_team|team_help|back_to_team)$"))(team_callback_handler)
    
    print("Team callback handlers registered successfully!")
