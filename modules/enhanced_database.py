#!/usr/bin/env python3
"""
Enhanced Database Module for MarvelX Bot
Optimized for performance with advanced caching and connection pooling.
"""

import asyncio
import logging
import time
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URI, DATABASE_NAME
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import random
from functools import lru_cache
from cachetools import TTLCache, LRUCache
import json
import gc

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enhanced connection pool settings
ENHANCED_POOL_SETTINGS = {
    'maxPoolSize': 150,  # Increased for better performance
    'minPoolSize': 30,   # Increased minimum pool
    'maxIdleTimeMS': 60000,  # Increased idle time
    'waitQueueTimeoutMS': 10000,  # Increased timeout
    'maxConnecting': 30,  # Increased max connecting
    'serverSelectionTimeoutMS': 10000,  # Increased selection timeout
    'connectTimeoutMS': 15000,  # Increased connect timeout
    'socketTimeoutMS': 45000,  # Increased socket timeout
    'heartbeatFrequencyMS': 10000,  # Heartbeat frequency
    'retryWrites': True,
    'retryReads': True
}

# Enhanced caching system
ENHANCED_CHARACTER_CACHE = TTLCache(maxsize=3000, ttl=7200)  # 2 hours TTL, larger cache
ENHANCED_USER_COLLECTION_CACHE = TTLCache(maxsize=1500, ttl=3600)  # 1 hour TTL
ENHANCED_DROP_SETTINGS_CACHE = TTLCache(maxsize=50, ttl=7200)  # 2 hours TTL
ENHANCED_USER_STATS_CACHE = TTLCache(maxsize=1000, ttl=1800)  # 30 minutes TTL
ENHANCED_LEADERBOARD_CACHE = TTLCache(maxsize=20, ttl=600)  # 10 minutes TTL
ENHANCED_CHAT_SETTINGS_CACHE = TTLCache(maxsize=200, ttl=3600)  # 1 hour TTL

# Global database instance
_enhanced_db_instance = None
_enhanced_db_initialized = False

