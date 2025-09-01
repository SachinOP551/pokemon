"""
Media Utilities for Pyrogram Client
Wrapper functions for sending media with proper session management
"""

import asyncio
import time
import random
from typing import Optional, Union
from pyrogram import Client
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from .session_manager import get_unique_id, mark_id_used

async def send_photo_safe(
    client: Client,
    chat_id: Union[int, str],
    photo: Union[str, bytes],
    caption: Optional[str] = None,
    **kwargs
) -> Optional[Message]:
    """
    Safely send a photo with proper session management and retry logic
    """
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            # Generate unique ID for this message
            unique_id = get_unique_id()
            
            # Add random ID to kwargs
            kwargs['random_id'] = unique_id
            
            # Send the photo
            message = await client.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                **kwargs
            )
            
            # Mark the ID as used
            if message and message.id:
                mark_id_used(message.id)
            
            return message
            
        except Exception as e:
            error_msg = str(e).lower()
            if "random_id_duplicate" in error_msg or "duplicate" in error_msg:
                print(f"⚠️  RANDOM_ID_DUPLICATE error on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"⏳ Waiting {delay:.2f}s before retry...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print("❌ Max retries reached for photo send")
                    return None
            else:
                print(f"❌ Error sending photo: {e}")
                return None
    
    return None

async def send_video_safe(
    client: Client,
    chat_id: Union[int, str],
    video: Union[str, bytes],
    caption: Optional[str] = None,
    **kwargs
) -> Optional[Message]:
    """
    Safely send a video with proper session management and retry logic
    """
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            # Generate unique ID for this message
            unique_id = get_unique_id()
            
            # Add random ID to kwargs
            kwargs['random_id'] = unique_id
            
            # Send the video
            message = await client.send_video(
                chat_id=chat_id,
                video=video,
                caption=caption,
                **kwargs
            )
            
            # Mark the ID as used
            if message and message.id:
                mark_id_used(message.id)
            
            return message
            
        except Exception as e:
            error_msg = str(e).lower()
            if "random_id_duplicate" in error_msg or "duplicate" in error_msg:
                print(f"⚠️  RANDOM_ID_DUPLICATE error on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"⏳ Waiting {delay:.2f}s before retry...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print("❌ Max retries reached for video send")
                    return None
            else:
                print(f"❌ Error sending video: {e}")
                return None
    
    return None

async def send_media_group_safe(
    client: Client,
    chat_id: Union[int, str],
    media: list,
    **kwargs
) -> Optional[list[Message]]:
    """
    Safely send a media group with proper session management and retry logic
    """
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            # Generate unique ID for this message group
            unique_id = get_unique_id()
            
            # Add random ID to kwargs
            kwargs['random_id'] = unique_id
            
            # Send the media group
            messages = await client.send_media_group(
                chat_id=chat_id,
                media=media,
                **kwargs
            )
            
            # Mark the IDs as used
            if messages:
                for message in messages:
                    if message and message.id:
                        mark_id_used(message.id)
            
            return messages
            
        except Exception as e:
            error_msg = str(e).lower()
            if "random_id_duplicate" in error_msg or "duplicate" in error_msg:
                print(f"⚠️  RANDOM_ID_DUPLICATE error on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"⏳ Waiting {delay:.2f}s before retry...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print("❌ Max retries reached for media group send")
                    return None
            else:
                print(f"❌ Error sending media group: {e}")
                return None
    
    return None

def add_delay_between_media():
    """
    Add a small delay between media sends to prevent rate limiting
    """
    time.sleep(0.1)  # 100ms delay 