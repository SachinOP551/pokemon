"""
Session Manager for Pyrogram Client
Handles random ID generation and prevents duplicates
"""

from collections import deque
import random
import threading
import time
from typing import Set

class SessionManager:
    """Manages session state and prevents duplicate random IDs"""
    
    def __init__(self):
        self._used_ids: Set[int] = set()
        self._id_lock = threading.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 3600  # Clean up every hour
        
    def generate_unique_id(self) -> int:
        """Generate a unique random ID for Telegram messages"""
        with self._id_lock:
            # Clean up old IDs periodically
            current_time = time.time()
            if current_time - self._last_cleanup > self._cleanup_interval:
                self._used_ids.clear()
                self._last_cleanup = current_time
            
            # Generate a unique ID
            while True:
                # Generate a random 64-bit integer
                random_id = random.randint(-9223372036854775808, 9223372036854775807)
                
                # Check if it's unique
                if random_id not in self._used_ids:
                    self._used_ids.add(random_id)
                    return random_id
    
    def mark_id_used(self, message_id: int):
        """Mark a message ID as used"""
        with self._id_lock:
            self._used_ids.add(message_id)
    
    def cleanup_old_ids(self):
        """Clean up old IDs to prevent memory leaks"""
        with self._id_lock:
            self._used_ids.clear()
            self._last_cleanup = time.time()

# Global session manager instance
session_manager = SessionManager()

def get_unique_id() -> int:
    """Get a unique random ID for Telegram messages"""
    return session_manager.generate_unique_id()

def mark_id_used(message_id: int):
    """Mark a message ID as used"""
    session_manager.mark_id_used(message_id)

def cleanup_session():
    """Clean up session data"""
    session_manager.cleanup_old_ids() 