class EnhancedDatabase:
    def __init__(self):
        """Initialize enhanced database connection with optimized settings"""
        self.client = AsyncIOMotorClient(MONGODB_URI, **ENHANCED_POOL_SETTINGS)
        self.db = self.client[DATABASE_NAME]
        
        # Collection references
        self.users = self.db.users
        self.characters = self.db.characters
        self.chat_settings = self.db.chat_settings
        self.claim_settings = self.db.claim_settings
        self.propose_settings = self.db.propose_settings
        self.redeem_codes = self.db.redeem_codes
        self.drop_settings = self.db.drop_settings
        
        # Performance tracking
        self.query_stats = {
            'total_queries': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'slow_queries': [],
            'last_cleanup': time.time()
        }
        
        # Batch operation queue for better performance
        self.batch_queue = []
        self.batch_size = 200  # Increased batch size
        self.batch_timeout = 10  # Increased timeout
        
        # Start background tasks
        asyncio.create_task(self._batch_processor())
        asyncio.create_task(self._cache_cleanup())
        asyncio.create_task(self._performance_monitor())
        
        logger.info("Enhanced database initialized with optimized settings")
    
    async def _batch_processor(self):
        """Process batched operations for better performance"""
        while True:
            try:
                if self.batch_queue:
                    # Process batch operations
                    batch_ops = self.batch_queue[:self.batch_size]
                    self.batch_queue = self.batch_queue[self.batch_size:]
                    
                    # Group operations by type
                    user_updates = []
                    character_updates = []
                    collection_updates = []
                    
                    for op in batch_ops:
                        if op['type'] == 'user_update':
                            user_updates.append(op['data'])
                        elif op['type'] == 'character_update':
                            character_updates.append(op['data'])
                        elif op['type'] == 'collection_update':
                            collection_updates.append(op['data'])
                    
                    # Execute batch operations
                    if user_updates:
                        await self._execute_user_batch(user_updates)
                    if character_updates:
                        await self._execute_character_batch(character_updates)
                    if collection_updates:
                        await self._execute_collection_batch(collection_updates)
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(5)
    
    async def _execute_user_batch(self, updates):
        """Execute batch user updates"""
        try:
            bulk_ops = []
            for update in updates:
                bulk_ops.append({
                    'updateOne': {
                        'filter': {'user_id': update['user_id']},
                        'update': {'$set': update['data']},
                        'upsert': True
                    }
                })
            
            if bulk_ops:
                await self.users.bulk_write(bulk_ops, ordered=False)
                logger.info(f"Executed {len(bulk_ops)} user batch operations")
                
        except Exception as e:
            logger.error(f"Error executing user batch: {e}")
    
    async def _execute_character_batch(self, updates):
        """Execute batch character updates"""
        try:
            bulk_ops = []
            for update in updates:
                bulk_ops.append({
                    'updateOne': {
                        'filter': {'character_id': update['character_id']},
                        'update': {'$set': update['data']},
                        'upsert': True
                    }
                })
            
            if bulk_ops:
                await self.characters.bulk_write(bulk_ops, ordered=False)
                logger.info(f"Executed {len(bulk_ops)} character batch operations")
                
        except Exception as e:
            logger.error(f"Error executing character batch: {e}")
    
    async def _execute_collection_batch(self, updates):
        """Execute batch collection updates"""
        try:
            bulk_ops = []
            for update in updates:
                if update['operation'] == 'add':
                    bulk_ops.append({
                        'updateOne': {
                            'filter': {'user_id': update['user_id']},
                            'update': {'$addToSet': {'characters': update['character_id']}},
                            'upsert': True
                        }
                    })
                elif update['operation'] == 'remove':
                    bulk_ops.append({
                        'updateOne': {
                            'filter': {'user_id': update['user_id']},
                            'update': {'$pull': {'characters': update['character_id']}}
                        }
                    })
            
            if bulk_ops:
                await self.users.bulk_write(bulk_ops, ordered=False)
                logger.info(f"Executed {len(bulk_ops)} collection batch operations")
                
        except Exception as e:
            logger.error(f"Error executing collection batch: {e}")
    
    async def _cache_cleanup(self):
        """Periodic cache cleanup to prevent memory leaks"""
        while True:
            try:
                # Clean up expired cache entries
                current_time = time.time()
                
                # Clear expired entries from all caches
                for cache_name, cache in [
                    ('character', ENHANCED_CHARACTER_CACHE),
                    ('user_collection', ENHANCED_USER_COLLECTION_CACHE),
                    ('drop_settings', ENHANCED_DROP_SETTINGS_CACHE),
                    ('user_stats', ENHANCED_USER_STATS_CACHE),
                    ('leaderboard', ENHANCED_LEADERBOARD_CACHE),
                    ('chat_settings', ENHANCED_CHAT_SETTINGS_CACHE)
                ]:
                    # TTLCache handles expiration automatically
                    # Just log cache size for monitoring
                    if len(cache) > 0:
                        logger.debug(f"{cache_name} cache size: {len(cache)}")
                
                # Force garbage collection every hour
                if current_time - self.query_stats['last_cleanup'] > 3600:
                    collected = gc.collect()
                    if collected > 0:
                        logger.info(f"Garbage collection freed {collected} objects")
                    self.query_stats['last_cleanup'] = current_time
                
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
                await asyncio.sleep(60)
    
    async def _performance_monitor(self):
        """Monitor database performance"""
        while True:
            try:
                # Get database statistics
                db_stats = await self.db.command("dbStats")
                
                # Check for performance issues
                if db_stats.get('connections', {}).get('current', 0) > 100:
                    logger.warning("High database connection count detected")
                
                # Log performance metrics
                logger.info(f"Database stats - Queries: {self.query_stats['total_queries']}, "
                          f"Cache hits: {self.query_stats['cache_hits']}, "
                          f"Cache misses: {self.query_stats['cache_misses']}")
                
                # Reset counters every hour
                if time.time() - self.query_stats.get('last_reset', 0) > 3600:
                    self.query_stats['total_queries'] = 0
                    self.query_stats['cache_hits'] = 0
                    self.query_stats['cache_misses'] = 0
                    self.query_stats['last_reset'] = time.time()
                
                await asyncio.sleep(600)  # Monitor every 10 minutes
                
            except Exception as e:
                logger.error(f"Error in performance monitor: {e}")
                await asyncio.sleep(60)
    
    async def get_character(self, char_id: int) -> Optional[Dict]:
        """Get character with enhanced caching"""
        try:
            self.query_stats['total_queries'] += 1
            
            # Check cache first
            if char_id in ENHANCED_CHARACTER_CACHE:
                self.query_stats['cache_hits'] += 1
                return ENHANCED_CHARACTER_CACHE[char_id]
            
            self.query_stats['cache_misses'] += 1
            
            # Query database
            character = await self.characters.find_one({"character_id": char_id})
            
            if character:
                # Cache the result
                ENHANCED_CHARACTER_CACHE[char_id] = character
                return character
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting character {char_id}: {e}")
            return None
    
    async def get_user_collection(self, user_id: int) -> List[Dict]:
        """Get user collection with enhanced caching"""
        try:
            self.query_stats['total_queries'] += 1
            
            cache_key = f"collection:{user_id}"
            
            # Check cache first
            if cache_key in ENHANCED_USER_COLLECTION_CACHE:
                self.query_stats['cache_hits'] += 1
                return ENHANCED_USER_COLLECTION_CACHE[cache_key]
            
            self.query_stats['cache_misses'] += 1
            
            # Query database
            user = await self.users.find_one({"user_id": user_id})
            
            if user and 'characters' in user:
                # Get character details
                character_ids = user['characters']
                characters = []
                
                # Batch query characters
                if character_ids:
                    cursor = self.characters.find({"character_id": {"$in": character_ids}})
                    characters = await cursor.to_list(None)
                
                # Cache the result
                ENHANCED_USER_COLLECTION_CACHE[cache_key] = characters
                return characters
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting user collection {user_id}: {e}")
            return []
    
    async def add_character_to_user(self, user_id: int, character_id: int, collected_at: datetime = None, source: str = 'collected'):
        """Add character to user with batch processing"""
        try:
            # Add to batch queue for better performance
            self.batch_queue.append({
                'type': 'collection_update',
                'data': {
                    'user_id': user_id,
                    'character_id': character_id,
                    'operation': 'add'
                }
            })
            
            # Invalidate cache
            cache_key = f"collection:{user_id}"
            if cache_key in ENHANCED_USER_COLLECTION_CACHE:
                del ENHANCED_USER_COLLECTION_CACHE[cache_key]
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding character {character_id} to user {user_id}: {e}")
            return False
    
    async def remove_character_from_user(self, user_id: int, character_id: int):
        """Remove character from user with batch processing"""
        try:
            # Add to batch queue for better performance
            self.batch_queue.append({
                'type': 'collection_update',
                'data': {
                    'user_id': user_id,
                    'character_id': character_id,
                    'operation': 'remove'
                }
            })
            
            # Invalidate cache
            cache_key = f"collection:{user_id}"
            if cache_key in ENHANCED_USER_COLLECTION_CACHE:
                del ENHANCED_USER_COLLECTION_CACHE[cache_key]
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing character {character_id} from user {user_id}: {e}")
            return False
    
    async def get_random_character(self, locked_rarities=None):
        """Get random character with enhanced caching"""
        try:
            self.query_stats['total_queries'] += 1
            
            # Build query
            query = {}
            if locked_rarities:
                query["rarity"] = {"$nin": locked_rarities}
            
            # Use aggregation for better performance
            pipeline = [
                {"$match": query},
                {"$sample": {"size": 1}}
            ]
            
            cursor = self.characters.aggregate(pipeline)
            characters = await cursor.to_list(1)
            
            if characters:
                character = characters[0]
                # Cache the character
                ENHANCED_CHARACTER_CACHE[character['character_id']] = character
                return character
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting random character: {e}")
            return None
    
    async def get_drop_settings(self):
        """Get drop settings with enhanced caching"""
        try:
            self.query_stats['total_queries'] += 1
            
            # Check cache first
            if 'drop_settings' in ENHANCED_DROP_SETTINGS_CACHE:
                self.query_stats['cache_hits'] += 1
                return ENHANCED_DROP_SETTINGS_CACHE['drop_settings']
            
            self.query_stats['cache_misses'] += 1
            
            # Query database
            settings = await self.drop_settings.find_one({})
            
            if settings:
                # Cache the result
                ENHANCED_DROP_SETTINGS_CACHE['drop_settings'] = settings
                return settings
            
            # Return default settings if none found
            default_settings = {
                "drop_interval": 300,  # 5 minutes
                "drop_duration": 60,   # 1 minute
                "locked_rarities": [],
                "daily_limits": {},
                "frequency": "normal"
            }
            
            ENHANCED_DROP_SETTINGS_CACHE['drop_settings'] = default_settings
            return default_settings
            
        except Exception as e:
            logger.error(f"Error getting drop settings: {e}")
            return None
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user stats with enhanced caching"""
        try:
            self.query_stats['total_queries'] += 1
            
            # Check cache first
            if user_id in ENHANCED_USER_STATS_CACHE:
                self.query_stats['cache_hits'] += 1
                return ENHANCED_USER_STATS_CACHE[user_id]
            
            self.query_stats['cache_misses'] += 1
            
            # Query database
            user = await self.users.find_one({"user_id": user_id})
            
            if user:
                # Calculate stats
                stats = {
                    'user_id': user_id,
                    'collection_size': len(user.get('characters', [])),
                    'wallet': user.get('wallet', 0),
                    'shards': user.get('shards', 0),
                    'is_banned': user.get('is_banned', False),
                    'is_sudo': user.get('is_sudo', False),
                    'is_og': user.get('is_og', False),
                    'joined_at': user.get('joined_at'),
                    'last_active': user.get('last_active')
                }
                
                # Cache the result
                ENHANCED_USER_STATS_CACHE[user_id] = stats
                return stats
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting user stats {user_id}: {e}")
            return {}
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get database performance statistics"""
        try:
            db_stats = await self.db.command("dbStats")
            
            return {
                'timestamp': datetime.now().isoformat(),
                'query_stats': self.query_stats,
                'cache_sizes': {
                    'character_cache': len(ENHANCED_CHARACTER_CACHE),
                    'user_collection_cache': len(ENHANCED_USER_COLLECTION_CACHE),
                    'drop_settings_cache': len(ENHANCED_DROP_SETTINGS_CACHE),
                    'user_stats_cache': len(ENHANCED_USER_STATS_CACHE),
                    'leaderboard_cache': len(ENHANCED_LEADERBOARD_CACHE),
                    'chat_settings_cache': len(ENHANCED_CHAT_SETTINGS_CACHE)
                },
                'database_stats': {
                    'collections': db_stats.get('collections', 0),
                    'data_size_mb': db_stats.get('dataSize', 0) / 1024 / 1024,
                    'storage_size_mb': db_stats.get('storageSize', 0) / 1024 / 1024,
                    'index_size_mb': db_stats.get('indexSize', 0) / 1024 / 1024,
                    'connections': db_stats.get('connections', {}).get('current', 0)
                },
                'batch_queue_size': len(self.batch_queue)
            }
            
        except Exception as e:
            logger.error(f"Error getting performance stats: {e}")
            return {'error': str(e)}
    
    async def close(self):
        """Close the enhanced database connection"""
        try:
            # Process remaining batch operations
            if self.batch_queue:
                logger.info(f"Processing {len(self.batch_queue)} remaining batch operations")
                await self._batch_processor()
            
            # Close client
            await self.client.close()
            logger.info("Enhanced database connection closed")
            
        except Exception as e:
            logger.error(f"Error closing enhanced database: {e}")

