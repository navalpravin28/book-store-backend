from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


class MongoDB:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    # tz_aware => every datetime we read back is timezone-aware UTC
    MongoDB.client = AsyncIOMotorClient(
        settings.MONGO_URI,
        tz_aware=True,
        serverSelectionTimeoutMS=5000,
        maxPoolSize=50,
    )
    MongoDB.db = MongoDB.client[settings.MONGO_DB_NAME]
    await create_indexes(MongoDB.db)


async def close_db() -> None:
    if MongoDB.client:
        MongoDB.client.close()


def get_db() -> AsyncIOMotorDatabase:
    return MongoDB.db


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("email", unique=True)

    await db.categories.create_index("slug", unique=True)

    await db.books.create_index("categoryId")
    await db.books.create_index("name")
    await db.books.create_index("createdAt")
    # unique ISBN only when an ISBN is present
    await db.books.create_index(
        "isbn", unique=True, partialFilterExpression={"isbn": {"$type": "string"}}
    )

    await db.sales.create_index([("soldAt", -1)])
    await db.sales.create_index("bookId")
    await db.sales.create_index("buyerMobile")

    await db.advertisements.create_index("ownerId")
    await db.advertisements.create_index("expiresAt")

    await db.revokedTokens.create_index("jti", unique=True)
    # Mongo removes the row once the token would have expired anyway
    await db.revokedTokens.create_index("expiresAt", expireAfterSeconds=0)

    await db.auditLogs.create_index([("createdAt", -1)])
