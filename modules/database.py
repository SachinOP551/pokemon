## MongoDB imports removed
from datetime import datetime
from typing import Optional, Dict, List, Any
import random
import base64
import aiohttp
from config import CATBOX_USERHASH
import aiosqlite
import asyncio
import logging
import json
from functools import lru_cache
import redis.asyncio as redis
from cachetools import TTLCache
import time
import gc
import weakref
import psutil
import threading
from collections import defaultdict

# Rate limiting for database operations
from asyncio import Semaphore
import time

# Database operation rate limiter
_db_semaphore = Semaphore(10)  # Limit concurrent database operations
_rate_limit_window = 60  # 1 minute window
_rate_limit_max_ops = 1000  # Max operations per minute
_rate_limit_ops = []

async def rate_limited_db_operation(operation_func, *args, **kwargs):
    """Execute database operation with rate limiting"""
    global _rate_limit_ops
    
    # Clean up old operations
    current_time = time.time()
    _rate_limit_ops = [op_time for op_time in _rate_limit_ops if current_time - op_time < _rate_limit_window]
    
    # Check rate limit
    if len(_rate_limit_ops) >= _rate_limit_max_ops:
        logger.warning("Database rate limit exceeded, waiting...")
        await asyncio.sleep(1)
    
    # Add current operation
    _rate_limit_ops.append(current_time)
    
    # Execute with semaphore
    async with _db_semaphore:
        return await operation_func(*args, **kwargs)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enhanced connection pool settings with better performance
ENHANCED_POOL_SETTINGS = {
    'maxPoolSize': 20,  # Reduced from 50 to prevent connection exhaustion
    'minPoolSize': 2,   # Reduced from 5
    'maxIdleTimeMS': 10000,  # Reduced idle time
    'waitQueueTimeoutMS': 2000,  # Faster timeout
    'maxConnecting': 5,  # Reduced from 10
    'serverSelectionTimeoutMS': 2000,  # Faster selection timeout
    'connectTimeoutMS': 3000,  # Reduced from 5000
    'socketTimeoutMS': 10000,  # Reduced from 15000
    'heartbeatFrequencyMS': 3000,  # More frequent heartbeats
    'retryWrites': True,
    'retryReads': True,
    'compressors': ['zlib'],  # Enable compression
    'zlibCompressionLevel': 6
}

# Global database instance with proper cleanup
_db_instance = None
_db_initialized = False
_mongo_client = None  # Single MongoDB client instance

# Optimized caching system with stricter memory limits
_character_cache = TTLCache(maxsize=500, ttl=1800)  # Reduced from 1000, 30 minutes TTL
_drop_settings_cache = TTLCache(maxsize=5, ttl=900)  # Reduced from 10, 15 minutes TTL
_user_stats_cache = TTLCache(maxsize=100, ttl=600)  # Reduced from 200, 10 minutes TTL
_leaderboard_cache = TTLCache(maxsize=3, ttl=180)  # Reduced from 5, 3 minutes TTL
_chat_settings_cache = TTLCache(maxsize=25, ttl=900)  # Reduced from 50, 15 minutes TTL

# Performance tracking with memory monitoring
_performance_stats = {
    'total_queries': 0,
    'cache_hits': 0,
    'cache_misses': 0,
    'last_cleanup': time.time(),
    'memory_usage': [],
    'connection_errors': 0,
    'slow_queries': 0
}

# Background cleanup task (removed)

# Connection health monitoring
_connection_health = {
    'last_check': time.time(),
    'is_healthy': True,
    'error_count': 0,
    'slow_query_count': 0
}

def get_mongo_client():
    """Get the single MongoDB client instance with health monitoring"""
    # MongoDB client removed
    return None