# Global enhanced database instance
_enhanced_db_instance = None

async def init_enhanced_database():
    """Initialize the enhanced database connection"""
    global _enhanced_db_instance
    if _enhanced_db_instance is None:
        _enhanced_db_instance = EnhancedDatabase()
        logger.info("Enhanced database initialized successfully")
    return _enhanced_db_instance

def get_enhanced_database():
    """Get the enhanced database instance"""
    global _enhanced_db_instance
    if _enhanced_db_instance is None:
        raise RuntimeError("Enhanced database not initialized. Call init_enhanced_database() first.")
    return _enhanced_db_instance

# Cache invalidation functions
def invalidate_character_cache(char_id: int):
    """Invalidate character cache"""
    if char_id in ENHANCED_CHARACTER_CACHE:
        del ENHANCED_CHARACTER_CACHE[char_id]

def invalidate_user_collection_cache(user_id: int):
    """Invalidate user collection cache"""
    cache_key = f"collection:{user_id}"
    if cache_key in ENHANCED_USER_COLLECTION_CACHE:
        del ENHANCED_USER_COLLECTION_CACHE[cache_key]

def invalidate_drop_settings_cache():
    """Invalidate drop settings cache"""
    if 'drop_settings' in ENHANCED_DROP_SETTINGS_CACHE:
        del ENHANCED_DROP_SETTINGS_CACHE['drop_settings']

def invalidate_user_stats_cache(user_id: int):
    """Invalidate user stats cache"""
    if user_id in ENHANCED_USER_STATS_CACHE:
        del ENHANCED_USER_STATS_CACHE[user_id]

def clear_all_caches():
    """Clear all caches"""
    ENHANCED_CHARACTER_CACHE.clear()
    ENHANCED_USER_COLLECTION_CACHE.clear()
    ENHANCED_DROP_SETTINGS_CACHE.clear()
    ENHANCED_USER_STATS_CACHE.clear()
    ENHANCED_LEADERBOARD_CACHE.clear()
    ENHANCED_CHAT_SETTINGS_CACHE.clear()
    logger.info("All caches cleared") 