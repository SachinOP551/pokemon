import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from collections import defaultdict
import time
import functools
from telegram import Update

class RateLimiter:
    def __init__(self, max_requests: int = 30, time_window: int = 60):
        self.max_requests = max_requests  # Maximum requests per time window
        self.time_window = time_window    # Time window in seconds
        self.requests: Dict[int, List[float]] = defaultdict(list)  # User ID -> List of request timestamps
        self.locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)  # User ID -> Lock
        self.queue: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)  # User ID -> Request queue
        
    async def acquire(self, user_id: int) -> bool:
        """Acquire permission to make a request"""
        async with self.locks[user_id]:
            now = time.time()
            
            # Clean up old requests
            self.requests[user_id] = [ts for ts in self.requests[user_id] 
                                    if now - ts < self.time_window]
            
            # Check if user has exceeded rate limit
            if len(self.requests[user_id]) >= self.max_requests:
                # Add request to queue
                await self.queue[user_id].put(now)
                return False
            
            # Add new request timestamp
            self.requests[user_id].append(now)
            return True
    
    async def wait_for_slot(self, user_id: int) -> None:
        """Wait for a slot to become available"""
        while True:
            if await self.acquire(user_id):
                break
            await asyncio.sleep(1)  # Wait before trying again
    
    def get_wait_time(self, user_id: int) -> float:
        """Get estimated wait time for user"""
        now = time.time()
        if len(self.requests[user_id]) < self.max_requests:
            return 0
        
        oldest_request = min(self.requests[user_id])
        return max(0, oldest_request + self.time_window - now)

class RequestQueue:
    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.processing = False
        
    async def add_request(self, request):
        """Add request to queue"""
        await self.queue.put(request)
        
    async def process_requests(self, handler):
        """Process requests in queue"""
        if self.processing:
            return
            
        self.processing = True
        try:
            while True:
                request = await self.queue.get()
                try:
                    await handler(request)
                except Exception as e:
                    logging.error(f"Error processing request: {e}")
                finally:
                    self.queue.task_done()
        finally:
            self.processing = False

class MediaProcessor:
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limiter = RateLimiter(max_requests=20, time_window=60)  # 20 requests per minute
        
    async def process_media(self, media_data):
        """Process media with rate limiting and concurrency control"""
        async with self.semaphore:
            await self.rate_limiter.wait_for_slot(media_data['user_id'])
            try:
                # Process media here
                return await self._process_media_internal(media_data)
            except Exception as e:
                logging.error(f"Error processing media: {e}")
                raise
    
    async def _process_media_internal(self, media_data):
        """Internal media processing logic"""
        # Implement your media processing logic here
        pass

# Global instances
rate_limiter = RateLimiter()
request_queue = RequestQueue()
media_processor = MediaProcessor()

def rate_limited(func):
    """Decorator to rate limit function calls"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Get user_id from args or kwargs
        user_id = None
        if args and isinstance(args[0], Update):
            user_id = args[0].effective_user.id
        elif 'update' in kwargs and isinstance(kwargs['update'], Update):
            user_id = kwargs['update'].effective_user.id
            
        if user_id:
            # Get rate limiter instance
            limiter = RateLimiter()
            # Wait for rate limit
            await limiter.wait_for_slot(user_id)
            
        # Call the original function
        return await func(*args, **kwargs)
    return wrapper 
