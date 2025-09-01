import asyncpg
import json
from datetime import datetime
NEON_URI = "postgresql://neondb_owner:npg_vyeSFHK7r3Eq@ep-snowy-sky-a1hx5dig-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

TABLE_NAME = "daily_store"

async def ensure_daily_store_table():
    conn = await asyncpg.connect(NEON_URI)
    await conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            store_date DATE UNIQUE NOT NULL,
            offer JSONB NOT NULL
        )
    ''')
    await conn.close()

async def get_today_store():
    today = datetime.utcnow().date()
    conn = await asyncpg.connect(NEON_URI)
    row = await conn.fetchrow(f"SELECT offer FROM {TABLE_NAME} WHERE store_date = $1", today)
    await conn.close()
    if row:
        return row["offer"]
    return None

async def set_today_store(offer):
    today = datetime.utcnow().date()
    conn = await asyncpg.connect(NEON_URI)
    await conn.execute(f'''
        INSERT INTO {TABLE_NAME} (store_date, offer)
        VALUES ($1, $2)
        ON CONFLICT (store_date) DO UPDATE SET offer = EXCLUDED.offer
    ''', today, json.dumps(offer))
    await conn.close()
