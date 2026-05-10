import asyncpg
import aiosql
from contextlib import asynccontextmanager

queries = aiosql.from_path("queries", "asyncpg")

pool: asyncpg.Pool | None = None


async def init_pool():
    global pool
    pool = await asyncpg.create_pool(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        database="sync-studio",
        min_size=2,
        max_size=10
    )


async def close_pool():
    await pool.close()


@asynccontextmanager
async def get_conn():
    async with pool.acquire() as conn:
        yield conn
