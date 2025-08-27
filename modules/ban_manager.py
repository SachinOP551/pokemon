from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import asyncio
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class BanManager:
    """Manages both temporary and permanent bans"""
    
    def __init__(self):
        # In-memory storage for temporary bans
        # Structure: {user_id: (ban_end_time, ban_reason)}
        self.temporary_bans: Dict[int, Tuple[datetime, str]] = {}
        self.ban_reasons: Dict[int, str] = {}
        self._cleanup_task = None
        
        # Don't start cleanup task here - will be started when needed
    
    def add_temporary_ban(self, user_id: int, duration_minutes: int = 10, reason: str = "Spam detected"):
        """Add a temporary ban to memory"""
        ban_end_time = datetime.now() + timedelta(minutes=duration_minutes)
        self.temporary_bans[user_id] = (ban_end_time, reason)
        self.ban_reasons[user_id] = reason
        logger.info(f"Temporary ban added for user {user_id} until {ban_end_time}")
    
    def remove_temporary_ban(self, user_id: int):
        """Remove a temporary ban from memory"""
        if user_id in self.temporary_bans:
            del self.temporary_bans[user_id]
        if user_id in self.ban_reasons:
            del self.ban_reasons[user_id]
        logger.info(f"Temporary ban removed for user {user_id}")
    
    def is_temporarily_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Check if user is temporarily banned and return ban reason if applicable"""
        if user_id not in self.temporary_bans:
            return False, None
        
        ban_end_time, reason = self.temporary_bans[user_id]
        current_time = datetime.now()
        
        if current_time < ban_end_time:
            return True, reason
        else:
            # Ban expired, remove it immediately
            self.remove_temporary_ban(user_id)
            return False, None
    
    def get_ban_info(self, user_id: int) -> Optional[Dict]:
        """Get ban information for a user"""
        # First check if ban is still valid
        is_temp_banned, temp_reason = self.is_temporarily_banned(user_id)
        
        if is_temp_banned:
            ban_end_time, _ = self.temporary_bans[user_id]
            current_time = datetime.now()
            remaining_minutes = (ban_end_time - current_time).total_seconds() / 60
            
            # Ensure remaining_minutes is not negative
            if remaining_minutes < 0:
                remaining_minutes = 0
                # Ban has expired, remove it
                self.remove_temporary_ban(user_id)
                return None
            
            return {
                'type': 'temporary',
                'reason': temp_reason,
                'end_time': ban_end_time,
                'remaining_minutes': remaining_minutes
            }
        
        return None
    
    def get_all_temporary_bans(self) -> Dict[int, Dict]:
        """Get all active temporary bans"""
        current_time = datetime.now()
        active_bans = {}
        
        for user_id, (ban_end_time, reason) in self.temporary_bans.items():
            if current_time < ban_end_time:
                active_bans[user_id] = {
                    'end_time': ban_end_time,
                    'reason': reason,
                    'remaining_minutes': int((ban_end_time - current_time).total_seconds() / 60)
                }
        
        return active_bans
    
    def force_cleanup_expired_bans(self):
        """Force cleanup all expired bans immediately"""
        current_time = datetime.now()
        expired_users = []
        
        for user_id, (ban_end_time, _) in self.temporary_bans.items():
            if current_time >= ban_end_time:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            self.remove_temporary_ban(user_id)
        
        if expired_users:
            logger.info(f"Force cleaned up {len(expired_users)} expired temporary bans")
        
        return len(expired_users)
    
    async def _cleanup_expired_bans(self):
        """Periodically clean up expired temporary bans"""
        while True:
            try:
                current_time = datetime.now()
                expired_users = []
                
                for user_id, (ban_end_time, _) in self.temporary_bans.items():
                    if current_time >= ban_end_time:
                        expired_users.append(user_id)
                
                for user_id in expired_users:
                    self.remove_temporary_ban(user_id)
                
                if expired_users:
                    logger.info(f"Cleaned up {len(expired_users)} expired temporary bans")
                
                # Run cleanup every 30 seconds for more responsive unbanning
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in ban cleanup: {e}")
                await asyncio.sleep(30)  # Wait 30 seconds before retrying

# Global ban manager instance
ban_manager = BanManager()

def start_ban_manager():
    """Start the ban manager cleanup task when there's a running event loop"""
    try:
        if ban_manager._cleanup_task is None:
            ban_manager._cleanup_task = asyncio.create_task(ban_manager._cleanup_expired_bans())
            logger.info("Ban manager cleanup task started")
    except Exception as e:
        logger.error(f"Failed to start ban manager cleanup task: {e}")

