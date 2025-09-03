import base64
from datetime import datetime
import gc
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional

import aiohttp
import asyncpg
from cachetools import TTLCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PostgreSQL connection pool
_pg_pool = None
_postgres_uri = None

# Caches
_character_cache = TTLCache(maxsize=500, ttl=1800)  # 30 minutes
_drop_settings_cache = TTLCache(maxsize=5, ttl=900)  # 15 minutes
_user_stats_cache = TTLCache(maxsize=100, ttl=600)  # 10 minutes
_leaderboard_cache = TTLCache(maxsize=3, ttl=180)  # 3 minutes
_chat_settings_cache = TTLCache(maxsize=25, ttl=900)  # 15 minutes

# Performance tracking
_performance_stats = {
    'total_queries': 0,
    'cache_hits': 0,
    'cache_misses': 0,
    'last_cleanup': time.time(),
    'memory_usage': [],
    'connection_errors': 0,
    'slow_queries': 0
}

# Define rarity system (same as MongoDB module)
RARITIES = {
    "Common": 1,
    "Medium": 2,
    "Rare": 3,
    "Legendary": 4,
    "Exclusive": 5,
    "Elite": 6,
    "Limited Edition": 7,
    "Ultimate": 8,
    "Supreme": 9,
    "Zenith": 10,
    "Ethereal": 11,
    "Mythic": 12,
    "Mega Evolution": 13,
    "Premium": 14
}

# Define emoji mappings for rarities (same as MongoDB module)
RARITY_EMOJIS = {
    "Common": "⚪️",
    "Medium": "🟢",
    "Rare": "🟠",
    "Legendary": "🟡",
    "Exclusive": "🫧",
    "Elite": "💎",
    "Limited Edition": "🔮",
    "Ultimate": "🔱",
    "Supreme": "👑",
    "Zenith": "💫",
    "Ethereal": "❄️",
    "Mythic": "🔴",
    "Mega Evolution": "🧬",
    "Premium": "🧿"
}

def get_rarity_display(rarity: str) -> str:
    """Get the display format for a rarity (emoji + name)"""
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    return f"{emoji} {rarity}"

def get_rarity_emoji(rarity: str) -> str:
    """Get just the emoji for a rarity"""
    return RARITY_EMOJIS.get(rarity, "❓")

# Update the migration mapping (same as MongoDB module)
OLD_TO_NEW_RARITIES = {
    "⚪️ Common": "Common",
    "🟢 Medium": "Medium",
    "🟠 Rare": "Rare",
    "🟡 Legendary": "Legendary",
    "🫧 Exclusive": "Exclusive",
    "💎 Elite": "Elite",
    "🔮 Limited Edition": "Limited Edition",
    "🔱 Ultimate": "Ultimate",
    "👑 Supreme": "Supreme",
    "💫 Zenith": "Zenith",
    "❄️ Ethereal": "Ethereal",
    "🔴 Mythic": "Mythic",
    "🧿 Premium": "Premium",
    "🧬 Mega Evolution": "Mega Evolution"
}

def get_performance_stats():
    """Get performance statistics"""
    return _performance_stats.copy()

def clear_all_caches():
    """Clear all caches"""
    _character_cache.clear()
    _drop_settings_cache.clear()
    _user_stats_cache.clear()
    _leaderboard_cache.clear()
    _chat_settings_cache.clear()

def get_postgres_pool():
    """Get the PostgreSQL connection pool"""
    global _pg_pool
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized. Call init_database() first.")
    return _pg_pool

async def init_database(postgres_uri: str):
    """Initialize PostgreSQL connection pool"""
    global _pg_pool, _postgres_uri, _db_instance
    
    if _pg_pool is None:
        try:
            _postgres_uri = postgres_uri
            _pg_pool = await asyncpg.create_pool(
                postgres_uri,
                min_size=5,
                max_size=20,
                command_timeout=30,
                server_settings={
                    'jit': 'off',  # Disable JIT for better performance
                    'statement_timeout': '30000',  # 30 seconds
                    'idle_in_transaction_session_timeout': '60000'  # 1 minute
                }
            )
            
            # Test connection
            async with _pg_pool.acquire() as conn:
                await conn.execute('SELECT 1')
            
            # Create database instance
            _db_instance = PostgresDatabase()
            pass  # Connection pool initialized
            # Run migrations for missing columns
            await run_column_migrations()
            
        except Exception as e:
            pass  # Error initializing pool
            raise
            async with _pg_pool.acquire() as conn:
                await conn.execute('''
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS bank BIGINT DEFAULT 0;
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS ban_reason TEXT;
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS ban_until TIMESTAMP;
                    -- Loan system columns
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS loan_amount BIGINT DEFAULT 0;
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS loan_due TIMESTAMP;
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS loan_active BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS loan_defaulted BOOLEAN DEFAULT FALSE;
                ''')