async def init_database():
    """Initialize the database connection with enhanced settings"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        
        logging.info("Database initialized successfully")
    return _db_instance

def get_database():
    """Get the database instance and ensure indexes are created"""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    # MongoDB ensure_indexes logic removed
    
    return _db_instance







def invalidate_character_cache(char_id: int):
    """Invalidate character cache"""
    if char_id in _character_cache:
        del _character_cache[char_id]

def invalidate_user_collection_cache(user_id: int):
    """Invalidate user collection cache (DISABLED)"""
    # Cache is disabled, no action needed
    pass

def invalidate_drop_settings_cache():
    """Invalidate drop settings cache"""
    _drop_settings_cache.clear()

def invalidate_user_stats_cache(user_id: int):
    """Invalidate user stats cache"""
    if user_id in _user_stats_cache:
        del _user_stats_cache[user_id]

def clear_all_caches():
    """Clear all caches to free memory"""
    try:
        _character_cache.clear()
        _drop_settings_cache.clear()
        _user_stats_cache.clear()
        _leaderboard_cache.clear()
        _chat_settings_cache.clear()
        logger.info("All caches cleared")
    except Exception as e:
        logger.error(f"Error clearing caches: {e}")
        # Try to clear individual caches if bulk clear fails
        try:
            if hasattr(_character_cache, 'clear'):
                _character_cache.clear()
            if hasattr(_drop_settings_cache, 'clear'):
                _drop_settings_cache.clear()
            if hasattr(_user_stats_cache, 'clear'):
                _user_stats_cache.clear()
            if hasattr(_leaderboard_cache, 'clear'):
                _leaderboard_cache.clear()
            if hasattr(_chat_settings_cache, 'clear'):
                _chat_settings_cache.clear()
            logger.info("Individual caches cleared")
        except Exception as e2:
            logger.error(f"Error clearing individual caches: {e2}")

def get_performance_stats():
    """Get current performance statistics"""
    return {
        'timestamp': datetime.now().isoformat(),
        'performance_stats': _performance_stats,
        'connection_health': _connection_health,
        'cache_sizes': {
            'character_cache': len(_character_cache),
            'drop_settings_cache': len(_drop_settings_cache),
            'user_stats_cache': len(_user_stats_cache),
            'leaderboard_cache': len(_leaderboard_cache),
            'chat_settings_cache': len(_chat_settings_cache)
        }
    }

async def close_database():
    """Close the database connection and cleanup resources"""
    global _mongo_client, _db_instance
    try:
        if _db_instance:
            await _db_instance.close()
        if _mongo_client:
            _mongo_client.close()
            logger.info("MongoDB client closed")
        clear_all_caches()
    except Exception as e:
        logger.error(f"Error closing database: {e}")

# Define rarity system
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
    "Premium": 13
}

# Define emoji mappings for rarities
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
    "Premium": "🧿"
}

def get_rarity_display(rarity: str) -> str:
    """Get the display format for a rarity (emoji + name)"""
    emoji = RARITY_EMOJIS.get(rarity, "❓")
    return f"{emoji} {rarity}"

def get_rarity_emoji(rarity: str) -> str:
    """Get just the emoji for a rarity"""
    return RARITY_EMOJIS.get(rarity, "❓")

# Update the migration mapping
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
    "🧿 Premium": "Premium"
}

class Database:
    def __init__(self, db_path: str = "marvelx.db"):
        """Initialize database with single client instance and enhanced connection pooling"""
        # MongoDB client and collections removed
        # TODO: Setup PostgreSQL connection and table references here
        # Example: self.conn = asyncpg.connect(...)
        # Add any required initialization for your backend
        
        # Enhanced caching with better memory management
        self.cache = TTLCache(maxsize=2000, ttl=1800)  # 30 minutes TTL
        self.media_cache = TTLCache(maxsize=1000, ttl=7200)  # 2 hours TTL
        
        # Batch operation queue for better performance
        self.batch_queue = []
        self.batch_size = 100
        self.batch_timeout = 5
        

        
        # Start background batch processor
        asyncio.create_task(self._batch_processor())
        
        logger.info("Database initialized with single client instance and enhanced settings")




    async def _batch_processor(self):
        """Process batched operations for better performance"""
        while True:
            try:
                if self.batch_queue:
                    # Process batch operations with size limit
                    batch_size = min(len(self.batch_queue), self.batch_size)
                    batch_ops = self.batch_queue[:batch_size]
                    self.batch_queue = self.batch_queue[batch_size:]
                    
                    # Group operations by type
                    user_updates = []
                    character_updates = []
                    
                    for op in batch_ops:
                        if op['type'] == 'user_update':
                            user_updates.append(op['data'])
                        elif op['type'] == 'character_update':
                            character_updates.append(op['data'])
                    
                    # Execute batch operations
                    if user_updates:
                        await self._execute_user_batch(user_updates)
                    if character_updates:
                        await self._execute_character_batch(character_updates)
                
                await asyncio.sleep(0.5)  # Check every 0.5 seconds (reduced from 1)
                
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(2)  # Reduced from 5

    async def _execute_user_batch(self, updates):
        """Execute batch user updates"""
        try:
            # Group updates by user_id to avoid conflicts
            user_updates = {}
            for update in updates:
                user_id = update['user_id']
                if user_id not in user_updates:
                    user_updates[user_id] = []
                user_updates[user_id].append(update['data'])
            
            # Execute updates for each user
            for user_id, update_data_list in user_updates.items():
                try:
                    # Merge all updates for this user
                    merged_update = {}
                    for update_data in update_data_list:
                        for operator, value in update_data.items():
                            if operator not in merged_update:
                                merged_update[operator] = {}
                            if isinstance(value, dict):
                                merged_update[operator].update(value)
                            else:
                                merged_update[operator] = value
                    
                    # Execute the merged update
                    await self.users.update_one(
                        {'user_id': user_id},
                        merged_update,
                        upsert=True
                    )
                    
                except Exception as e:
                    logger.error(f"Error updating user {user_id}: {e}")
                    # Fallback to individual operations if merge fails
                    for update_data in update_data_list:
                        try:
                            await self.users.update_one(
                                {'user_id': user_id},
                                update_data,
                                upsert=True
                            )
                        except Exception as fallback_error:
                            logger.error(f"Error in fallback update for user {user_id}: {fallback_error}")
            
            logger.debug(f"Executed {len(updates)} user batch operations")
                
        except Exception as e:
            logger.error(f"Error executing user batch: {e}")

    async def _execute_character_batch(self, updates):
        """Execute batch character updates"""
        try:
            # Group updates by character_id to avoid conflicts
            character_updates = {}
            for update in updates:
                character_id = update['character_id']
                if character_id not in character_updates:
                    character_updates[character_id] = []
                character_updates[character_id].append(update['data'])
            
            # Execute updates for each character
            for character_id, update_data_list in character_updates.items():
                try:
                    # Merge all updates for this character
                    merged_update = {}
                    for update_data in update_data_list:
                        for operator, value in update_data.items():
                            if operator not in merged_update:
                                merged_update[operator] = {}
                            if isinstance(value, dict):
                                merged_update[operator].update(value)
                            else:
                                merged_update[operator] = value
                    
                    # Execute the merged update
                    await self.characters.update_one(
                        {'character_id': character_id},
                        merged_update,
                        upsert=True
                    )
                    
                except Exception as e:
                    logger.error(f"Error updating character {character_id}: {e}")
                    # Fallback to individual operations if merge fails
                    for update_data in update_data_list:
                        try:
                            await self.characters.update_one(
                                {'character_id': character_id},
                                update_data,
                                upsert=True
                            )
                        except Exception as fallback_error:
                            logger.error(f"Error in fallback update for character {character_id}: {fallback_error}")
            
            logger.debug(f"Executed {len(updates)} character batch operations")
                
        except Exception as e:
            logger.error(f"Error executing character batch: {e}")

    async def get_character(self, char_id: int) -> Optional[Dict]:
        """Get character with enhanced caching"""
        try:
            _performance_stats['total_queries'] += 1
            
            # Check cache first
            if char_id in _character_cache:
                _performance_stats['cache_hits'] += 1
                return _character_cache[char_id]
            
            _performance_stats['cache_misses'] += 1
            
            # Query database
            character = await self.characters.find_one({"character_id": char_id})
            
            if character:
                # Cache the result
                _character_cache[char_id] = character
                return character
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting character {char_id}: {e}")
            return None

    async def get_user_collection(self, user_id: int) -> List[Dict]:
        """Get user collection without caching"""
        try:
            _performance_stats['total_queries'] += 1
            
            # Query database with optimized pipeline (no caching)
            user = await self.users.find_one({"user_id": user_id})
            if not user or not user.get('characters'):
                return []
                
            # Get all characters from the characters collection with optimized pipeline
            pipeline = [
                # Match the user's characters by character_id
                {
                    "$match": {
                        "character_id": {"$in": user['characters']}
                    }
                },
                # Group by character_id and count occurrences
                {
                    "$group": {
                        "_id": "$character_id",
                        "name": {"$first": "$name"},
                        "rarity": {"$first": "$rarity"},
                        "file_id": {"$first": "$file_id"},
                        "img_url": {"$first": "$img_url"},
                        "is_video": {"$first": "$is_video"},
                        "count": {
                            "$sum": {
                                "$size": {
                                    "$filter": {
                                        "input": user['characters'],
                                        "as": "char",
                                        "cond": {"$eq": ["$$char", "$character_id"]}
                                    }
                                }
                            }
                        }
                    }
                },
                # Sort by rarity and name
                {
                    "$sort": {
                        "rarity": 1,
                        "name": 1
                    }
                }
            ]

            collection = []
            async for doc in self.characters.aggregate(pipeline):
                collection.append({
                    'character_id': doc['_id'],
                    'name': doc.get('name', 'Unknown'),
                    'rarity': doc.get('rarity', 'Unknown'),
                    'file_id': doc.get('file_id'),
                    'img_url': doc.get('img_url'),
                    'is_video': doc.get('is_video', False),
                    'count': doc['count']
                })
                
            return collection
            
        except Exception as e:
            logger.error(f"Error getting user collection {user_id}: {e}")
            return []

    async def add_character_to_user(self, user_id: int, character_id: int, collected_at: datetime = None, source: str = 'collected'):
        """Add character to user with batch processing and immediate cache invalidation"""
        try:
            if collected_at is None:
                collected_at = datetime.now()
            
            # Add to batch queue for better performance
            self.batch_queue.append({
                'type': 'user_update',
                'data': {
                    'user_id': user_id,
                    'data': {
                        '$push': {
                            'characters': character_id,
                            'collection_history': {
                                'character_id': character_id,
                                'collected_at': collected_at,
                                'source': source
                            }
                        },
                        '$set': {
                            f'character_timestamps.{character_id}': collected_at
                        }
                    }
                }
            })
            
            # Cache invalidation disabled
            pass
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding character {character_id} to user {user_id}: {e}")
            return False

    async def remove_character_from_user(self, user_id: int, character_id: int):
        """Remove character from user with batch processing and immediate cache invalidation"""
        try:
            # Add to batch queue for better performance
            self.batch_queue.append({
                'type': 'user_update',
                'data': {
                    'user_id': user_id,
                    'data': {
                        '$pull': {'characters': character_id}
                    }
                }
            })
            
            # Cache invalidation disabled
            pass
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing character {character_id} from user {user_id}: {e}")
            return False

    async def remove_single_character_from_user(self, user_id: int, character_id: int):
        """Remove only one instance of a character from user's collection"""
        try:
            # Get current user data to find the first occurrence
            user_data = await self.users.find_one({'user_id': user_id})
            if not user_data or 'characters' not in user_data:
                return False
            
            characters = user_data['characters']
            if character_id not in characters:
                return False
            
            # Find the index of the first occurrence
            try:
                index_to_remove = characters.index(character_id)
            except ValueError:
                return False
            
            # Remove only the first occurrence
            characters.pop(index_to_remove)
            
            # Update the user's characters array
            self.batch_queue.append({
                'type': 'user_update',
                'data': {
                    'user_id': user_id,
                    'data': {
                        '$set': {'characters': characters}
                    }
                }
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing single character {character_id} from user {user_id}: {e}")
            return False

    async def get_random_character(self, locked_rarities=None):
        """Get random character with enhanced caching and optimized query"""
        try:
            _performance_stats['total_queries'] += 1
            
            if locked_rarities is None:
                locked_rarities = []
            
            # Get drop settings for weights
            settings = await self.get_drop_settings()
            rarity_weights = settings.get('rarity_weights', {})
            
            # Get all rarities not locked and with positive weight
            allowed_rarities = [r for r, w in rarity_weights.items() if w > 0 and r not in locked_rarities]
            if not allowed_rarities:
                return None
            
            # Use weighted random selection without multiplying sequences
            total_weight = sum(rarity_weights.get(r, 1) for r in allowed_rarities)
            if total_weight <= 0:
                return None
            
            # Pick a random number and find the corresponding rarity
            rand_val = random.uniform(0, total_weight)
            current_weight = 0
            
            for rarity in allowed_rarities:
                weight = rarity_weights.get(rarity, 1)
                current_weight += weight
                if rand_val <= current_weight:
                    selected_rarity = rarity
                    break
            else:
                # Fallback to random choice if something goes wrong
                selected_rarity = random.choice(allowed_rarities)
            
            # Use $sample to get a random character of that rarity
            cursor = self.characters.aggregate([
                {'$match': {'rarity': selected_rarity}},
                {'$sample': {'size': 1}}
            ])
            docs = [doc async for doc in cursor]
            
            if docs:
                character = docs[0]
                # Cache the character
                _character_cache[character['character_id']] = character
                return character
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting random character: {e}")
            return None

    async def get_drop_settings(self):
        """Get drop settings with enhanced caching"""
        try:
            _performance_stats['total_queries'] += 1
            
            # Check cache first
            if 'drop_settings' in _drop_settings_cache:
                _performance_stats['cache_hits'] += 1
                return _drop_settings_cache['drop_settings']
            
            _performance_stats['cache_misses'] += 1
            
            # Query database
            settings = await self.drop_settings.find_one({})
            if not settings:
                # Create default settings with all required fields
                default_settings = {
                    "locked_rarities": [],
                    "rarity_frequency": {
                        "Common": 100,
                        "Medium": 100,
                        "Rare": 100,
                        "Legendary": 100,
                        "Exclusive": 100,
                        "Elite": 100,
                        "Limited Edition": 100,
                        "Ultimate": 100,
                        "Supreme": 100,
                        "Zenith": 100,
                        "Mythic": 100,
                        "Ethereal": 100,
                        "Premium": 100
                    },
                    "daily_limits": {
                        "Common": 1000,
                        "Medium": 500,
                        "Rare": 200,
                        "Legendary": 100,
                        "Exclusive": 50,
                        "Elite": 25,
                        "Limited Edition": 10,
                        "Ultimate": 5,
                        "Supreme": 3,
                        "Zenith": 2,
                        "Mythic": 1,
                        "Ethereal": 1,
                        "Premium": 1
                    },
                    "daily_drops": {
                        "Common": 0,
                        "Medium": 0,
                        "Rare": 0,
                        "Legendary": 0,
                        "Exclusive": 0,
                        "Elite": 0,
                        "Limited Edition": 0,
                        "Ultimate": 0,
                        "Supreme": 0,
                        "Zenith": 0,
                        "Mythic": 0,
                        "Ethereal": 0,
                        "Premium": 0
                    },
                    "rarity_weights": {
                        "Common": 40,
                        "Medium": 25,
                        "Rare": 15,
                        "Legendary": 10,
                        "Exclusive": 5,
                        "Elite": 3,
                        "Limited Edition": 1,
                        "Ultimate": 0.5,
                        "Supreme": 0.3,
                        "Zenith": 0.2,
                        "Mythic": 0.1,
                        "Ethereal": 0.05,
                        "Premium": 0.02
                    },
                    "last_reset_date": datetime.now().strftime('%Y-%m-%d')
                }
                await self.drop_settings.insert_one(default_settings)
                settings = default_settings
            
            # Ensure all required fields exist (backward compatibility)
            if 'locked_rarities' not in settings:
                settings['locked_rarities'] = []
            if 'rarity_frequency' not in settings:
                settings['rarity_frequency'] = {r: 100 for r in ["Common", "Medium", "Rare", "Legendary", "Exclusive", "Elite", "Limited Edition", "Ultimate", "Supreme", "Zenith", "Mythic", "Ethereal", "Premium"]}
            if 'daily_drops' not in settings:
                settings['daily_drops'] = {r: 0 for r in ["Common", "Medium", "Rare", "Legendary", "Exclusive", "Elite", "Limited Edition", "Ultimate", "Supreme", "Zenith", "Mythic", "Ethereal", "Premium"]}
            
            # Cache the settings
            _drop_settings_cache['drop_settings'] = settings
            return settings
            
        except Exception as e:
            logger.error(f"Error getting drop settings: {e}")
            return None

    async def update_drop_settings(self, settings: dict):
        """Update drop settings and clear cache"""
        try:
            # Update the settings in database
            await self.drop_settings.replace_one({}, settings, upsert=True)
            
            # Clear the cache to force refresh
            if 'drop_settings' in _drop_settings_cache:
                del _drop_settings_cache['drop_settings']
            
            logger.info("Drop settings updated successfully")
            
        except Exception as e:
            logger.error(f"Error updating drop settings: {e}")

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user stats with enhanced caching"""
        try:
            _performance_stats['total_queries'] += 1
            
            # Check cache first
            if user_id in _user_stats_cache:
                _performance_stats['cache_hits'] += 1
                return _user_stats_cache[user_id]
            
            _performance_stats['cache_misses'] += 1
            
            # Query database with optimized aggregation
            pipeline = [
                {'$match': {'user_id': user_id}},
                {'$project': {
                    'user_id': 1,
                    'total_chars': {'$size': '$characters'},
                    'wallet': 1,
                    'shards': 1,
                    'is_banned': 1,
                    'is_sudo': 1,
                    'is_og': 1,
                    'joined_at': 1,
                    'last_active': 1
                }}
            ]
            
            result = await self.users.aggregate(pipeline).to_list(1)
            
            if result:
                stats = result[0]
                # Cache the result
                _user_stats_cache[user_id] = stats
                return stats
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting user stats {user_id}: {e}")
            return {}

    async def get_chat_settings(self, chat_id: int):
        """Get chat settings with enhanced caching"""
        try:
            _performance_stats['total_queries'] += 1
            
            # Check cache first
            if chat_id in _chat_settings_cache:
                _performance_stats['cache_hits'] += 1
                return _chat_settings_cache[chat_id]
            
            _performance_stats['cache_misses'] += 1
            
            settings = await self.chat_settings.find_one({'chat_id': chat_id})
            
            # Default settings if none exist
            if not settings:
                default_settings = {
                    'chat_id': chat_id,
                    'drop_time': 100,  # Default drop time
                    'message_count': 0,
                    'auto_drop': True
                }
                await self.chat_settings.insert_one(default_settings)
                settings = default_settings
            
            # Cache the result
            _chat_settings_cache[chat_id] = settings
            return settings
            
        except Exception as e:
            logger.error(f"Error getting chat settings {chat_id}: {e}")
            return None

    async def close(self):
        """Close database connection and cleanup resources"""
        try:
            # Process remaining batch operations
            if self.batch_queue:
                logger.info(f"Processing {len(self.batch_queue)} remaining batch operations")
                await self._batch_processor()
            
            # Don't close the client here as it's shared
            logger.info("Database instance closed")
            
        except Exception as e:
            logger.error(f"Error closing database: {e}")

    async def add_character(self, name: str, rarity: str, file_id: str, img_url: str, is_video: bool = False) -> int:
        """Add character with cache invalidation"""
        character_data = {
            "name": name,
            "rarity": rarity,
            "file_id": file_id,
            "img_url": img_url,
            "is_video": is_video
        }
        result = await self.characters.insert_one(character_data)
        return result.inserted_id

    async def update_character(self, char_id: int, **kwargs) -> bool:
        """Update character with cache invalidation"""
        if not kwargs:
            return False
            
        update_data = {k: v for k, v in kwargs.items() if v is not None}
        result = await self.characters.update_one(
            {"character_id": char_id},
            {"$set": update_data}
        )
        # Invalidate cache for this character
        if char_id in _character_cache:
            del _character_cache[char_id]
        return result.modified_count > 0

    async def delete_character(self, char_id: int) -> bool:
        """Delete character with cache invalidation"""
        result = await self.characters.delete_one({"character_id": char_id})
        # Invalidate cache for this character
        if char_id in _character_cache:
            del _character_cache[char_id]
        return result.deleted_count > 0

    async def add_to_collection(self, user_id: int, char_id: int) -> bool:
        """Add to collection with cache invalidation"""
        result = await self.users.update_one(
            {'user_id': user_id},
            {'$addToSet': {'characters': char_id}}
        )
        # Cache invalidation disabled
        pass
        return result.modified_count > 0

    async def remove_from_collection(self, user_id: int, char_id: int) -> bool:
        """Remove from collection with cache invalidation"""
        result = await self.users.update_one(
            {'user_id': user_id},
            {'$pull': {'characters': char_id}}
        )
        # Cache invalidation disabled
        pass
        return result.modified_count > 0

    async def get_character_owners_count(self, char_id: int) -> int:
        """Get character owners count with caching"""
        cache_key = f"owners_count:{char_id}"
        
        # Try memory cache
        if char_id in _character_cache: # This cache is for characters, not owners count
            return _character_cache[char_id]
        
        # Query database
        count = await self.users.count_documents({'characters': char_id})
        
        # Update cache
        _character_cache[char_id] = count # This cache is for characters, not owners count
        return count

    async def get_character_owners(self, char_id: int) -> List[int]:
        """Get character owners with caching"""
        cache_key = f"owners:{char_id}"
        
        # Try memory cache
        if char_id in _character_cache: # This cache is for characters, not owners
            return _character_cache[char_id]
        
        # Query database
        owners = await self.users.find({'characters': char_id}, {'user_id': 1}).to_list(None)
        
        # Update cache
        _character_cache[char_id] = [owner['user_id'] for owner in owners] # This cache is for characters, not owners
        return _character_cache[char_id]

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user stats with caching"""
        cache_key = f"stats:{user_id}"
        
        # Try memory cache
        if user_id in _character_cache: # This cache is for characters, not stats
            return _character_cache[user_id]
        
        # Query database with optimized joins
        stats = await self.users.aggregate([
            {'$match': {'user_id': user_id}},
            {'$project': {
                'total_chars': {'$size': '$characters'},
                'common': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Common']}}}},
                'uncommon': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Medium']}}}},
                'rare': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Rare']}}}},
                'epic': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Epic']}}}},
                'legendary': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Legendary']}}}},
                'mythic': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Mythic']}}}}
            }}
        ]).to_list(None)
        
        # Update cache
        _character_cache[user_id] = stats[0] if stats else {} # This cache is for characters, not stats
        return _character_cache[user_id]

    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard with caching"""
        cache_key = f"leaderboard:{limit}"
        
        # Try memory cache
        if limit in _character_cache: # This cache is for characters, not leaderboard
            return _character_cache[limit]
        
        # Query database with optimized joins
        leaderboard = await self.users.aggregate([
            {'$project': {
                'user_id': 1,
                'total_chars': {'$size': '$characters'},
                'legendary': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Legendary']}}}},
                'mythic': {'$size': {'$filter': {'input': '$characters', 'as': 'char', 'cond': {'$eq': ['$$char.rarity', 'Mythic']}}}}
            }},
            {'$sort': {'total_chars': -1, 'legendary': -1, 'mythic': -1}},
            {'$limit': limit}
        ]).to_list(None)
        
        # Update cache
        _character_cache[limit] = leaderboard # This cache is for characters, not leaderboard
        return leaderboard

    async def add_user(self, user_data: dict):
        """Add or update user with proper fields"""
        # Ensure required fields are present
        if 'user_id' not in user_data:
            return None
        # Add default fields if not present
        if 'first_name' not in user_data:
            user_data['first_name'] = 'Unknown'
        if 'username' not in user_data:
            user_data['username'] = ''
        if 'characters' not in user_data:
            user_data['characters'] = []
        if 'groups' not in user_data:
            user_data['groups'] = []
        if 'tokens' not in user_data:
            user_data['tokens'] = 100000  # Default 1 lakh tokens
        if 'shards' not in user_data:
            user_data['shards'] = 0  # 🎐 Shards currency
        result = await self.users.update_one(
            {'user_id': user_data['user_id']},
            {'$set': user_data},
            upsert=True
        )
        return result.upserted_id if result.modified_count > 0 else None

    async def update_user_shards(self, user_id: int, amount: int):
        """Update user's shards balance by incrementing amount (can be negative)"""
        try:
            user = await self.get_user(user_id)
            if not user:
                return False
            result = await self.users.update_one(
                {'user_id': user_id},
                {'$inc': {'shards': amount}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating user shards: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        # FIX: This backend does not support self.users.find_one. Implement your backend logic here.
        # For now, raise NotImplementedError so the error is clear.
        raise NotImplementedError("get_user is not implemented for this backend. Please implement database logic.")

    async def is_banned(self, user_id: int) -> bool:
        """Check if user is permanently banned from the database"""
        try:
            user = await self.users.find_one({"user_id": user_id})
            return user and user.get('is_banned', False)
        except Exception as e:
            logger.error(f"Error checking ban status for user {user_id}: {e}")
            return False

    async def ban_user(self, user_id: int, permanent: bool = False, duration_minutes: int = 10):
        """Ban a user - temporary (in memory) or permanent (in database)"""
        try:
            if permanent:
                # Permanent ban - store in database
                await self.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"is_banned": True, "banned_at": datetime.now().isoformat()}},
                    upsert=True
                )
            else:
                # Temporary ban - will be handled by memory system
                # Just log it for tracking purposes
                await self.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"last_temp_ban": datetime.now().isoformat()}},
                    upsert=True
                )
            return True
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")
            return False

    async def unban_user(self, user_id: int):
        """Unban a user from the database"""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": False}, "$unset": {"banned_at": ""}}
            )
            return True
        except Exception as e:
            logger.error(f"Error unbanning user {user_id}: {e}")
            return False

    async def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Get user collection preferences"""
        try:
            user_data = await self.get_user(user_id)
            if not user_data:
                return {'mode': 'default', 'filter': None}
            
            preferences = user_data.get('collection_preferences', {})
            return {
                'mode': preferences.get('mode', 'default'),
                'filter': preferences.get('filter', None)
            }
        except Exception as e:
            logger.error(f"Error getting user preferences {user_id}: {e}")
            return {'mode': 'default', 'filter': None}

    async def update_user_preferences(self, user_id: int, preferences: Dict[str, Any]):
        """Update user collection preferences"""
        try:
            await self.users.update_one(
                {'user_id': user_id},
                {'$set': {'collection_preferences': preferences}}
            )
        except Exception as e:
            logger.error(f"Error updating user preferences {user_id}: {e}")

    async def set_favorite_character(self, user_id: int, character_id: int):
        """Set user's favorite character"""
        try:
            await self.users.update_one(
                {'user_id': user_id},
                {'$set': {'favorite_character': character_id}}
            )
        except Exception as e:
            logger.error(f"Error setting favorite character {user_id}: {e}")

    async def get_propose_settings(self):
        """Get propose settings"""
        try:
            settings = await self.propose_settings.find_one({})
            if not settings:
                # Create default settings
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
                await self.propose_settings.insert_one(default_settings)
                settings = default_settings
            return settings
        except Exception as e:
            logger.error(f"Error getting propose settings: {e}")
            return None

    async def update_propose_settings(self, settings: Dict[str, Any]):
        """Update propose settings"""
        try:
            await self.propose_settings.update_one(
                {},
                {'$set': settings},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating propose settings: {e}")

    async def get_claim_settings(self) -> Optional[Dict[str, Any]]:
        """Get claim settings from database"""
        try:
            settings = await self.claim_settings.find_one({})
            if not settings:
                # Create default settings if none exist
                default_settings = {
                    'locked_rarities': [],
                    'claim_cooldown': 24
                }
                await self.claim_settings.insert_one(default_settings)
                settings = default_settings
            return settings
        except Exception as e:
            logger.error(f"Error getting claim settings: {e}")
            return None

    async def update_claim_settings(self, settings: Dict[str, Any]):
        """Update claim settings in database"""
        try:
            await self.claim_settings.update_one({}, {'$set': settings}, upsert=True)
        except Exception as e:
            logger.error(f"Error updating claim settings: {e}")

    async def get_daily_drops(self, rarity: str) -> int:
        """Get daily drops count for a specific rarity"""
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
        """Increment daily drops count for a specific rarity"""
        try:
            # Get current drop settings
            settings = await self.get_drop_settings()
            if not settings:
                # Create default settings if none exist
                settings = {
                    'daily_drops': {},
                    'drop_time': 50,
                    'rarity_weights': {},
                    'daily_limits': {}
                }
                await self.drop_settings.insert_one(settings)
            
            # Get current daily drops
            daily_drops = settings.get('daily_drops', {})
            current_count = daily_drops.get(rarity, 0)
            
            # Increment the count
            daily_drops[rarity] = current_count + 1
            
            # Update the settings
            await self.drop_settings.update_one(
                {},
                {'$set': {'daily_drops': daily_drops}},
                upsert=True
            )
            
            logger.debug(f"Incremented daily drops for {rarity}: {current_count + 1}")
            
        except Exception as e:
            logger.error(f"Error incrementing daily drops for {rarity}: {e}")

    async def update_user(self, user_id: int, update_data: dict):
        result = await self.users.update_one(
            {'user_id': user_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    # Admin-related methods
    async def make_sudo(self, user_id: int):
        # First ensure user exists with admin fields
        await self.users.update_one(
            {'user_id': user_id},
            {'$setOnInsert': {'og': False, 'sudo': False}},
            upsert=True
        )
        # Then set sudo status
        return await self.users.update_one(
            {'user_id': user_id},
            {'$set': {'sudo': True}}
        )

    async def make_og(self, user_id: int):
        # First ensure user exists with admin fields
        await self.users.update_one(
            {'user_id': user_id},
            {'$setOnInsert': {'og': False, 'sudo': False}},
            upsert=True
        )
        # Then set og status
        return await self.users.update_one(
            {'user_id': user_id},
            {'$set': {'og': True}}
        )

    async def remove_sudo(self, user_id: int):
        return await self.users.update_one(
            {'user_id': user_id},
            {'$set': {'sudo': False}}
        )

    async def remove_og(self, user_id: int):
        return await self.users.update_one(
            {'user_id': user_id},
            {'$set': {'og': False}}
        )

    async def get_next_character_id(self):
        # Find the highest current ID and increment by 1
        result = await self.characters.find_one(
            sort=[("character_id", -1)]
        )
        return 1 if result is None else result["character_id"] + 1

    async def add_character(self, character_data: dict):
        character_data["character_id"] = await self.get_next_character_id()
        # Ensure img_url is present for image characters
        if not character_data.get("is_video", False) and "img_url" not in character_data:
            character_data["img_url"] = None
        result = await self.characters.insert_one(character_data)
        return result.inserted_id

    async def edit_character(self, character_id: int, update_data: dict):
        # If updating file_id for image character, ensure img_url is also updated
        if not update_data.get("is_video", False) and "file_id" in update_data and "img_url" not in update_data:
            update_data["img_url"] = None
        result = await self.characters.update_one(
            {"character_id": character_id},
            {"$set": update_data}
        )
        # Invalidate cache for this character
        if character_id in _character_cache:
            del _character_cache[character_id]
        return result.modified_count > 0

    async def delete_character(self, character_id: int):
        result = await self.characters.delete_one({"character_id": character_id})
        # Invalidate cache for this character
        if character_id in _character_cache:
            del _character_cache[character_id]
        return result.deleted_count > 0

    async def get_character_collectors(self, character_id: str) -> List[Dict]:
        """Get all users who have collected this character, excluding those who got it via admin commands"""
        try:
            # Convert character_id to integer
            try:
                char_id = int(character_id)
            except ValueError:
                return []

            # Find all users who have this character but exclude those who got it via 'give' source
            cursor = self.users.find({"characters": char_id})
            collectors = []
            
            async for user in cursor:
                # Check if user got this character via admin command
                collection_history = user.get('collection_history', [])
                if isinstance(collection_history, str):
                    try:
                        import json
                        collection_history = json.loads(collection_history)
                    except:
                        collection_history = []
                
                # Check if any entry in collection_history shows this character was given by admin
                got_via_admin = any(
                    entry.get('character_id') == char_id and entry.get('source') == 'give'
                    for entry in collection_history
                )
                
                # Special check for user 6669536790 - exclude if they got via 'give' or 'massgive'
                user_id = user.get('user_id')
                if user_id == 6669536790:
                    got_via_admin_or_massgive = any(
                        entry.get('character_id') == char_id and entry.get('source') in ['give', 'massgive']
                        for entry in collection_history
                    )
                    if got_via_admin_or_massgive:
                        continue
                
                if not got_via_admin:
                    # Count occurrences of this character in user's collection
                    count = user['characters'].count(char_id)
                    # Get user's first name and username
                    first_name = user.get('first_name', 'Unknown')
                    username = user.get('username', '')
                    collectors.append({
                        'user_id': user['user_id'],
                        'name': first_name,
                        'username': username,
                        'count': count
                    })
            
            # Sort by count in descending order
            collectors.sort(key=lambda x: x['count'], reverse=True)
            return collectors
        except Exception as e:
            print(f"Error getting character collectors: {e}")
            return []

    async def get_group_collectors(self, chat_id: int, character_id) -> List[Dict]:
        """Get collectors of a character in a specific group. Robust to character_id type (int or str)."""
        try:
            # Try both int and str for character_id
            try:
                char_id_int = int(character_id)
            except (ValueError, TypeError):
                char_id_int = None
            char_id_str = str(character_id)

            # Get all users in this group who have this character (int or str)
            pipeline = [
                {"$match": {"groups": chat_id}},
                {"$unwind": "$characters"},
                {"$match": {"$or": [
                    {"characters": char_id_int} if char_id_int is not None else {},
                    {"characters": char_id_str}
                ]}},
                # Add a field to check if user got this character via admin command
                {
                    "$addFields": {
                        "got_via_admin": {
                            "$anyElementTrue": {
                                "$map": {
                                    "input": {"$ifNull": ["$collection_history", []]},
                                    "as": "entry",
                                    "in": {
                                        "$and": [
                                            {"$eq": ["$$entry.character_id", char_id_str]},
                                            {"$eq": ["$$entry.source", "give"]}
                                        ]
                                    }
                                }
                            }
                        },
                        "got_via_admin_or_massgive": {
                            "$anyElementTrue": {
                                "$map": {
                                    "input": {"$ifNull": ["$collection_history", []]},
                                    "as": "entry",
                                    "in": {
                                        "$and": [
                                            {"$eq": ["$$entry.character_id", char_id_str]},
                                            {"$in": ["$$entry.source", ["give", "massgive"]]}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                # Filter out users who got the character via admin command
                {"$match": {"got_via_admin": False}},
                # Filter out user 6669536790 if they got via 'give' or 'massgive'
                {"$match": {
                    "$or": [
                        {"_id": {"$ne": 6669536790}},
                        {"got_via_admin_or_massgive": False}
                    ]
                }},
                {"$group": {
                    "_id": "$user_id",
                    "count": {"$sum": 1},
                    "first_name": {"$first": "$first_name"},
                    "username": {"$first": "$username"}
                }},
                {"$sort": {"count": -1}}
            ]

            collectors = []
            async for doc in self.users.aggregate(pipeline):
                collectors.append({
                    'user_id': doc['_id'],
                    'name': doc.get('first_name', 'Unknown'),
                    'username': doc.get('username', ''),
                    'count': doc['count']
                })

            return collectors
        except Exception as e:
            print(f"Error getting group collectors: {e}")
            return []

    async def add_user_to_group(self, user_id: int, chat_id: int):
        """Add a group to user's groups list"""
        try:
            # First ensure user exists
            user = await self.get_user(user_id)
            if not user:
                return False

            # Add group to user's groups list
            await self.users.update_one(
                {'user_id': user_id},
                {'$addToSet': {'groups': chat_id}}
            )
            return True
        except Exception as e:
            print(f"Error adding user to group: {e}")
            return False

    async def remove_user_from_group(self, user_id: int, chat_id: int):
        """Remove a group from user's groups list"""
        try:
            await self.users.update_one(
                {'user_id': user_id},
                {'$pull': {'groups': chat_id}}
            )
            return True
        except Exception as e:
            print(f"Error removing user from group: {e}")
            return False

    async def get_top_collectors(self, character_id: str, limit: int = 5) -> List[Dict]:
        """Get top collectors of a character, excluding those who got it via admin commands"""
        try:
            # Convert character_id to integer
            try:
                char_id = int(character_id)
            except ValueError:
                return []

            # Get all users who have this character but exclude those who got it via 'give' source
            pipeline = [
                # Unwind the characters array to count occurrences
                {"$unwind": "$characters"},
                # Match only this character
                {"$match": {"characters": char_id}},
                # Add a field to check if user got this character via admin command
                {
                    "$addFields": {
                        "got_via_admin": {
                            "$anyElementTrue": {
                                "$map": {
                                    "input": {"$ifNull": ["$collection_history", []]},
                                    "as": "entry",
                                    "in": {
                                        "$and": [
                                            {"$eq": ["$$entry.character_id", char_id]},
                                            {"$eq": ["$$entry.source", "give"]}
                                        ]
                                    }
                                }
                            }
                        },
                        "got_via_admin_or_massgive": {
                            "$anyElementTrue": {
                                "$map": {
                                    "input": {"$ifNull": ["$collection_history", []]},
                                    "as": "entry",
                                    "in": {
                                        "$and": [
                                            {"$eq": ["$$entry.character_id", char_id]},
                                            {"$in": ["$$entry.source", ["give", "massgive"]]}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                # Filter out users who got the character via admin command
                {"$match": {"got_via_admin": False}},
                # Filter out user 6669536790 if they got via 'give' or 'massgive'
                {"$match": {
                    "$or": [
                        {"user_id": {"$ne": 6669536790}},
                        {"got_via_admin_or_massgive": False}
                    ]
                }},
                # Group by user to count occurrences
                {
                    "$group": {
                        "_id": "$user_id",
                        "count": {"$sum": 1},
                        "first_name": {"$first": "$first_name"},
                        "username": {"$first": "$username"}
                    }
                },
                # Sort by count in descending order
                {"$sort": {"count": -1}},
                # Limit to top N collectors
                {"$limit": limit}
            ]

            collectors = []
            async for doc in self.users.aggregate(pipeline):
                collectors.append({
                    'user_id': doc['_id'],
                    'name': doc.get('first_name', 'Unknown'),
                    'username': doc.get('username', ''),
                    'count': doc['count']
                })

            return collectors
        except Exception as e:
            print(f"Error getting top collectors: {e}")
            return []

    async def get_random_character_by_rarities(self, rarities: list) -> dict:
        """Get a random character from specific rarities using $sample aggregation."""
        if not rarities:
            return None
        cursor = self.characters.aggregate([
            {'$match': {'rarity': {'$in': rarities}}},
            {'$sample': {'size': 1}}
        ])
        docs = [doc async for doc in cursor]
        return docs[0] if docs else None

    async def get_random_character_by_rarities_excluding(self, excluded_rarities: list, count: int = 1) -> list:
        """Get random characters excluding specific rarities using $sample aggregation."""
        if count <= 0:
            return []
        
        cursor = self.characters.aggregate([
            {'$match': {'rarity': {'$nin': excluded_rarities}}},
            {'$sample': {'size': count}}
        ])
        docs = [doc async for doc in cursor]
        return docs

    async def reset_character_from_collections(self, character_id: int):
        """Remove a character from all users' collections"""
        try:
            # Update all users who have this character in their collection
            await self.users.update_many(
                {'characters': character_id},
                {'$pull': {'characters': character_id}}
            )
            return True
        except Exception as e:
            print(f"Error resetting character from collections: {e}")
            return False

    async def get_character_owners_count(self, character_id: int) -> int:
        """Get the total number of users who own this character"""
        try:
            # Count all users who have this character in their collection
            count = await self.users.count_documents({'characters': character_id})
            return count
        except Exception as e:
            print(f"Error getting character owners count: {e}")
            return 0

    async def update_missing_img_urls(self, client):
        """Update characters that have file_id but missing img_url"""
        try:
            # Find all characters that have file_id but no img_url or null img_url
            characters = await self.characters.find({
                'file_id': {'$exists': True},
                '$or': [
                    {'img_url': {'$exists': False}},
                    {'img_url': None}
                ],
                'is_video': {'$ne': True}  # Exclude video characters
            }).to_list(None)
            
            if not characters:
                return "No characters found needing img_url update."
            
            updated_count = 0
            failed_chars = []
            expired_file_ids = []
            
            for character in characters:
                try:
                    # Get file from Telegram using Pyrogram
                    try:
                        import asyncio
                        file = await asyncio.wait_for(client.download_media(character['file_id'], in_memory=True), timeout=120)
                        if not file:
                            failed_chars.append(f"ID {character['character_id']}: Empty file")
                            continue
                        file_bytes = file
                    except asyncio.TimeoutError:
                        failed_chars.append(f"ID {character['character_id']}: Timeout downloading media (120 seconds exceeded)")
                        continue
                    except Exception as e:
                        if "Bad Request" in str(e) or "file not found" in str(e).lower():
                            expired_file_ids.append(character['character_id'])
                            failed_chars.append(f"ID {character['character_id']}: Expired file_id")
                            continue
                        raise e
                    
                    if not file_bytes:
                        failed_chars.append(f"ID {character['character_id']}: Empty file")
                        continue
                    
                    # Upload to Catbox with retry
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            async with aiohttp.ClientSession() as session:
                                data = aiohttp.FormData()
                                # Create a temporary file-like object for upload
                                import io
                                file_obj = io.BytesIO(file_bytes)
                                data.add_field('fileToUpload', file_obj, filename='image.jpg', content_type='image/jpeg')
                                async with session.post('https://catbox.moe/user/api.php', data=data, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                                    if response.status != 200:
                                        if attempt < max_retries - 1:
                                            continue
                                        failed_chars.append(f"ID {character['character_id']}: HTTP {response.status}")
                                        break
                                    
                                    result = await response.text()
                                    if result and not result.startswith('Error'):
                                        img_url = result.strip()
                                        # Update character with img_url
                                        await self.characters.update_one(
                                            {'_id': character['_id']},
                                            {'$set': {'img_url': img_url}}
                                        )
                                        updated_count += 1
                                        break
                                    else:
                                        if attempt < max_retries - 1:
                                            continue
                                        failed_chars.append(f"ID {character['character_id']}: Catbox error - {result if result else 'Unknown error'}")
                                        break
                        except aiohttp.ClientError as e:
                            if attempt < max_retries - 1:
                                continue
                            failed_chars.append(f"ID {character['character_id']}: Network error - {str(e)}")
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                continue
                            failed_chars.append(f"ID {character['character_id']}: {str(e)}")
                            break
                            
                except Exception as e:
                    failed_chars.append(f"ID {character['character_id']}: {str(e)}")
            
            # Prepare detailed report
            report = f"Updated {updated_count} characters.\n"
            if failed_chars:
                report += f"\nFailed ({len(failed_chars)}):\n"
                # Group similar errors
                error_groups = {}
                for error in failed_chars:
                    if error in error_groups:
                        error_groups[error] += 1
                    else:
                        error_groups[error] = 1
                
                # Add grouped errors to report
                for error, count in error_groups.items():
                    report += f"- {error} (x{count})\n"
            
            if expired_file_ids:
                report += f"\n⚠️ Found {len(expired_file_ids)} characters with expired file_ids.\n"
                report += "These characters need to be re-uploaded with new images.\n"
                report += "Character IDs: " + ", ".join(map(str, expired_file_ids))
            
            return report
            
        except Exception as e:
            print(f"Error in update_missing_img_urls: {e}")
            return f"Error: {str(e)}"

    async def update_character(self, character_id: int, update_data: dict):
        """Update character data"""
        result = await self.characters.update_one(
            {"character_id": character_id},
            {"$set": update_data}
        )
        # Invalidate cache for this character
        if character_id in _character_cache:
            del _character_cache[character_id]
        return result.modified_count > 0

    async def update_user_wallet(self, user_id: int, amount: int):
        """Update user's token balance"""
        try:
            # First ensure user exists
            user = await self.get_user(user_id)
            if not user:
                return False

            # Update tokens
            result = await self.users.update_one(
                {'user_id': user_id},
                {'$inc': {'wallet': amount}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating user wallet: {e}")
            return False

    async def get_all_characters(self):
        """Get all characters from database"""
        cursor = self.characters.find({})
        characters = []
        async for char in cursor:
            characters.append(char)
        return characters

    async def get_random_characters(self, n=10):
        """Get n random characters"""
        pipeline = [{"$sample": {"size": n}}]
        characters = []
        async for char in self.characters.aggregate(pipeline):
            characters.append(char)
        return characters

    # Referral System Methods
    async def generate_referral_code(self, user_id: int) -> str:
        """Generate a unique referral code for a user"""
        import random
        import string
        
        # Generate a 6-character alphanumeric code
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Check if code already exists
        existing_user = await self.users.find_one({"referral_code": code})
        if existing_user:
            # If code exists, generate a new one
            return await self.generate_referral_code(user_id)
        
        # Update user with referral code
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"referral_code": code}}
        )
        
        return code

    async def get_referral_code(self, user_id: int) -> str:
        """Get or generate referral code for a user"""
        user = await self.get_user(user_id)
        if not user:
            return None
            
        if not user.get('referral_code'):
            return await self.generate_referral_code(user_id)
        
        return user.get('referral_code')

    async def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict]:
        """Get user by referral code"""
        user = await self.users.find_one({"referral_code": referral_code})
        return user

    async def add_referral(self, referrer_id: int, referred_id: int):
        """Add a referral relationship"""
        # Update referrer's referrals list
        await self.users.update_one(
            {"user_id": referrer_id},
            {"$addToSet": {"referrals": referred_id}}
        )
        
        # Update referred user's referrer
        await self.users.update_one(
            {"user_id": referred_id},
            {"$set": {"referred_by": referrer_id}}
        )

    async def get_referrals(self, user_id: int) -> List[Dict]:
        """Get all users referred by a specific user"""
        user = await self.get_user(user_id)
        if not user or not user.get('referrals'):
            return []
        
        referrals = []
        for referred_id in user.get('referrals', []):
            referred_user = await self.get_user(referred_id)
            if referred_user:
                referrals.append({
                    'user_id': referred_id,
                    'first_name': referred_user.get('first_name', 'Unknown'),
                    'username': referred_user.get('username', ''),
                    'joined_at': referred_user.get('joined_at')
                })
        
        return referrals

    async def get_referral_stats(self, user_id: int) -> Dict:
        """Get referral statistics for a user"""
        user = await self.get_user(user_id)
        if not user:
            return {
                'total_referrals': 0,
                'referral_code': None,
                'referral_rewards': 0
            }
        
        referrals = user.get('referrals', [])
        referral_rewards = user.get('referral_rewards', 0)
        
        return {
            'total_referrals': len(referrals),
            'referral_code': user.get('referral_code'),
            'referral_rewards': referral_rewards
        }

    async def add_referral_reward(self, user_id: int, amount: int):
        """Add referral reward to user's tokens"""
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    "tokens": amount,
                    "referral_rewards": amount
                }
            }
        )

    async def get_top_referrers(self, limit: int = 10) -> List[Dict]:
        """Get top referrers by number of referrals"""
        pipeline = [
            {"$match": {"referrals": {"$exists": True, "$ne": []}}},
            {"$addFields": {"referral_count": {"$size": "$referrals"}}},
            {"$sort": {"referral_count": -1}},
            {"$limit": limit},
            {"$project": {
                "user_id": 1,
                "first_name": 1,
                "username": 1,
                "referral_count": 1,
                "referral_rewards": 1
            }}
        ]
        
        top_referrers = []
        async for doc in self.users.aggregate(pipeline):
            top_referrers.append({
                'user_id': doc['user_id'],
                'first_name': doc.get('first_name', 'Unknown'),
                'username': doc.get('username', ''),
                'referral_count': doc['referral_count'],
                'referral_rewards': doc.get('referral_rewards', 0)
            })
        
        return top_referrers

    async def get_all_user_ids(self) -> list:
        """Return a list of all user IDs (for DM broadcast)."""
        cursor = self.users.find({}, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]

    async def get_all_group_ids(self) -> list:
        """Return a list of all group chat IDs (for group broadcast)."""
        cursor = self.chat_settings.find({}, {"chat_id": 1})
        return [doc["chat_id"] async for doc in cursor]

    async def log_user_transaction(self, user_id: int, action_type: str, details: dict):
        """Append a transaction record to the user's transaction_history array."""
        record = {
            "type": action_type,
            "timestamp": datetime.now(),
            "details": details
        }
        await self.users.update_one(
            {"user_id": user_id},
            {"$push": {"transaction_history": {"$each": [record], "$position": 0, "$slice": 50}}}
        )

async def ensure_database():
    global _db_initialized
    if not _db_initialized:
        await init_database()
        _db_initialized = True