async def check_user_ban_status(user_id: int, db) -> Tuple[bool, Optional[str]]:
    """
    Check if a user is banned (temporary or permanent)
    Returns: (is_banned, ban_reason)
    """
    # Check temporary ban first (this will automatically clean up expired bans)
    is_temp_banned, temp_reason = ban_manager.is_temporarily_banned(user_id)
    if is_temp_banned:
        return True, temp_reason
    
    # Check permanent ban in database
    try:
        is_permanent_banned = await db.is_banned(user_id)
        if is_permanent_banned:
            return True, "Permanently banned"
    except Exception as e:
        logger.error(f"Error checking permanent ban for user {user_id}: {e}")
    
    return False, None

async def ban_user(user_id: int, db, permanent: bool = False, duration_minutes: int = 10, reason: str = "Spam detected"):
    """
    Ban a user - temporary (in memory) or permanent (in database)
    """
    try:
        if permanent:
            # Permanent ban - store in database
            success = await db.ban_user(user_id, permanent=True)
            if success:
                logger.info(f"Permanent ban added for user {user_id}: {reason}")
                return True
        else:
            # Temporary ban - store in memory
            ban_manager.add_temporary_ban(user_id, duration_minutes, reason)
            # Also log in database for tracking
            await db.ban_user(user_id, permanent=False, duration_minutes=duration_minutes)
            return True
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {e}")
        return False

async def unban_user(user_id: int, db):
    """
    Unban a user from both temporary and permanent bans
    """
    try:
        # Remove temporary ban if exists
        ban_manager.remove_temporary_ban(user_id)
        
        # Check if user exists in database first
        user_data = await db.get_user(user_id)
        if not user_data:
            logger.warning(f"User {user_id} not found in database during unban")
            return False
        
        # Remove permanent ban from database
        success = await db.unban_user(user_id)
        
        if success:
            logger.info(f"User {user_id} unbanned successfully")
            return True
        return False
    except Exception as e:
        logger.error(f"Error unbanning user {user_id}: {e}")
        return False

def get_ban_info(user_id: int) -> Optional[Dict]:
    """Get ban information for a user (temporary bans only)"""
    return ban_manager.get_ban_info(user_id)

def get_all_temporary_bans() -> Dict[int, Dict]:
    """Get all active temporary bans"""
    return ban_manager.get_all_temporary_bans()

def force_cleanup_all_expired_bans() -> int:
    """Force cleanup all expired temporary bans immediately"""
    return ban_manager.force_cleanup_expired_bans()

async def get_comprehensive_ban_info(user_id: int, db) -> Optional[Dict]:
    """Get comprehensive ban information for a user (both temporary and permanent)"""
    # Check temporary ban
    temp_ban_info = ban_manager.get_ban_info(user_id)
    if temp_ban_info:
        return temp_ban_info
    
    # Check permanent ban
    try:
        is_permanent_banned = await db.is_banned(user_id)
        if is_permanent_banned:
            return {
                'type': 'permanent',
                'reason': 'Permanently banned',
                'end_time': None,
                'remaining_minutes': None
            }
    except Exception as e:
        logger.error(f"Error checking permanent ban for user {user_id}: {e}")
    
    return None 