
import asyncio
from datetime import datetime
from postgres_database import init_database, get_database

# MongoDB and PostgreSQL connection strings
POSTGRES_URI = "postgresql://neondb_owner:npg_vyeSFHK7r3Eq@ep-snowy-sky-a1hx5dig-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
MONGO_URI = "mongodb+srv://vegetakun447:r4SIiJ1OOhRNLknD@cluster0.z4bsdym.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"  # Update to your actual MongoDB URI
MONGO_DB = "superhero_collector"                # Update to your actual database name
MONGO_COLLECTION = "users"               # Update to your actual collection name

from motor.motor_asyncio import AsyncIOMotorClient

async def migrate_collection_history():
    await init_database(POSTGRES_URI)
    db = get_database()

    mongo_client = AsyncIOMotorClient(MONGO_URI)
    mongo_db = mongo_client[MONGO_DB]
    users_collection = mongo_db[MONGO_COLLECTION]

    cursor = users_collection.find({}, {"user_id": 1, "collection_history": 1})
    async for user in cursor:
        user_id = user.get("user_id")
        collection_history = user.get("collection_history", [])
        if collection_history is None:
            collection_history = []
        # Recursively convert all datetime objects to ISO strings
        def convert_datetimes(obj):
            if isinstance(obj, dict):
                return {k: convert_datetimes(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetimes(v) for v in obj]
            elif isinstance(obj, datetime):
                return obj.isoformat()
            else:
                return obj
        collection_history_clean = convert_datetimes(collection_history)
        import json
        # Update in PostgreSQL
        await db.update_user(user_id, {"collection_history": json.dumps(collection_history_clean)})
        print(f"Migrated user {user_id}")

    mongo_client.close()

if __name__ == "__main__":
    asyncio.run(migrate_collection_history())