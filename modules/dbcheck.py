import time
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display

async def check_db():
    # Use the single MongoDB client instance
    client = get_mongo_client()
    db = client.marvel
    
    start = time.time()
    await db.command("ping")
    print("DB response:", time.time() - start, "seconds")
    # Don't close the client as it's shared
    print("DB check completed - client remains open for other operations")

asyncio.get_event_loop().run_until_complete(check_db())








