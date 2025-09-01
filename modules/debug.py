import asyncio
import time
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display

MONGO_URI = "mongodb+srv://vegetakun447:Swami447@cluster0.hcngy.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "marvel"

async def check_db():
    # Use the single MongoDB client instance
    client = get_mongo_client()
    db = client[DB_NAME]

    print("=== MongoDB Latency Debugger ===")

    # 1. Ping Test
    start = time.time()
    await db.command("ping")
    print(f"[Ping] Response time: {time.time() - start:.3f} sec")

    # 2. Test Query Time on 'users'
    try:
        start = time.time()
        doc = await db.users.find_one({}, {"_id": 1})
        print(f"[Test Query - users] Time: {time.time() - start:.3f} sec | Found: {bool(doc)}")
    except Exception as e:
        print(f"[Test Query - users] Error: {e}")

    # 3. Count documents (may be slow on big collections)
    start = time.time()
    count = await db.users.estimated_document_count()
    print(f"[Count users] Time: {time.time() - start:.3f} sec | Total: {count}")

    # 4. Check Indexes
    indexes = await db.users.index_information()
    print(f"[Indexes on users]: {list(indexes.keys())}")

    # 5. Check active connections
    try:
        server_status = await db.command("serverStatus")
        print(f"[Connections] Current: {server_status['connections']['current']} / Available: {server_status['connections']['available']}")
    except Exception:
        print("[Connections] Could not fetch (limited permissions on shared tiers).")

    # Don't close the client as it's shared
    print("Debug completed - client remains open for other operations")

asyncio.run(check_db())