async def run_column_migrations():
    """Ensure all required columns exist in tables."""
    global _pg_pool
    async with _pg_pool.acquire() as conn:
        # Users table columns
        await conn.execute('''
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS bank BIGINT DEFAULT 0;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS ban_reason TEXT;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS ban_until TIMESTAMP;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS claimed_achievements JSONB DEFAULT '[]';
            -- Loan system columns
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_amount BIGINT DEFAULT 0;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_due TIMESTAMP;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_active BOOLEAN DEFAULT FALSE;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_defaulted BOOLEAN DEFAULT FALSE;
            -- Loan interest/penalty columns
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_interest_rate DOUBLE PRECISION;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_penalty_rate DOUBLE PRECISION;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_base_due BIGINT;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS loan_tier TEXT;
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS last_loan_reminder TIMESTAMP;
            -- Safari Zone column
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS last_safari TIMESTAMP;
        ''')
        # Characters table columns
        await conn.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='characters' AND column_name='added_by'
                ) THEN
                    ALTER TABLE characters ADD COLUMN added_by BIGINT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='characters' AND column_name='anime'
                ) THEN
                    ALTER TABLE characters ADD COLUMN anime VARCHAR(255);
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='characters' AND column_name='mega'
                ) THEN
                    ALTER TABLE characters ADD COLUMN mega BOOLEAN DEFAULT FALSE;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='characters' AND column_name='type'
                ) THEN
                    ALTER TABLE characters ADD COLUMN type VARCHAR(100);
                END IF;
            END$$;
        ''')
        # Ensure character_id is auto-incrementing and unique
        await conn.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='characters' AND column_name='character_id'
                ) THEN
                    ALTER TABLE characters ADD COLUMN character_id SERIAL PRIMARY KEY;
                ELSE
                    BEGIN
                        -- If not identity, alter to identity (PostgreSQL 12+)
                        BEGIN
                            EXECUTE 'ALTER TABLE characters ALTER COLUMN character_id ADD GENERATED ALWAYS AS IDENTITY';
                        EXCEPTION WHEN others THEN NULL; -- Ignore if already identity
                        END;
                        -- Remove duplicates if any
                        DELETE FROM characters a USING characters b
                        WHERE a.ctid < b.ctid AND a.character_id = b.character_id;
                    END;
                END IF;
            END$$;
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                type TEXT, -- 'character' (NULL), 'token', or 'shard'
                character_id INTEGER,
                token_amount INTEGER,
                shard_amount INTEGER,
                created_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                max_claims INTEGER NOT NULL DEFAULT 1,
                claims INTEGER NOT NULL DEFAULT 0,
                claimed_by BIGINT[] DEFAULT ARRAY[]::BIGINT[]
            );
        ''')
        
        # Create battles table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS battles (
                id SERIAL PRIMARY KEY,
                battle_id VARCHAR(100) UNIQUE NOT NULL,
                challenger_id BIGINT NOT NULL,
                opponent_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                challenger_team JSONB DEFAULT '[]',
                opponent_team JSONB DEFAULT '[]',
                battle_log JSONB DEFAULT '[]',
                current_round INTEGER DEFAULT 0,
                current_turn VARCHAR(20) DEFAULT 'challenger',
                winner_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP
            );
            
            -- Create indexes for battles table
            CREATE INDEX IF NOT EXISTS idx_battles_challenger_id ON battles(challenger_id);
            CREATE INDEX IF NOT EXISTS idx_battles_opponent_id ON battles(opponent_id);
            CREATE INDEX IF NOT EXISTS idx_battles_status ON battles(status);
            CREATE INDEX IF NOT EXISTS idx_battles_battle_id ON battles(battle_id);
        ''')
        
        # Ensure all required columns exist (for existing tables)
        await conn.execute('''
            DO $$
            BEGIN
                -- Add shard_amount if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='shard_amount'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN shard_amount INTEGER;
                END IF;
                
                -- Add token_amount if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='token_amount'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN token_amount INTEGER;
                END IF;
                
                -- Add type if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='type'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN type TEXT;
                END IF;
                
                -- Add character_id if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='character_id'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN character_id INTEGER;
                END IF;
                
                -- Add created_by if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='created_by'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN created_by BIGINT;
                END IF;
                
                -- Add created_at if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='created_at'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                END IF;
                
                -- Add max_claims if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='max_claims'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN max_claims INTEGER NOT NULL DEFAULT 1;
                END IF;
                
                -- Add claims if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='claims'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN claims INTEGER NOT NULL DEFAULT 0;
                END IF;
                
                -- Add claimed_by if missing
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='redeem_codes' AND column_name='claimed_by'
                ) THEN
                    ALTER TABLE redeem_codes ADD COLUMN claimed_by BIGINT[] DEFAULT ARRAY[]::BIGINT[];
                END IF;
            END$$;
        ''')

class PostgresDatabase:
    async def get_users_with_active_loans_for_reminder(self, min_hours_since_last: int = 24):
        """Return users with active loans who should receive a reminder.

        Remind if:
        - loan_active = TRUE
        - AND (last_loan_reminder is NULL OR now() - last_loan_reminder >= min_hours_since_last)
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_id, wallet, loan_amount, loan_due, loan_interest_rate, loan_penalty_rate, loan_base_due
                    FROM users
                    WHERE loan_active = TRUE
                      AND (
                        last_loan_reminder IS NULL
                        OR last_loan_reminder <= NOW() - make_interval(hours => $1::int)
                      )
                    """,
                    min_hours_since_last,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching users for loan reminder: {e}")
            return []

    async def mark_loan_reminder_sent(self, user_id: int):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET last_loan_reminder = NOW() WHERE user_id = $1",
                    user_id,
                )
        except Exception as e:
            logger.error(f"Error marking loan reminder sent for {user_id}: {e}")
    async def ensure_loan_columns(self):
        """Ensure loan columns exist on users."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_amount'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_amount BIGINT DEFAULT 0;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_due'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_due TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_active'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_active BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_defaulted'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_defaulted BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_interest_rate'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_interest_rate DOUBLE PRECISION;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_penalty_rate'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_penalty_rate DOUBLE PRECISION;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_base_due'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_base_due BIGINT;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='loan_tier'
                        ) THEN
                            ALTER TABLE users ADD COLUMN loan_tier TEXT;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='last_loan_reminder'
                        ) THEN
                            ALTER TABLE users ADD COLUMN last_loan_reminder TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='last_safari'
                        ) THEN
                            ALTER TABLE users ADD COLUMN last_safari TIMESTAMP;
                        END IF;
                    END$$;
                    """
                )
        except Exception as e:
            logger.error(f"Error ensuring loan columns: {e}")
    async def reset_character_from_collections(self, character_id: int):
        """Remove character from all users' collections but keep in database."""
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET characters = array_remove(characters, $1)", character_id)
        return True
    async def delete_character(self, character_id: int):
        """Delete character from database and remove from all user collections."""
        async with self.pool.acquire() as conn:
            # Remove character from characters table
            await conn.execute("DELETE FROM characters WHERE character_id = $1", character_id)
            # Remove character from all users' characters arrays
            await conn.execute("UPDATE users SET characters = array_remove(characters, $1)", character_id)
        # Invalidate character cache
        if character_id in _character_cache:
            del _character_cache[character_id]
        return True
    async def edit_character(self, character_id: int, update_data: dict):
        """Edit character fields by character_id."""
        if not update_data:
            return False
        set_clauses = []
        params = []
        idx = 1
        for key, value in update_data.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(value)
            idx += 1
        sql = f"UPDATE characters SET {', '.join(set_clauses)} WHERE character_id = ${idx}"
        params.append(character_id)
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *params)
        # Invalidate character cache so updates are reflected
        if character_id in _character_cache:
            del _character_cache[character_id]
        return True
    async def add_character(self, character_data: dict):
        """Add a new character to the database and return its ID."""
        async with self.pool.acquire() as conn:
            # Remove explicit character_id if present
            data = dict(character_data)
            
            # Ensure anime field has a default value
            anime = data.get("anime")
            if not anime or anime.strip() == "":
                anime = "Unknown Anime"
            
            result = await conn.fetchrow(
                """
                INSERT INTO characters (name, anime, rarity, file_id, img_url, is_video, added_by, mega, type, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
                RETURNING character_id
                """,
                data.get("name"),
                anime,
                data.get("rarity"),
                data.get("file_id"),
                data.get("img_url"),
                data.get("is_video", False),
                data.get("added_by"),
                data.get("mega", False),
                data.get("type")
            )
            return result["character_id"] if result else None
    async def add_user_to_group(self, user_id, group_id):
        """Stub for add_user_to_group to prevent AttributeError. Does nothing."""
        pass
    async def get_daily_drops(self, rarity: str) -> int:
        """Get current daily drops count for a specific rarity"""
        try:
            settings = await self.get_drop_settings()
            if not settings:
                return 0
            
            daily_drops = settings.get('daily_drops', {})
            return daily_drops.get(rarity, 0)
            
        except Exception as e:
            logger.error(f"Error getting daily drops for {rarity}: {e}")
            return 0
    async def increment_daily_drops(self, rarity: str):
        """Increment daily drops counter for a specific rarity"""
        try:
            async with self.pool.acquire() as conn:
                # Get current drop settings
                settings = await self.get_drop_settings()
                if not settings:
                    return False
                
                # Get current daily drops
                daily_drops = settings.get('daily_drops', {})
                current_count = daily_drops.get(rarity, 0)
                
                # Increment the count
                daily_drops[rarity] = current_count + 1
                
                # Update the settings
                await self.update_drop_settings(settings)
                return True
                
        except Exception as e:
            logger.error(f"Error incrementing daily drops for {rarity}: {e}")
            return False
    async def ensure_drop_settings_columns(self):
        """Ensure the drop_settings table has all required columns"""
        query = """
        DO $$
        BEGIN
            -- Add daily_drops column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='drop_settings' AND column_name='daily_drops'
            ) THEN
                ALTER TABLE drop_settings ADD COLUMN daily_drops JSONB DEFAULT '{}';
            END IF;
            
            -- Add last_reset_date column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='drop_settings' AND column_name='last_reset_date'
            ) THEN
                ALTER TABLE drop_settings ADD COLUMN last_reset_date VARCHAR(10) DEFAULT '';
            END IF;
            
            -- Add time_weights column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='drop_settings' AND column_name='time_weights'
            ) THEN
                ALTER TABLE drop_settings ADD COLUMN time_weights JSONB DEFAULT '{}';
            END IF;
            
            -- Add rarity_progression column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='drop_settings' AND column_name='rarity_progression'
            ) THEN
                ALTER TABLE drop_settings ADD COLUMN rarity_progression JSONB DEFAULT '{}';
            END IF;
        END$$;
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query)
        except Exception as e:
            logger.error(f"Error ensuring drop_settings columns: {e}")

    async def ensure_collection_history_column(self):
        """Ensure the 'collection_history' column exists in the users table (JSONB, nullable)."""
        query = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='collection_history'
            ) THEN
                ALTER TABLE users ADD COLUMN collection_history JSONB;
            END IF;
        END$$;
        """
        try:
            await self.pool.execute(query)
        except Exception as e:
            pass  # Error handling, optionally print or raise
            raise
    async def ensure_active_action_column(self):
        """Ensure the 'active_action' column exists in the users table (JSONB, nullable)."""
        query = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='active_action'
            ) THEN
                ALTER TABLE users ADD COLUMN active_action JSONB;
            END IF;
        END$$;
        """
        try:
            await self.pool.execute(query)
        except Exception as e:
            pass  # Error handling, optionally print or raise
            raise

    async def ensure_claimed_achievements_column(self):
        """Ensure the 'claimed_achievements' column exists in the users table (JSONB, default '[]')."""
        query = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='claimed_achievements'
            ) THEN
                ALTER TABLE users ADD COLUMN claimed_achievements JSONB DEFAULT '[]';
            END IF;
        END$$;
        """
        try:
            await self.pool.execute(query)
        except Exception as e:
            pass  # Error handling, optionally print or raise
            raise

    async def update_user_atomic(self, user_id, new_characters, wallet_delta, sold_entries):
        # Ensure collection_history column exists before update
        await self.ensure_collection_history_column()
        """Atomically update characters, wallet, and append to collection_history for a user."""
        query = """
        UPDATE users
        SET characters = $1,
            wallet = wallet + $2,
            collection_history = COALESCE(collection_history, '[]'::jsonb) || $3::jsonb
        WHERE user_id = $4
        """
        import json
        def convert(obj):
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert(i) for i in obj]
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                return obj
        safe_entries = convert(sold_entries)
        try:
            await self.pool.execute(query, new_characters, wallet_delta, json.dumps(safe_entries), user_id)
        except Exception as e:
            pass  # Error handling, optionally print or raise
            raise
    async def set_favorite_character(self, user_id, character_id):
        """Set the user's favorite character by updating the favorite_character field."""
        query = """
            UPDATE users
            SET favorite_character = $1
            WHERE user_id = $2
        """
        try:
            await self.pool.execute(query, character_id, user_id)
        except Exception as e:
            pass  # Error handling, optionally print or raise
            raise
    async def get_all_characters(self) -> list:
        """Fetch all characters from the database as a list of dicts."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM characters")
                return [dict(row) for row in rows]
        except Exception as e:
            pass  # Error fetching all characters
            return []

    async def get_store_eligible_characters(self, count: int = 10) -> list:
        """Fetch characters eligible for store offers using PostgreSQL aggregation.
        Excludes Supreme rarity, is_video=True characters, and specific excluded IDs."""
        try:
            async with self.pool.acquire() as conn:
                # First check if is_video column exists
                column_check = await conn.fetchrow("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'characters' AND column_name = 'is_video'
                """)
                
                # Get total count of eligible characters for debugging
                if column_check:
                    count_query = """
                        SELECT COUNT(*) FROM characters 
                        WHERE rarity != 'Supreme' 
                        AND (is_video IS NULL OR is_video = false OR is_video = 'false')
                        AND character_id NOT IN (531, 664, 678, 849, 853, 877, 957, 1109, 1248, 1305)
                    """
                else:
                    count_query = """
                        SELECT COUNT(*) FROM characters 
                        WHERE rarity != 'Supreme' 
                        AND character_id NOT IN (531, 664, 678, 849, 853, 877, 957, 1109, 1248, 1305)
                    """
                
                total_count = await conn.fetchval(count_query)
                print(f"[DEBUG] get_store_eligible_characters: total eligible characters in DB: {total_count}")
                
                if column_check:
                    # Use PostgreSQL aggregation to filter and randomly select characters
                    # Handle is_video field more robustly - it might be NULL or not exist
                    query = """
                        SELECT * FROM characters 
                        WHERE rarity != 'Supreme' 
                        AND (is_video IS NULL OR is_video = false OR is_video = 'false')
                        AND character_id NOT IN (531, 664, 678, 849, 853, 877, 957, 1109, 1248, 1305)
                        ORDER BY RANDOM()
                        LIMIT $1
                    """
                else:
                    # Fallback if is_video column doesn't exist
                    query = """
                        SELECT * FROM characters 
                        WHERE rarity != 'Supreme' 
                        AND character_id NOT IN (531, 664, 678, 849, 853, 877, 957, 1109, 1248, 1305)
                        ORDER BY RANDOM()
                        LIMIT $1
                    """
                
                rows = await conn.fetch(query, count)
                result = [dict(row) for row in rows]
                print(f"[DEBUG] Store eligible characters: {len(result)} found, requested: {count}")
                # Log any characters with is_video=True that might have slipped through
                for char in result:
                    if char.get('is_video'):
                        print(f"[WARNING] Character {char.get('character_id')} has is_video=True but was included in store!")
                return result
        except Exception as e:
            print(f"[ERROR] Failed to fetch store eligible characters: {e}")
            return []

    async def get_all_user_ids(self) -> list:
        """Fetch all user IDs from the database."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id FROM users")
                return [row['user_id'] for row in rows]
        except Exception as e:
            pass  # Error fetching all user IDs
            return []

    async def get_characters_by_ids(self, char_ids: list) -> list:
        """Fetch characters by a list of character IDs."""
        if not char_ids:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM characters WHERE character_id = ANY($1::int[])",
                    char_ids
                )
                return [dict(row) for row in rows]
        except Exception as e:
            pass  # Error fetching characters by ids
            return []
    def __init__(self):
        self.pool = _pg_pool
        # Add collection-like attributes for compatibility with MongoDB interface
        self.users = self  # Use self for user operations
        self.characters = self  # Use self for character operations
        self.chat_settings = self  # Use self for chat settings operations
        self.claim_settings = self  # Use self for claim settings operations
        self.drop_settings = self  # Use self for drop settings operations
        self.propose_settings = self  # Use self for propose settings operations
        self.redeem_codes = self  # Use self for redeem codes operations
        
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user data by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not row:
                return None
            user = dict(row)
            # Ensure last_propose is always an ISO string if present
            if 'last_propose' in user and user['last_propose']:
                if isinstance(user['last_propose'], datetime):
                    user['last_propose'] = user['last_propose'].isoformat()
                else:
                    user['last_propose'] = str(user['last_propose'])
            
            # Parse active_action if it's stored as JSON string
            if 'active_action' in user and isinstance(user['active_action'], str):
                try:
                    import json
                    user['active_action'] = json.loads(user['active_action'])
                except (json.JSONDecodeError, TypeError):
                    user['active_action'] = None
            
            # Parse collection_history if it's stored as JSON string
            if 'collection_history' in user and isinstance(user['collection_history'], str):
                try:
                    import json
                    user['collection_history'] = json.loads(user['collection_history'])
                except (json.JSONDecodeError, TypeError):
                    user['collection_history'] = []
            
            # Parse store_offer if it's stored as JSON string
            if 'store_offer' in user and isinstance(user['store_offer'], str):
                try:
                    import json
                    user['store_offer'] = json.loads(user['store_offer'])
                except (json.JSONDecodeError, TypeError):
                    user['store_offer'] = {}
            
            # Parse claimed_achievements if it's stored as JSON string
            if 'claimed_achievements' in user and isinstance(user['claimed_achievements'], str):
                try:
                    import json
                    user['claimed_achievements'] = json.loads(user['claimed_achievements'])
                except (json.JSONDecodeError, TypeError):
                    user['claimed_achievements'] = []
            elif 'claimed_achievements' not in user:
                user['claimed_achievements'] = []
            
            return user

    async def add_user(self, user_data: dict):
        """Add a new user"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO users (
                        user_id, username, first_name, last_name, wallet, shards
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        updated_at = CURRENT_TIMESTAMP
                """, user_data['user_id'], user_data.get('username'),
                     user_data.get('first_name'), user_data.get('last_name'),
                     user_data.get('wallet', 0), user_data.get('shards', 0))
        except Exception as e:
            pass  # Error adding user

    async def sync_user_profile(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
        """Upsert the latest Telegram profile fields for a user.

        This keeps `users.username`, `users.first_name`, and `users.last_name` in sync
        without modifying wallet/shards or other fields.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    user_id, username, first_name, last_name
                )
            return True
        except Exception as e:
            logger.error(f"Error syncing user profile for {user_id}: {e}")
            return False
    
    async def update_user(self, user_id: int, update_data: dict):
        """Update user data"""
        import json
        set_clauses = []
        params = []
        idx = 1
        from datetime import datetime
        
        def convert(obj):
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert(i) for i in obj]
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                return obj
        
        for key, value in update_data.items():
            # Serialize dicts and lists for JSONB columns
            if key in ['active_action', 'collection_preferences'] and isinstance(value, dict):
                value = json.dumps(convert(value))
            elif key == 'collection_history' and isinstance(value, list):
                value = json.dumps(convert(value))
            elif key == 'store_offer' and isinstance(value, dict):
                value = json.dumps(convert(value))
            elif key == 'claimed_achievements' and isinstance(value, list):
                value = json.dumps(convert(value))
            elif key == 'last_propose' and value:
                if isinstance(value, str):
                    try:
                        value = datetime.fromisoformat(value)
                    except Exception:
                        pass  # If conversion fails, keep as is
            
            set_clauses.append(f"{key} = ${idx}")
            params.append(value)
            idx += 1
        if not set_clauses:
            return False
        sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = ${idx}"
        params.append(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *params)
        return True

    async def ensure_collection_handler_column(self):
        """Ensure the users table has collection_handler column and a unique index."""
        try:
            async with self.pool.acquire() as conn:
                # Add column if missing
                await conn.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='collection_handler'
                        ) THEN
                            ALTER TABLE users ADD COLUMN collection_handler VARCHAR(50);
                        END IF;
                    END$$;
                    """
                )
                # Create unique index (case-insensitive) if not exists, excluding NULLs
                await conn.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_indexes WHERE tablename = 'users' AND indexname = 'idx_users_collection_handler_unique'
                        ) THEN
                            CREATE UNIQUE INDEX idx_users_collection_handler_unique
                            ON users (LOWER(collection_handler))
                            WHERE collection_handler IS NOT NULL;
                        END IF;
                    END$$;
                    """
                )
        except Exception as e:
            # Best-effort; log and continue
            logger.error(f"Error ensuring collection_handler column/index: {e}")

    async def get_user_by_collection_handler(self, handler: str) -> Optional[Dict]:
        """Fetch user by collection_handler (case-insensitive)."""
        if not handler:
            return None
        await self.ensure_collection_handler_column()
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE LOWER(collection_handler) = LOWER($1)",
                    handler
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting user by collection_handler '{handler}': {e}")
            return None

    async def set_collection_handler(self, user_id: int, handler: Optional[str]) -> bool:
        """Set or clear a user's collection_handler after enforcing uniqueness."""
        await self.ensure_collection_handler_column()
        try:
            async with self.pool.acquire() as conn:
                # If setting a non-null handler, rely on unique index for enforcement
                await conn.execute(
                    "UPDATE users SET collection_handler = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                    handler, user_id
                )
            return True
        except Exception as e:
            # Unique violation or other errors
            logger.error(f"Error setting collection_handler for {user_id} -> '{handler}': {e}")
            return False
    
    async def get_character(self, char_id: int) -> Optional[Dict]:
        """Get character data by ID"""
        # Check cache first
        if char_id in _character_cache:
            _performance_stats['cache_hits'] += 1
            return _character_cache[char_id]
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM characters WHERE character_id = $1",
                    char_id
                )
                if row:
                    character_data = dict(row)
                    _character_cache[char_id] = character_data
                    _performance_stats['cache_hits'] += 1
                    return character_data
                return None
        except Exception as e:
            pass  # Error getting character
            return None
    
    async def get_character_by_file_id(self, file_id: str) -> Optional[Dict]:
        """Get character data by file_id"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM characters WHERE file_id = $1",
                    file_id
                )
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Error getting character by file_id: {e}")
            return None
    
    async def character_exists(self, character_id: int) -> bool:
        """Check if a character exists by character_id"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT 1 FROM characters WHERE character_id = $1",
                    character_id
                )
                return row is not None
        except Exception as e:
            logger.error(f"Error checking if character exists: {e}")
            return False
    
    async def get_user_collection(self, user_id: int) -> List[Dict]:
        """Get user's character collection"""
        try:
            async with self.pool.acquire() as conn:
                # First get the user's character IDs from the characters array
                user_result = await conn.fetchrow(
                    "SELECT characters FROM users WHERE user_id = $1",
                    user_id
                )
                
                if not user_result or not user_result[0]:
                    return []
                
                character_ids = user_result[0]
                if not character_ids:
                    return []
                
                # Get character details for all character IDs
                char_ids_tuple = tuple(character_ids)
                if len(char_ids_tuple) == 1:
                    char_ids_tuple = (char_ids_tuple[0],)
                
                rows = await conn.fetch("""
                    SELECT character_id, name, rarity, anime, img_url, file_id, is_video, type
                    FROM characters 
                    WHERE character_id = ANY($1::int[])
                    ORDER BY character_id
                """, char_ids_tuple)
                
                # Convert to list of dictionaries and add count information
                char_counts = {}
                for char_id in character_ids:
                    char_counts[char_id] = char_counts.get(char_id, 0) + 1
                
                collection = []
                for row in rows:
                    char_dict = dict(row)
                    char_dict['count'] = char_counts.get(char_dict['character_id'], 1)
                    collection.append(char_dict)
                
                return collection
        except Exception as e:
            pass  # Error getting user collection
            return []
    
    async def add_character_to_user(self, user_id: int, character_id: int, collected_at: datetime = None, source: str = 'collected'):
        if collected_at is None:
            collected_at = datetime.utcnow()
        # Always ensure collected_at is an ISO string
        if isinstance(collected_at, datetime):
            collected_at_str = collected_at.isoformat()
        else:
            # fallback: use current time
            collected_at_str = datetime.utcnow().isoformat()
        entry = {
            "character_id": character_id,
            "collected_at": collected_at_str,
            "source": source
        }
        async with self.pool.acquire() as conn:
            # Add character to user's collection
            await conn.execute("""
                UPDATE users 
                SET characters = CASE 
                    WHEN characters IS NULL THEN ARRAY[$2::integer] 
                    ELSE array_append(characters, $2::integer) 
                END
                WHERE user_id = $1
            """, user_id, character_id)

            # Append to collection_history
            await conn.execute("""
                UPDATE users
                SET collection_history = 
                    CASE 
                        WHEN collection_history IS NULL THEN to_jsonb(ARRAY[$2::jsonb])
                        ELSE collection_history || to_jsonb(ARRAY[$2::jsonb])
                    END
                WHERE user_id = $1
            """, user_id, json.dumps(entry))
    async def remove_character_from_user(self, user_id: int, character_id: int):
        """Remove character from user's collection"""
        try:
            async with self.pool.acquire() as conn:
                # Remove character from user's characters array
                # This removes ALL instances of the character from the user
                await conn.execute("""
                    UPDATE users 
                    SET characters = array_remove(characters, $2)
                    WHERE user_id = $1
                """, user_id, character_id)
                
                # Double-check: remove any remaining instances (in case of duplicates)
                while True:
                    result = await conn.execute("""
                        UPDATE users 
                        SET characters = array_remove(characters, $2)
                        WHERE user_id = $1 AND $2 = ANY(characters)
                    """, user_id, character_id)
                    
                    # If no rows were affected, we're done
                    if result.split()[-1] == '0':
                        break
                
        except Exception as e:
            pass  # Error removing character from user
    async def remove_single_character_from_user(self, user_id: int, character_id: int):
        """Remove a single instance of character_id from user's characters array (not all)."""
        try:
            async with self.pool.acquire() as conn:
                # Get current characters array
                row = await conn.fetchrow("SELECT characters FROM users WHERE user_id = $1", user_id)
                if not row or not row['characters']:
                    return False
                chars = list(row['characters'])
                if character_id in chars:
                    chars.remove(character_id)
                    await conn.execute("UPDATE users SET characters = $1 WHERE user_id = $2", chars, user_id)
                    return True
                return False
        except Exception as e:
            pass  # Error removing single character
            return False
    
    async def get_random_character(self, locked_rarities=None):
        """Get a random character"""
        try:
            if locked_rarities is None:
                locked_rarities = []
            
            async with self.pool.acquire() as conn:
                if locked_rarities:
                    row = await conn.fetchrow("""
                        SELECT * FROM characters 
                        WHERE rarity NOT IN (SELECT unnest($1::text[]))
                        ORDER BY RANDOM()
                        LIMIT 1
                    """, locked_rarities)
                else:
                    row = await conn.fetchrow("""
                        SELECT * FROM characters 
                        ORDER BY RANDOM()
                        LIMIT 1
                    """)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            pass  # Error getting random character
            return None
    
    async def get_random_character_by_rarities(self, rarities: list) -> dict:
        """Get a random character from specific rarities"""
        if not rarities:
            return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM characters 
                    WHERE rarity = ANY($1::text[])
                    ORDER BY RANDOM()
                    LIMIT 1
                """, rarities)
                
                if row:
                    return dict(row)
                return None
        except Exception as e:
            pass  # Error getting random character by rarities
            return None
    
    async def get_multiple_random_characters_by_rarity(self, rarity: str, count: int = 2) -> list:
        """Get multiple random characters of a specific rarity"""
        if count <= 0:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM characters 
                    WHERE rarity = $1
                    ORDER BY RANDOM()
                    LIMIT $2
                """, rarity, count)
                
                result = [dict(row) for row in rows]
                return result
        except Exception as e:
            return []
    
    async def get_random_character_by_rarities_excluding(self, excluded_rarities: list, count: int = 1) -> list:
        """Get random characters excluding specific rarities"""
        if count <= 0:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM characters 
                    WHERE rarity NOT IN (SELECT unnest($1::text[]))
                    ORDER BY RANDOM()
                    LIMIT $2
                """, excluded_rarities, count)
                
                return [dict(row) for row in rows]
        except Exception as e:
            pass  # Error getting random characters by rarities excluding
            return []
    
    async def get_propose_settings(self):
        """Get propose settings"""
        try:
            async with self.pool.acquire() as conn:
                # Get the most recent record (highest ID) to ensure consistency
                row = await conn.fetchrow("SELECT * FROM propose_settings ORDER BY id DESC LIMIT 1")
                if row:
                    settings = dict(row)
                    # Parse JSON fields if they are strings
                    if isinstance(settings.get('propose_weights'), str):
                        settings['propose_weights'] = json.loads(settings['propose_weights'])
                    if isinstance(settings.get('rarity_rates'), str):
                        settings['rarity_rates'] = json.loads(settings['rarity_rates'])
                    return settings
                
                # Create default settings if none exist
                default_settings = {
                    'locked_rarities': ['Common', 'Medium'],
                    'propose_cooldown': 100,
                    'propose_cost': 20000,
                    'acceptance_rate': 50,
                    'propose_weights': {
                        'Common': 30,
                        'Medium': 25,
                        'Rare': 20,
                        'Legendary': 15,
                        'Exclusive': 10,
                        'Elite': 5,
                        'Limited Edition': 3,
                        'Ultimate': 2,
                        'Supreme': 1,
                        'Zenith': 1,
                        'Mythic': 1,
                        'Ethereal': 1,
                        'Premium': 1
                    },
                    'rarity_rates': {
                        'Common': 80,
                        'Medium': 70,
                        'Rare': 60,
                        'Legendary': 50,
                        'Exclusive': 40,
                        'Elite': 30,
                        'Limited Edition': 20,
                        'Ultimate': 15,
                        'Supreme': 10,
                        'Zenith': 8,
                        'Mythic': 5,
                        'Ethereal': 3,
                        'Premium': 2
                    }
                }
                
                # Insert default settings
                await conn.execute("""
                    INSERT INTO propose_settings (
                        locked_rarities, propose_cooldown, propose_cost, acceptance_rate,
                        propose_weights, rarity_rates
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                """, 
                default_settings['locked_rarities'],
                default_settings['propose_cooldown'],
                default_settings['propose_cost'],
                default_settings['acceptance_rate'],
                json.dumps(default_settings['propose_weights']),
                json.dumps(default_settings['rarity_rates'])
                )
                
                return default_settings
                
        except Exception as e:
            logger.error(f"Error getting propose settings: {e}")
            return None
    
    async def update_propose_settings(self, settings: Dict[str, Any]):
        """Update propose settings"""
        try:
            # First, get current settings to merge with new ones
            current_settings = await self.get_propose_settings()
            if not current_settings:
                # If no current settings, use defaults
                current_settings = {
                    'locked_rarities': [],
                    'propose_cooldown': 100,
                    'propose_cost': 20000,
                    'acceptance_rate': 50,
                    'propose_weights': {},
                    'rarity_rates': {}
                }
            
            # Merge current settings with new settings
            merged_settings = current_settings.copy()
            merged_settings.update(settings)
            
            async with self.pool.acquire() as conn:
                # Get the current record ID to update the correct record
                current_row = await conn.fetchrow("SELECT id FROM propose_settings ORDER BY id DESC LIMIT 1")
                
                if current_row:
                    # Update the most recent record
                    current_id = current_row['id']
                    result = await conn.execute("""
                        UPDATE propose_settings 
                        SET locked_rarities = $1, propose_cooldown = $2, propose_cost = $3,
                            acceptance_rate = $4, propose_weights = $5, rarity_rates = $6,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $7
                    """, 
                    merged_settings.get('locked_rarities', []),
                    merged_settings.get('propose_cooldown', 100),
                    merged_settings.get('propose_cost', 20000),
                    merged_settings.get('acceptance_rate', 50),
                    json.dumps(merged_settings.get('propose_weights', {})),
                    json.dumps(merged_settings.get('rarity_rates', {})),
                    current_id
                    )
                    
                    logger.info(f"Updated propose_settings record ID {current_id}")
                else:
                    # No records exist, insert a new one
                    await conn.execute("""
                        INSERT INTO propose_settings (
                            locked_rarities, propose_cooldown, propose_cost, acceptance_rate,
                            propose_weights, rarity_rates
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                    """, 
                    merged_settings.get('locked_rarities', []),
                    merged_settings.get('propose_cooldown', 100),
                    merged_settings.get('propose_cost', 20000),
                    merged_settings.get('acceptance_rate', 50),
                    json.dumps(merged_settings.get('propose_weights', {})),
                    json.dumps(merged_settings.get('rarity_rates', {}))
                    )
                    
                    logger.info("Inserted new propose_settings record")
                
        except Exception as e:
            logger.error(f"Error updating propose settings: {e}")
            raise
    
    async def get_claim_settings(self) -> Optional[Dict[str, Any]]:
        """Get claim settings from database"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM claim_settings LIMIT 1")
                if row:
                    settings = dict(row)
                    # Parse JSON fields if they are strings
                    if isinstance(settings.get('settings'), str):
                        settings['settings'] = json.loads(settings['settings'])
                    return settings
                
                # Create default settings if none exist
                default_settings = {
                    'locked_rarities': [],
                    'claim_cooldown': 24,
                    'settings': {}
                }
                
                await conn.execute("""
                    INSERT INTO claim_settings (locked_rarities, claim_cooldown, settings)
                    VALUES ($1, $2, $3)
                """, default_settings['locked_rarities'], default_settings['claim_cooldown'], json.dumps(default_settings['settings']))
                
                return default_settings
                
        except Exception as e:
            pass  # Error getting claim settings
            return None
    
    async def update_claim_settings(self, settings: Dict[str, Any]):
        """Update claim settings in database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE claim_settings 
                    SET locked_rarities = $1, claim_cooldown = $2, settings = $3, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, settings.get('locked_rarities', []), settings.get('claim_cooldown', 24), json.dumps(settings.get('settings', {})))
                
        except Exception as e:
            pass  # Error updating claim settings
    
    async def log_user_transaction(self, user_id: int, action_type: str, details: dict):
        """Log user transaction"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_transactions (user_id, action_type, details, created_at)
                    VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                """, user_id, action_type, json.dumps(details))
                
        except Exception as e:
            pass  # Error handling, optionally print or raise
    
    async def get_drop_settings(self):
        """Get drop settings"""
        # Check cache first
        if 'drop_settings' in _drop_settings_cache:
            return _drop_settings_cache['drop_settings']
        
        try:
            # Ensure all required columns exist
            await self.ensure_drop_settings_columns()
            
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM drop_settings LIMIT 1")
                if row:
                    settings = dict(row)
                    # Parse JSON fields if they are strings
                    if isinstance(settings.get('rarity_weights'), str):
                        settings['rarity_weights'] = json.loads(settings['rarity_weights'])
                    if isinstance(settings.get('daily_limits'), str):
                        settings['daily_limits'] = json.loads(settings['daily_limits'])
                    if isinstance(settings.get('daily_drops'), str):
                        settings['daily_drops'] = json.loads(settings['daily_drops'])
                    if isinstance(settings.get('time_weights'), str):
                        settings['time_weights'] = json.loads(settings['time_weights'])
                    if isinstance(settings.get('rarity_progression'), str):
                        settings['rarity_progression'] = json.loads(settings['rarity_progression'])
                    _drop_settings_cache['drop_settings'] = settings
                    return settings
                
                # If no settings exist, create default ones
                print("No drop settings found, creating default settings...")
                default_settings = {
                    'rarity_weights': {
                        "Common": 1000,
                        "Medium": 500,
                        "Rare": 250,
                        "Legendary": 180,
                        "Exclusive": 50,
                        "Elite": 45,
                        "Limited Edition": 35,
                        "Ultimate": 0,
                        "Supreme": 0,
                        "Mythic": 0,
                        "Zenith": 0,
                        "Ethereal": 0,
                        "Premium": 0
                    },
                    'daily_limits': {
                        "Common": None,
                        "Medium": None,
                        "Rare": None,
                        "Legendary": None,
                        "Exclusive": None,
                        "Elite": None,
                        "Limited Edition": None,
                        "Ultimate": 0,
                        "Supreme": 0,
                        "Mythic": 0,
                        "Zenith": 0,
                        "Ethereal": 0,
                        "Premium": 0
                    },
                    'daily_drops': {},
                    'locked_rarities': [],
                    'drop_frequency': 300,
                    'last_reset_date': datetime.now().strftime('%Y-%m-%d'),
                    'time_weights': {},
                    'rarity_progression': {}
                }
                
                # Insert default settings
                await conn.execute("""
                    INSERT INTO drop_settings (
                        rarity_weights, daily_limits, daily_drops, locked_rarities,
                        drop_frequency, last_reset_date, time_weights, rarity_progression
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, json.dumps(default_settings['rarity_weights']),
                     json.dumps(default_settings['daily_limits']),
                     json.dumps(default_settings['daily_drops']),
                     default_settings['locked_rarities'],
                     default_settings['drop_frequency'],
                     default_settings['last_reset_date'],
                     json.dumps(default_settings['time_weights']),
                     json.dumps(default_settings['rarity_progression']))
                
                print("Default drop settings created successfully")
                _drop_settings_cache['drop_settings'] = default_settings
                return default_settings
                
        except Exception as e:
            logger.error(f"Error getting drop settings: {e}")
            return None
    
    async def update_drop_settings(self, settings: dict):
        """Update drop settings"""
        try:
            # Ensure all required columns exist
            await self.ensure_drop_settings_columns()
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE drop_settings 
                    SET rarity_weights = $1, daily_limits = $2, 
                        locked_rarities = $3, drop_frequency = $4,
                        daily_drops = $5, last_reset_date = $6,
                        time_weights = $7, rarity_progression = $8,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, json.dumps(settings.get('rarity_weights', {})),
                     json.dumps(settings.get('daily_limits', {})),
                     settings.get('locked_rarities', []),
                     settings.get('drop_frequency', 300),
                     json.dumps(settings.get('daily_drops', {})),
                     settings.get('last_reset_date', datetime.now().strftime('%Y-%m-%d')),
                     json.dumps(settings.get('time_weights', {})),
                     json.dumps(settings.get('rarity_progression', {})))
                
                # Clear cache
                _drop_settings_cache.clear()
                
        except Exception as e:
            logger.error(f"Error updating drop settings: {e}")
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user statistics"""
        # Check cache first
        if user_id in _user_stats_cache:
            return _user_stats_cache[user_id]
        
        try:
            async with self.pool.acquire() as conn:
                # Get user data
                user_row = await conn.fetchrow("""
                    SELECT wallet, shards, characters, created_at
                    FROM users WHERE user_id = $1
                """, user_id)
                
                if not user_row:
                    return {}
                
                user_data = dict(user_row)
                character_count = len(user_data.get('characters', []))
                
                # Get collection stats by rarity
                # Since we don't have user_characters table, we need to work with the characters array
                if user_data.get('characters'):
                    # Get character details for all characters in user's collection
                    char_ids = user_data['characters']
                    if char_ids:
                        # Create a temporary table or use array operations to get rarity stats
                        rarity_stats = await conn.fetch("""
                            SELECT c.rarity, COUNT(*) as count
                            FROM unnest($1::int[]) AS char_id
                            JOIN characters c ON c.character_id = char_id
                            GROUP BY c.rarity
                        """, char_ids)
                    else:
                        rarity_stats = []
                else:
                    rarity_stats = []
                
                stats = {
                    'user_id': user_id,
                    'wallet': user_data.get('wallet', 0),
                    'shards': user_data.get('shards', 0),
                    'total_characters': character_count,
                    'rarity_breakdown': {row['rarity']: row['count'] for row in rarity_stats},
                    'created_at': user_data.get('created_at')
                }
                
                _user_stats_cache[user_id] = stats
                return stats
                
        except Exception as e:
            logger.error(f"Error getting user stats {user_id}: {e}")
            return {}
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard"""
        # Check cache first
        cache_key = f'leaderboard_{limit}'
        if cache_key in _leaderboard_cache:
            return _leaderboard_cache[cache_key]
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT u.user_id, u.first_name, u.username, 
                           u.wallet, u.shards, array_length(u.characters, 1) as character_count
                    FROM users u
                    WHERE u.is_banned = FALSE
                    ORDER BY array_length(u.characters, 1) DESC, u.wallet DESC
                    LIMIT $1
                """, limit)
                
                leaderboard = [dict(row) for row in rows]
                _leaderboard_cache[cache_key] = leaderboard
                return leaderboard
                
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []
    
    async def get_chat_settings(self, chat_id: int):
        """Get chat settings"""
        # Check cache first
        if chat_id in _chat_settings_cache:
            return _chat_settings_cache[chat_id]
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM chat_settings WHERE chat_id = $1
                """, chat_id)
                
                if row:
                    settings = dict(row)
                    _chat_settings_cache[chat_id] = settings
                    return settings
                return None
                
        except Exception as e:
            logger.error(f"Error getting chat settings {chat_id}: {e}")
            return None
    
    async def update_chat_settings(self, chat_id: int, settings: dict):
        """Update chat settings"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO chat_settings (chat_id, chat_title, drop_enabled, drop_interval, last_drop)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        chat_title = EXCLUDED.chat_title,
                        drop_enabled = EXCLUDED.drop_enabled,
                        drop_interval = EXCLUDED.drop_interval,
                        last_drop = EXCLUDED.last_drop,
                        updated_at = CURRENT_TIMESTAMP
                """, chat_id, settings.get('chat_title'),
                     settings.get('drop_enabled', True),
                     settings.get('drop_interval', 300),
                     settings.get('last_drop'))
                
                # Clear cache
                if chat_id in _chat_settings_cache:
                    del _chat_settings_cache[chat_id]
                    
        except Exception as e:
            logger.error(f"Error updating chat settings {chat_id}: {e}")
    
    async def is_banned(self, user_id: int) -> bool:
        """Check if user is banned"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT is_banned FROM users WHERE user_id = $1
                """, user_id)
                return row and row['is_banned']
        except Exception as e:
            logger.error(f"Error checking ban status for user {user_id}: {e}")
            return False
    
    async def ban_user(self, user_id: int, permanent: bool = False, duration_minutes: int = 10):
        """Ban a user"""
        try:
            async with self.pool.acquire() as conn:
                if permanent:
                    await conn.execute("""
                        UPDATE users 
                        SET is_banned = TRUE, banned_at = CURRENT_TIMESTAMP
                        WHERE user_id = $1
                    """, user_id)
                else:
                    await conn.execute("""
                        UPDATE users 
                        SET last_temp_ban = CURRENT_TIMESTAMP
                        WHERE user_id = $1
                    """, user_id)
            return True
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")
            return False
    
    async def unban_user(self, user_id: int):
        """Unban a user"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE users SET is_banned = FALSE WHERE user_id = $1",
                    user_id
                )
                # Check if any row was affected
                return result.split()[-1] != '0'  # Returns True if rows were affected
        except Exception as e:
            logger.error(f"Error unbanning user {user_id}: {e}")
            return False
    
    async def remove_sudo(self, user_id: int):
        """Remove sudo privileges from a user"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE users SET sudo = FALSE WHERE user_id = $1",
                    user_id
                )
                # Check if any row was affected
                return result.split()[-1] != '0'  # Returns True if rows were affected
        except Exception as e:
            logger.error(f"Error removing sudo from user {user_id}: {e}")
            return False
    
    async def remove_og(self, user_id: int):
        """Remove OG status from a user"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE users SET og = FALSE WHERE user_id = $1",
                    user_id
                )
                # Check if any row was affected
                return result.split()[-1] != '0'  # Returns True if rows were affected
        except Exception as e:
            logger.error(f"Error removing OG status from user {user_id}: {e}")
            return False
    
    async def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Get user preferences"""
        import json
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT collection_preferences FROM users WHERE user_id = $1",
                user_id
            )
            if result and result[0]:
                try:
                    # Parse JSON string if it's a string
                    if isinstance(result[0], str):
                        return json.loads(result[0])
                    # If it's already a dict, return as is
                    elif isinstance(result[0], dict):
                        return result[0]
                    else:
                        return {
                            'mode': 'default',
                            'filter': None
                        }
                except (json.JSONDecodeError, TypeError):
                    return {
                        'mode': 'default',
                        'filter': None
                    }
            return {
                'mode': 'default',
                'filter': None
            }
    
    async def update_user_preferences(self, user_id: int, preferences: Dict[str, Any]):
        """Update user preferences"""
        import json
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET collection_preferences = $1 WHERE user_id = $2",
                json.dumps(preferences), user_id
            )
    
    async def close(self):
        """Close the database connection"""
        global _pg_pool
        if _pg_pool:
            await _pg_pool.close()
            _pg_pool = None
    
    # MongoDB-style methods for compatibility
    async def find_one(self, query: dict, projection: dict = None) -> Optional[Dict]:
        """MongoDB-style find_one method"""
        if 'user_id' in query:
            return await self.get_user(query['user_id'])
        elif 'character_id' in query:
            return await self.get_character(query['character_id'])
        elif 'chat_id' in query:
            return await self.get_chat_settings(query['chat_id'])
        return None
    
    async def update_one(self, query: dict, update: dict):
        """MongoDB-style update_one method for users table. Supports $set, $inc, $push. Handles nested JSONB keys."""
        if 'user_id' not in query:
            raise ValueError("update_one only supports user_id queries for now")
        user_id = query['user_id']
        set_fields = update.get('$set', {})
        inc_fields = update.get('$inc', {})
        push_fields = update.get('$push', {})
        updates = []
        params = []
        # $set
        for k, v in set_fields.items():
            param_idx = len(params) + 1
            if '.' in k:
                field, subkey = k.split('.', 1)
                # Always cast to text for jsonb_set to avoid polymorphic type errors
                updates.append(f"{field} = jsonb_set(COALESCE({field}, '{{}}'::jsonb), '{{{subkey}}}', to_jsonb(${param_idx}::text), true)")
                params.append(v if isinstance(v, str) else str(v))
            else:
                updates.append(f"{k} = ${param_idx}")
                params.append(v)
        # $inc
        for k, v in inc_fields.items():
            param_idx = len(params) + 1
            if '.' in k:
                field, subkey = k.split('.', 1)
                updates.append(f"{field} = jsonb_set(COALESCE({field}, '{{}}'::jsonb), '{{{subkey}}}', to_jsonb((COALESCE(({field}->>'{subkey}')::int, 0) + ${param_idx})), true)")
                params.append(v)
            else:
                updates.append(f"{k} = {k} + ${param_idx}")
                params.append(v)
        # $push (for JSONB arrays and integer[] arrays)
        for k, v in push_fields.items():
            param_idx = len(params) + 1
            # Handle $each for arrays
            if isinstance(v, dict) and '$each' in v:
                values = v['$each']
                if k == 'characters':
                    # For integer[] fields, use array concatenation
                    updates.append(f"{k} = COALESCE({k}, ARRAY[]::integer[]) || ${param_idx}::integer[]")
                    params.append(values)
                else:
                    # Default to jsonb array append - convert to JSON string first
                    import json
                    def convert_for_json(obj):
                        if isinstance(obj, dict):
                            return {k: convert_for_json(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [convert_for_json(i) for i in obj]
                        elif hasattr(obj, 'isoformat'):
                            return obj.isoformat()
                        else:
                            return obj
                    
                    json_values = json.dumps(convert_for_json(values))
                    updates.append(f"{k} = COALESCE({k}, '[]'::jsonb) || ${param_idx}::jsonb")
                    params.append(json_values)
            else:
                if '.' in k:
                    field, subkey = k.split('.', 1)
                    # Always cast to text for jsonb_set to avoid polymorphic type errors
                    updates.append(f"{field} = jsonb_set(COALESCE({field}, '{{}}'::jsonb), '{{{subkey}}}', (COALESCE({field}->'{subkey}', '[]'::jsonb) || to_jsonb(${param_idx}::text)), true)")
                    params.append(v if isinstance(v, str) else str(v))
                elif k == 'characters':
                    # For integer[] fields, use array_append
                    updates.append(f"{k} = array_append(COALESCE({k}, ARRAY[]::integer[]), ${param_idx}::integer)")
                    params.append(v)
                else:
                    # Default to jsonb array append
                    updates.append(f"{k} = COALESCE({k}, '[]'::jsonb) || to_jsonb(${param_idx})")
                    params.append(v)
        if not updates:
            return False
        param_idx = len(params) + 1
        sql = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ${param_idx}"
        params.append(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *params)
        return True
    
    async def find(self, query: dict = None, projection: dict = None):
        """MongoDB-style find method - returns a cursor-like object"""
        return PostgresCursor(self, query, projection)
    
    async def count_documents(self, query: dict = None) -> int:
        """MongoDB-style count_documents method"""
        if query is None:
            query = {}
        
        if 'user_id' in query:
            # Count users
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) FROM users WHERE user_id = $1", query['user_id'])
                return result[0] if result else 0
        elif 'character_id' in query:
            # Count characters
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) FROM characters WHERE character_id = $1", query['character_id'])
                return result[0] if result else 0
        elif 'is_video' in query:
            # Count video characters
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) FROM characters WHERE is_video = $1", query['is_video'])
                return result[0] if result else 0
        elif 'rarity' in query:
            # Count characters by rarity
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) FROM characters WHERE rarity = $1", query['rarity'])
                return result[0] if result else 0
        elif 'characters' in query:
            # Count users with specific character
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) FROM users WHERE $1 = ANY(characters::int[])", query['characters'])
                return result[0] if result else 0
        else:
            # Count all records in the appropriate table
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("SELECT COUNT(*) FROM users")
                return result[0] if result else 0
    
    def aggregate(self, pipeline: list):
        """MongoDB-style aggregate method"""
        return PostgresAggregationCursor(self, pipeline)
    
    async def estimated_document_count(self) -> int:
        """MongoDB-style estimated_document_count method"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("SELECT COUNT(*) FROM users")
            return result[0] if result else 0
        
    async def get_character_collectors(self, character_id: int) -> list:
        """Return a list of users who have collected the given character_id, excluding those who got it ONLY via admin commands."""
        try:
            async with self.pool.acquire() as conn:
                # Get users who have the character but exclude those who got it ONLY via 'give' source
                # This allows users who got the character from legitimate sources to be included
                # Also exclude user 6669536790 if they got the character via 'give' or 'massgive'
                rows = await conn.fetch(
                    """
                    SELECT u.user_id, u.characters 
                    FROM users u 
                    WHERE $1 = ANY(u.characters)
                    AND (
                        -- Exclude user 6669536790 if they got this character via 'give' or 'massgive'
                        u.user_id != 6669536790
                        OR
                        NOT EXISTS (
                            SELECT 1 
                            FROM jsonb_array_elements(COALESCE(u.collection_history, '[]'::jsonb)) AS entry
                            WHERE entry->>'character_id' = $1::text 
                            AND entry->>'source' IN ('give', 'massgive')
                        )
                    )
                    """,
                    character_id
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error in get_character_collectors for character {character_id}: {e}")
            return []
        
    async def get_top_collectors(self, character_id: int, limit: int = 5) -> list:
        """Return the top users who have collected the given character_id, with name, username, and count, excluding those who got it ONLY via admin commands."""
        try:
            char_id_int = int(character_id)
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT u.user_id, u.first_name AS name, u.username,
                        (SELECT COUNT(*) FROM unnest(u.characters) AS c WHERE c = $1) AS count
                    FROM users u
                    WHERE $1 = ANY(u.characters)
                    AND (
                        -- Exclude user 6669536790 if they got this character via 'give' or 'massgive'
                        u.user_id != 6669536790
                        OR
                        NOT EXISTS (
                            SELECT 1 
                            FROM jsonb_array_elements(COALESCE(u.collection_history, '[]'::jsonb)) AS entry
                            WHERE entry->>'character_id' = $1::text 
                            AND entry->>'source' IN ('give', 'massgive')
                        )
                    )
                    ORDER BY count DESC
                    LIMIT $2
                    """,
                    char_id_int, limit
                )
                return [dict(row) for row in rows if row['count'] > 0]
        except Exception as e:
            logger.error(f"Error in get_top_collectors for character {character_id}: {e}")
            return []
        
    # ...existing methods...

    async def get_group_collectors(self, chat_id, character_id):
        await self.ensure_groups_column()
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    '''
                    SELECT u.user_id, u.first_name AS name, u.username,
                        (SELECT COUNT(*) FROM unnest(u.characters) AS c WHERE c = $2) AS count
                    FROM users u
                    WHERE $2 = ANY(u.characters) AND $1::bigint = ANY(u.groups)
                    AND (
                        -- Exclude user 6669536790 if they got this character via 'give' or 'massgive'
                        u.user_id != 6669536790
                        OR
                        NOT EXISTS (
                            SELECT 1 
                            FROM jsonb_array_elements(COALESCE(u.collection_history, '[]'::jsonb)) AS entry
                            WHERE entry->>'character_id' = $2::text 
                            AND entry->>'source' IN ('give', 'massgive')
                        )
                    )
                    ORDER BY count DESC
                    LIMIT 10
                    ''', chat_id, character_id
                )
                return [dict(row) for row in rows if row['count'] > 0]
        except Exception as e:
            logger.error(f"Error in get_group_collectors for character {character_id} in chat {chat_id}: {e}")
            return []
        
    async def ensure_groups_column(self):
        """Ensure the 'groups' column exists in the users table (bigint[])."""
        query = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='groups'
            ) THEN
                ALTER TABLE users ADD COLUMN groups bigint[] DEFAULT ARRAY[]::bigint[];
            END IF;
            -- If column exists and is integer[], alter to bigint[]
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='groups' AND data_type='ARRAY' AND udt_name='_int4'
            ) THEN
                ALTER TABLE users ALTER COLUMN groups TYPE bigint[] USING groups::bigint[];
            END IF;
        END$$;
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query)
        except Exception as e:
            logger.error(f"Error ensuring groups column: {e}")

    async def add_user_to_group(self, user_id, group_id):
        """Add group_id to user's groups array if not already present."""
        await self.ensure_groups_column()
        query = """
        UPDATE users
        SET groups = (
            CASE WHEN NOT groups @> ARRAY[$1::bigint] THEN array_append(groups, $1::bigint) ELSE groups END
        )
        WHERE user_id = $2;
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, group_id, user_id)
        except Exception as e:
            logger.error(f"Error adding user {user_id} to group {group_id}: {e}")
        
    async def insert_redeem_code(self, redeem_data: dict):
        """Insert a new redeem code into the redeem_codes table."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO redeem_codes (code, type, character_id, token_amount, shard_amount, created_by, created_at, max_claims, claims, claimed_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                redeem_data.get("code"),
                redeem_data.get("type", "character"),
                redeem_data.get("character_id"),
                redeem_data.get("token_amount"),
                redeem_data.get("shard_amount"),
                redeem_data.get("created_by"),
                redeem_data.get("created_at"),
                redeem_data.get("max_claims"),
                redeem_data.get("claims", 0),
                redeem_data.get("claimed_by", []),
            )
    async def get_redeem_code(self, code: str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM redeem_codes WHERE LOWER(code) = LOWER($1)",
                code
            )
            return dict(row) if row else None

    async def update_redeem_code_claim(self, code: str, user_id: int):
        """Increment claims and add user_id to claimed_by for a redeem code."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE redeem_codes
                SET claims = claims + 1,
                    claimed_by = array_append(claimed_by, $2)
                WHERE LOWER(code) = LOWER($1)
                """,
                code, user_id
            )

    async def add_tdgoal_claim(self, user_id: int, today: str, task_id: str):
     async with self.pool.acquire() as conn:
        # Fetch current claimed
        row = await conn.fetchrow("SELECT tdgoal_claimed FROM users WHERE user_id = $1", user_id)
        import json
        claimed = row['tdgoal_claimed'] if row and row['tdgoal_claimed'] else {}
        if isinstance(claimed, str):
            try:
                claimed = json.loads(claimed)
            except Exception:
                claimed = {}
        today_claims = claimed.get(today, [])
        if task_id not in today_claims:
            today_claims.append(task_id)
        claimed[today] = today_claims
        await conn.execute(
            "UPDATE users SET tdgoal_claimed = $2 WHERE user_id = $1",
            user_id, json.dumps(claimed)
        )

    async def update_many(self, query: dict, update: dict):
        # Only support $unset for now
        unset_fields = update.get('$unset', {})
        if unset_fields:
            set_clauses = []
            for k in unset_fields:
                set_clauses.append(f"{k} = NULL")
            sql = f"UPDATE users SET {', '.join(set_clauses)}"
            async with self.pool.acquire() as conn:
                await conn.execute(sql)
            return True
        # You can add more logic for $set, $inc, etc. if needed
        return False

    async def get_todays_top_collectors(self, limit: int = 10):
        """Get today's top collectors efficiently using JSONB queries."""
        try:
            # Use UTC only for simplicity and consistency
            from datetime import datetime, timedelta
            
            # Get current UTC time and calculate today's boundaries
            utc_now = datetime.utcnow()
            today_utc = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_utc = today_utc + timedelta(days=1)
            
            query = """
            SELECT 
                u.user_id,
                u.first_name,
                COUNT(*) as today_count
            FROM users u,
            LATERAL jsonb_array_elements(
                CASE 
                    WHEN jsonb_typeof(u.collection_history) = 'array' THEN 
                        COALESCE(u.collection_history, '[]'::jsonb)
                    ELSE 
                        '[]'::jsonb
                END
            ) AS entry
            WHERE 
                entry->>'source' = 'collected'
                AND entry->>'collected_at' IS NOT NULL
                AND (
                    -- Handle both timestamp and string formats
                    CASE 
                        WHEN jsonb_typeof(entry->'collected_at') = 'string' THEN
                            (entry->>'collected_at')::timestamp >= $1
                            AND (entry->>'collected_at')::timestamp < $2
                        ELSE
                            (entry->>'collected_at')::timestamp >= $1
                            AND (entry->>'collected_at')::timestamp < $2
                    END
                )
            GROUP BY u.user_id, u.first_name
            ORDER BY today_count DESC
            LIMIT $3
            """
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, today_utc, tomorrow_utc, limit)
            
            collectors = []
            for row in rows:
                collectors.append({
                    'first_name': row['first_name'] or 'Unknown',
                    'user_id': row['user_id'],
                    'count': row['today_count']
                })
            
            return collectors
            
        except Exception as e:
            logger.error(f"Error getting today's top collectors: {e}")
            return []

    async def fix_redeem_codes_table(self):
        """Manually fix the redeem_codes table schema if it's missing columns."""
        try:
            async with self.pool.acquire() as conn:
                # Check if table exists
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'redeem_codes'
                    );
                """)
                
                if not table_exists:
                    # Create table from scratch
                    await conn.execute('''
                        CREATE TABLE redeem_codes (
                            code TEXT PRIMARY KEY,
                            type TEXT,
                            character_id INTEGER,
                            token_amount INTEGER,
                            shard_amount INTEGER,
                            created_by BIGINT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            max_claims INTEGER NOT NULL DEFAULT 1,
                            claims INTEGER NOT NULL DEFAULT 0,
                            claimed_by BIGINT[] DEFAULT ARRAY[]::BIGINT[]
                        );
                    ''')
                    print("✅ Created redeem_codes table from scratch")
                    return True
                
                # Check and add missing columns
                columns_to_check = [
                    ('shard_amount', 'INTEGER'),
                    ('token_amount', 'INTEGER'),
                    ('type', 'TEXT'),
                    ('character_id', 'INTEGER'),
                    ('created_by', 'BIGINT'),
                    ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                    ('max_claims', 'INTEGER NOT NULL DEFAULT 1'),
                    ('claims', 'INTEGER NOT NULL DEFAULT 0'),
                    ('claimed_by', 'BIGINT[] DEFAULT ARRAY[]::BIGINT[]')
                ]
                
                for column_name, column_type in columns_to_check:
                    column_exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_name = 'redeem_codes' AND column_name = $1
                        );
                    """, column_name)
                    
                    if not column_exists:
                        try:
                            await conn.execute(f"ALTER TABLE redeem_codes ADD COLUMN {column_name} {column_type}")
                            print(f"✅ Added missing column: {column_name}")
                        except Exception as e:
                            print(f"⚠️ Could not add column {column_name}: {e}")
                
                print("✅ Redeem codes table schema check completed")
                return True
                
        except Exception as e:
            print(f"❌ Error fixing redeem_codes table: {e}")
            return False

    # Active Drops Management Methods
    async def get_active_drops(self) -> list:
        """Get all active drops from the database"""
        try:
            async with self.pool.acquire() as conn:
                # Check if active_drops table exists, if not create it
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'active_drops'
                    );
                """)
                
                if not table_exists:
                    # Create active_drops table
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS active_drops (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            character_id INTEGER NOT NULL,
                            name VARCHAR(255) NOT NULL,
                            rarity VARCHAR(100) NOT NULL,
                            drop_message_id BIGINT NOT NULL,
                            dropped_at TIMESTAMP WITH TIME ZONE NOT NULL,
                            anime VARCHAR(255),
                            is_video BOOLEAN DEFAULT FALSE,
                            file_id TEXT,
                            img_url TEXT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                    """)
                    print("✅ Created active_drops table")
                
                # Fetch all active drops
                rows = await conn.fetch("""
                    SELECT chat_id, character_id, name, rarity, drop_message_id, 
                           dropped_at, anime, is_video, file_id, img_url
                    FROM active_drops 
                    ORDER BY dropped_at DESC
                """)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"Error getting active drops: {e}")
            return []
    
    async def add_active_drop(self, drop_data: dict):
        """Add a new active drop to the database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO active_drops (chat_id, character_id, name, rarity, drop_message_id, 
                                           dropped_at, anime, is_video, file_id, img_url)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """, 
                drop_data['chat_id'], drop_data['character_id'], drop_data['name'], 
                drop_data['rarity'], drop_data['drop_message_id'], drop_data['dropped_at'],
                drop_data['anime'], drop_data['is_video'], drop_data['file_id'], drop_data['img_url'])
                
        except Exception as e:
            print(f"Error adding active drop: {e}")
    
    async def clear_active_drops(self):
        """Clear all active drops from the database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM active_drops")
        except Exception as e:
            print(f"Error clearing active drops: {e}")
    
    async def remove_active_drop(self, chat_id: int, character_id: int):
        """Remove a specific active drop from the database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM active_drops 
                    WHERE chat_id = $1 AND character_id = $2
                """, chat_id, character_id)
        except Exception as e:
            print(f"Error removing active drop: {e}")

    async def get_weekly_battle_winners(self, limit: int = 10):
        """Get users with most battle wins in the current week (Monday to Sunday)."""
        try:
            from datetime import datetime, timedelta
            
            # Calculate the start of the current week (Monday)
            now = datetime.utcnow()
            days_since_monday = now.weekday()  # Monday is 0, Sunday is 6
            start_of_week = now - timedelta(days=days_since_monday)
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # End of week is next Monday
            end_of_week = start_of_week + timedelta(days=7)
            
            query = """
            SELECT 
                u.user_id,
                u.first_name,
                COUNT(*) as wins_count
            FROM users u
            JOIN battles b ON u.user_id = b.winner_id
            WHERE 
                b.winner_id IS NOT NULL
                AND b.status = 'finished'
                AND b.finished_at >= $1
                AND b.finished_at < $2
            GROUP BY u.user_id, u.first_name
            ORDER BY wins_count DESC
            LIMIT $3
            """
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, start_of_week, end_of_week, limit)
            
            winners = []
            for row in rows:
                winners.append({
                    'user_id': row['user_id'],
                    'first_name': row['first_name'] or 'Unknown',
                    'wins': row['wins_count']
                })
            
            return winners
            
        except Exception as e:
            logger.error(f"Error getting weekly battle winners: {e}")
            return []

class PostgresCursor:
    """Cursor-like object for PostgreSQL queries"""
    def __init__(self, db, query: dict = None, projection: dict = None):
        self.db = db
        self.query = query or {}
        self.projection = projection or {}
        self.limit_val = None
        self.skip_val = 0
        self.sort_field = None
        self.sort_direction = 1
    
    def limit(self, limit: int):
        self.limit_val = limit
        return self
    
    def skip(self, skip: int):
        self.skip_val = skip
        return self
    
    def sort(self, field: str, direction: int = 1):
        self.sort_field = field
        self.sort_direction = direction
        return self
    
    async def to_list(self, length: int = None):
        """Convert cursor to list"""
        if length is None and self.limit_val:
            length = self.limit_val
        
        # Build SQL query based on MongoDB-style query
        sql = "SELECT * FROM users"  # Default table
        params = []
        param_count = 0
        
        if 'user_id' in self.query:
            param_count += 1
            sql = "SELECT * FROM users WHERE user_id = $" + str(param_count)
            params.append(self.query['user_id'])
        elif 'character_id' in self.query:
            param_count += 1
            sql = "SELECT * FROM characters WHERE character_id = $" + str(param_count)
            params.append(self.query['character_id'])
        elif 'is_video' in self.query:
            param_count += 1
            sql = "SELECT * FROM characters WHERE is_video = $" + str(param_count)
            params.append(self.query['is_video'])
        elif 'rarity' in self.query:
            param_count += 1
            sql = "SELECT * FROM characters WHERE rarity = $" + str(param_count)
            params.append(self.query['rarity'])
        elif 'sudo' in self.query:
            param_count += 1
            sql = "SELECT * FROM users WHERE sudo = $" + str(param_count)
            params.append(self.query['sudo'])
        elif 'og' in self.query:
            param_count += 1
            sql = "SELECT * FROM users WHERE og = $" + str(param_count)
            params.append(self.query['og'])
        
        # Add sorting
        if self.sort_field:
            sql += f" ORDER BY {self.sort_field}"
            if self.sort_direction == -1:
                sql += " DESC"
        
        # Add limit and offset
        if self.limit_val:
            sql += f" LIMIT {self.limit_val}"
        if self.skip_val:
            sql += f" OFFSET {self.skip_val}"
        
        async with self.db.pool.acquire() as conn:
            results = await conn.fetch(sql, *params)
            return [dict(row) for row in results]
        

class PostgresAggregationCursor:
    """Aggregation cursor-like object for PostgreSQL"""
    def __init__(self, db, pipeline: list):
        self.db = db
        self.pipeline = pipeline
    
    async def to_list(self, length: int = None):
        """Convert aggregation cursor to list"""
        try:
            # Handle the specific aggregation pipeline used in vidcollection.py
            if len(self.pipeline) == 2:
                match_stage = self.pipeline[0]
                project_stage = self.pipeline[1]
                
                # Check if this is the character count aggregation
                if (match_stage.get('$match', {}).get('characters') and 
                    project_stage.get('$project', {}).get('count', {}).get('$size', {}).get('$filter')):
                    
                    character_id = match_stage['$match']['characters']
                    
                    # Convert MongoDB aggregation to SQL
                    async with self.db.pool.acquire() as conn:
                        # Count occurrences of this character in each user's collection
                        sql = """
                            SELECT user_id, 
                                   (SELECT COUNT(*) FROM unnest(characters) AS c WHERE c = $1) as count
                            FROM users 
                            WHERE $1 = ANY(characters)
                        """
                        results = await conn.fetch(sql, character_id)
                        return [dict(row) for row in results]
            
            # Default fallback for other aggregations
            return []
            
        except Exception as e:
            logger.error(f"Error in PostgresAggregationCursor.to_list: {e}")
            return []

# Initialize database instance
_db_instance = None

async def ensure_database():
    """Ensure database is initialized (compatibility function)"""
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized. Call init_database() first.")
    return True

async def init_database_instance(postgres_uri: str):
    """Initialize the database instance"""
    global _db_instance
    if _db_instance is None:
        # Initialize the connection pool
        await init_database(postgres_uri)
        _db_instance = PostgresDatabase()
        logger.info("PostgreSQL database initialized successfully")
    return _db_instance

def get_database():
    """Get the database instance"""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_instance

async def close_database():
    """Close database connections"""
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None

async def restart_connection_pool():
    """Restart the connection pool to clear cached statements"""
    global _pg_pool, _db_instance, _postgres_uri
    
    logger.info("Restarting PostgreSQL connection pool...")
    
    # Close existing pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
    
    # Reinitialize pool
    try:
        _pg_pool = await asyncpg.create_pool(
            _postgres_uri,
            min_size=5,
            max_size=20,
            command_timeout=30,
            server_settings={
                'jit': 'off',  # Disable JIT for better performance
                'statement_timeout': '30000',  # 30 seconds
                'idle_in_transaction_session_timeout': '60000'  # 1 minute
            }
        )
        
        # Test connection
        async with _pg_pool.acquire() as conn:
            await conn.execute('SELECT 1')
        
        # Update database instance
        _db_instance = PostgresDatabase()
        
        logger.info("PostgreSQL connection pool restarted successfully")
        
    except Exception as e:
        logger.error(f"Failed to restart PostgreSQL pool: {e}")
        raise