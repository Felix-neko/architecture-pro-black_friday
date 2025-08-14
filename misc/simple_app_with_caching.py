import logging

# Простое решение - включи DEBUG для aioredis
logging.getLogger("aioredis").setLevel(logging.DEBUG)

# И добавь обработчик в консоль
console = logging.StreamHandler()
console.setFormatter(logging.Formatter("%(name)s: %(message)s"))
logging.getLogger("aioredis").addHandler(console)

# Включаем логирование для всех возможных компонентов кэширования
loggers_to_enable = [
    "aioredis",
    "fastapi_cache", 
    "fastapi-cache",
    "fastapi_cache.backends",
    "fastapi_cache.backends.redis",
    "fastapi_cache.decorator",
    "redis",
    "redis.asyncio"
]

for logger_name in loggers_to_enable:
    logger_obj = logging.getLogger(logger_name)
    logger_obj.setLevel(logging.DEBUG)
    
    # Добавляем консольный обработчик если его нет
    if not logger_obj.handlers:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(f" {logger_name}: %(message)s"))
        logger_obj.addHandler(console)
    
    print(f" Enabled logging for: {logger_name}")

import json
from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.monitoring import CommandListener, CommandStartedEvent, CommandSucceededEvent, CommandFailedEvent
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Pydantic models
class Item(BaseModel):
    id: str
    name: str
    description: str
    value: int


class ItemCreate(BaseModel):
    name: str
    description: str
    value: int


class ItemResponse(BaseModel):
    id: str
    name: str
    description: str
    value: int
    cached: bool = False


# MongoDB Command Logger
class MongoCommandLogger(CommandListener):
    """Logs all MongoDB operations"""

    def started(self, event: CommandStartedEvent):
        logger.info(
            f"MongoDB REQUEST -> Command: {event.command_name}, "
            f"Database: {event.database_name}, "
            f"Request ID: {event.request_id}, "
            f"Command: {json.dumps(event.command, default=str, indent=2)}"
        )

    def succeeded(self, event: CommandSucceededEvent):
        logger.info(
            f"MongoDB RESPONSE <- Command: {event.command_name}, "
            f"Request ID: {event.request_id}, "
            f"Duration: {event.duration_micros/1000:.2f}ms, "
            f"Reply: {json.dumps(event.reply, default=str, indent=2)}"
        )

    def failed(self, event: CommandFailedEvent):
        logger.error(
            f"MongoDB ERROR <- Command: {event.command_name}, "
            f"Request ID: {event.request_id}, "
            f"Duration: {event.duration_micros/1000:.2f}ms, "
            f"Error: {event.failure}"
        )


# Redis Logger Class
class RedisLogger:
    """Custom Redis client wrapper that logs all operations"""

    def __init__(self, redis_client):
        self.redis_client = redis_client

    async def get(self, key: str):
        logger.info(f"Redis REQUEST -> GET {key}")
        try:
            result = await self.redis_client.get(key)
            logger.info(f"Redis RESPONSE <- GET {key}: {result}")
            return result
        except Exception as e:
            logger.error(f"Redis ERROR <- GET {key}: {e}")
            raise

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        logger.info(f"Redis REQUEST -> SET {key} = {value} (expire: {ex})")
        try:
            result = await self.redis_client.set(key, value, ex=ex)
            logger.info(f"Redis RESPONSE <- SET {key}: {result}")
            return result
        except Exception as e:
            logger.error(f"Redis ERROR <- SET {key}: {e}")
            raise

    async def delete(self, *keys):
        logger.info(f"Redis REQUEST -> DELETE {keys}")
        try:
            result = await self.redis_client.delete(*keys)
            logger.info(f"Redis RESPONSE <- DELETE {keys}: {result}")
            return result
        except Exception as e:
            logger.error(f"Redis ERROR <- DELETE {keys}: {e}")
            raise

    async def flushdb(self):
        logger.info("Redis REQUEST -> FLUSHDB")
        try:
            result = await self.redis_client.flushdb()
            logger.info(f"Redis RESPONSE <- FLUSHDB: {result}")
            return result
        except Exception as e:
            logger.error(f"Redis ERROR <- FLUSHDB: {e}")
            raise


# Global variables
mongo_client: AsyncIOMotorClient = None
db = None
redis_logger: RedisLogger = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global mongo_client, db, redis_logger

    # Setup MongoDB with logging
    logger.info("Connecting to MongoDB at localhost:27017...")
    mongo_client = AsyncIOMotorClient("mongodb://localhost:27017", event_listeners=[MongoCommandLogger()])
    db = mongo_client.test_db
    logger.info("MongoDB connection established")

    # Setup Redis with logging
    logger.info("Connecting to Redis at localhost:6379...")
    redis_client = redis.from_url("redis://localhost:6379", encoding="utf8", decode_responses=True)
    redis_logger = RedisLogger(redis_client)

    # Initialize FastAPI Cache
    FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")
    
    # Add Redis command logging by monkey-patching the backend
    backend = FastAPICache.get_backend()
    redis_client = backend.redis
    
    logger.info(f" Redis client type: {type(redis_client)}")
    logger.info(f" Redis client methods: {[method for method in dir(redis_client) if not method.startswith('_')]}")
    
    # Store original methods
    original_methods = {}
    methods_to_patch = ['get', 'set', 'delete', 'exists', 'keys', 'mget', 'hget', 'hset', 'expire', 'ttl']
    
    for method_name in methods_to_patch:
        if hasattr(redis_client, method_name):
            original_methods[method_name] = getattr(redis_client, method_name)
            logger.info(f" Found method: {method_name}")
        else:
            logger.warning(f" Method not found: {method_name}")
    
    # Create universal logging wrapper
    def create_logged_method(method_name, original_method):
        async def logged_method(*args, **kwargs):
            logger.info(f" Redis {method_name.upper()} -> args: {args}, kwargs: {kwargs}")
            try:
                result = await original_method(*args, **kwargs)
                if method_name == 'get' and result is not None:
                    logger.info(f" CACHE HIT! Found cached value for {method_name}")
                elif method_name == 'get' and result is None:
                    logger.info(f" CACHE MISS! No cached value for {method_name}")
                else:
                    logger.info(f" Redis {method_name.upper()} <- result: {result}")
                return result
            except Exception as e:
                logger.error(f" Redis {method_name.upper()} ERROR: {e}")
                raise
        return logged_method
    
    # Apply patches
    for method_name, original_method in original_methods.items():
        logged_method = create_logged_method(method_name, original_method)
        setattr(redis_client, method_name, logged_method)
        logger.info(f" Patched method: {method_name}")
    
    logger.info("Redis connection and FastAPI Cache initialized with aggressive logging")

    yield

    # Shutdown
    if mongo_client:
        mongo_client.close()
        logger.info("MongoDB connection closed")


# Cache key generator
def cache_key_builder(func, *args, **kwargs):
    """Generate cache key for the function"""
    key = f"cache:{func.__name__}:{hash(str(args) + str(kwargs))}"
    logger.info(f" Cache key generated: {key} for {func.__name__} with args: {args}")
    return key


# Custom cache decorator with logging
def logged_cache(expire: int = 300, key_builder=None):
    """Cache decorator with logging"""
    def decorator(func):
        # Apply the original cache decorator
        cached_func = cache(expire=expire, key_builder=key_builder)(func)
        
        async def wrapper(*args, **kwargs):
            cache_key = key_builder(func, *args, **kwargs) if key_builder else f"cache:{func.__name__}:{hash(str(args) + str(kwargs))}"
            full_cache_key = f"fastapi-cache:{cache_key}"
            
            logger.info(f" Cache decorator called for {func.__name__} with key: {cache_key}")
            
            # Check if item is in cache before calling the function
            try:
                redis_client = FastAPICache.get_backend().redis
                cached_value = await redis_client.get(full_cache_key)
                if cached_value is not None:
                    logger.info(f" CACHE HIT! Found cached value for {func.__name__}")
                else:
                    logger.info(f" CACHE MISS! No cached value for {func.__name__}")
            except Exception as e:
                logger.error(f" Error checking cache: {e}")
            
            # Call the cached function
            result = await cached_func(*args, **kwargs)
            return result
        
        return wrapper
    return decorator


app = FastAPI(title="FastAPI with Redis Cache and MongoDB", version="1.0.0", lifespan=lifespan)


@app.get("/items/{item_id}", response_model=ItemResponse)
@logged_cache(expire=300, key_builder=cache_key_builder)  # Use our logged cache decorator
async def read_item(item_id: str) -> ItemResponse:
    """
    Read endpoint - checks cache first, then MongoDB
    """
    logger.info(f" ENDPOINT CALLED: Reading item with ID: {item_id} - This should only appear on cache miss!")

    # This will be cached by fastapi-cache decorator
    # The actual MongoDB query will only happen on cache miss
    result = await db.items.find_one({"_id": item_id})

    if not result:
        logger.warning(f" Item {item_id} not found in MongoDB")
        raise HTTPException(status_code=404, detail="Item not found")

    response = ItemResponse(
        id=result["_id"],
        name=result["name"],
        description=result["description"],
        value=result["value"],
        cached=False,  # This will be True if served from cache
    )

    logger.info(f" Item {item_id} retrieved from MongoDB - Cache miss occurred")
    return response


@app.post("/items", response_model=ItemResponse)
async def create_item(item: ItemCreate) -> ItemResponse:
    """
    Write endpoint - creates item in MongoDB and invalidates related cache
    """
    logger.info(f"Creating new item: {item.model_dump()}")

    # Generate ID
    item_id = f"item_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    # Create document
    document = {
        "_id": item_id,
        "name": item.name,
        "description": item.description,
        "value": item.value,
        "created_at": datetime.now(),
    }

    # Insert into MongoDB
    await db.items.insert_one(document)
    logger.info(f"Item {item_id} created in MongoDB")

    # Cache invalidation - invalidate cache for the specific item
    await invalidate_specific_item_cache(item_id)

    response = ItemResponse(id=item_id, name=item.name, description=item.description, value=item.value, cached=False)

    logger.info(f"Item {item_id} created successfully")
    return response


@app.put("/items/{item_id}", response_model=ItemResponse)
async def update_item(item_id: str, item: ItemCreate) -> ItemResponse:
    """
    Update endpoint - updates item in MongoDB and invalidates cache
    """
    logger.info(f"Updating item {item_id}: {item.model_dump()}")

    # Update document
    update_doc = {
        "$set": {"name": item.name, "description": item.description, "value": item.value, "updated_at": datetime.now()}
    }

    result = await db.items.update_one({"_id": item_id}, update_doc)

    if result.matched_count == 0:
        logger.warning(f"Item {item_id} not found for update")
        raise HTTPException(status_code=404, detail="Item not found")

    logger.info(f"Item {item_id} updated in MongoDB")

    # Cache invalidation - invalidate cache for the specific item
    await invalidate_specific_item_cache(item_id)

    # Get updated document
    updated_doc = await db.items.find_one({"_id": item_id})

    response = ItemResponse(
        id=updated_doc["_id"],
        name=updated_doc["name"],
        description=updated_doc["description"],
        value=updated_doc["value"],
        cached=False,
    )

    logger.info(f"Item {item_id} updated successfully")
    return response


@app.delete("/items/{item_id}")
async def delete_item(item_id: str) -> Dict[str, str]:
    """
    Delete endpoint - removes item from MongoDB and invalidates cache
    """
    logger.info(f"Deleting item {item_id}")

    result = await db.items.delete_one({"_id": item_id})

    if result.deleted_count == 0:
        logger.warning(f"Item {item_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Item not found")

    logger.info(f"Item {item_id} deleted from MongoDB")

    # Cache invalidation - invalidate cache for the specific item
    await invalidate_specific_item_cache(item_id)

    logger.info(f"Item {item_id} deleted successfully")
    return {"message": f"Item {item_id} deleted successfully"}


@app.get("/items")
async def list_items(limit: int = 10, skip: int = 0) -> Dict[str, Any]:
    """
    List all items (not cached for simplicity)
    """
    logger.info(f"Listing items (limit: {limit}, skip: {skip})")

    cursor = db.items.find().skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)

    total_count = await db.items.count_documents({})

    response = {
        "items": [
            {"id": item["_id"], "name": item["name"], "description": item["description"], "value": item["value"]}
            for item in items
        ],
        "total": total_count,
        "limit": limit,
        "skip": skip,
    }

    logger.info(f"Listed {len(items)} items")
    return response


async def invalidate_cache_for_read_item():
    """
    Invalidate cache entries for read_item function
    """
    logger.info("Invalidating cache for read_item function")

    try:
        # Clear all cache entries for read_item function
        # This will clear all cached read_item calls regardless of item_id
        await FastAPICache.clear(namespace="", key="cache:read_item:*")
        logger.info("Cache invalidated for read_item function")
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")


async def invalidate_specific_item_cache(item_id: str):
    """
    Invalidate cache for a specific item using the same key builder
    """
    logger.info(f"Invalidating cache for item: {item_id}")

    try:
        # Generate the same cache key that would be used by the read_item function
        cache_key = cache_key_builder(read_item, item_id)
        await FastAPICache.clear(namespace="", key=cache_key)
        logger.info(f"Cache invalidated for item {item_id} with key: {cache_key}")
    except Exception as e:
        logger.error(f"Error invalidating cache for item {item_id}: {e}")


async def invalidate_cache_pattern(pattern: str):
    """
    Invalidate cache entries matching a pattern (deprecated - use FastAPICache.clear instead)
    """
    logger.warning(f"Using deprecated invalidate_cache_pattern for: {pattern}")

    try:
        # Use FastAPICache.clear instead of direct Redis access
        await FastAPICache.clear(namespace="", key=pattern)
        logger.info(f"Cache pattern invalidated: {pattern}")
    except Exception as e:
        logger.error(f"Error invalidating cache pattern {pattern}: {e}")


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint"""
    try:
        # Check MongoDB
        await db.admin.command("ping")
        mongo_status = "healthy"
    except Exception as e:
        mongo_status = f"unhealthy: {e}"

    try:
        # Check Redis
        redis_client = FastAPICache.get_backend().redis
        await redis_client.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {e}"

    return {
        "status": "healthy" if mongo_status == "healthy" and redis_status == "healthy" else "unhealthy",
        "mongodb": mongo_status,
        "redis": redis_status,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/cache/clear")
async def clear_cache() -> Dict[str, str]:
    """Clear all cache entries"""
    logger.info("Clearing all cache entries")

    try:
        redis_client = FastAPICache.get_backend().redis
        await redis_client.flushdb()
        logger.info("All cache entries cleared")
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {e}")


@app.post("/test/create-sample-item")
async def create_sample_item() -> ItemResponse:
    """Create a sample item for testing"""
    sample_item = ItemCreate(name="Test Item", description="This is a test item for cache testing", value=42)
    return await create_item(sample_item)


@app.get("/test/cache-status")
async def cache_status() -> Dict[str, Any]:
    """Check cache status and keys"""
    try:
        redis_client = FastAPICache.get_backend().redis

        # Get all keys
        all_keys = await redis_client.keys("*")

        # Get cache-specific keys
        cache_keys = await redis_client.keys("fastapi-cache:*")

        return {
            "redis_connected": True,
            "total_keys": len(all_keys),
            "cache_keys": len(cache_keys),
            "all_keys": all_keys,
            "cache_keys_list": cache_keys,
            "cache_prefix": "fastapi-cache",
        }
    except Exception as e:
        return {"redis_connected": False, "error": str(e)}


@app.get("/test/cache-debug/{item_id}")
async def cache_debug(item_id: str) -> Dict[str, Any]:
    """Debug cache behavior for a specific item"""
    try:
        # Generate the cache key that would be used
        cache_key = cache_key_builder(read_item, item_id)
        full_cache_key = f"fastapi-cache:{cache_key}"
        
        # Check if key exists in Redis
        redis_client = FastAPICache.get_backend().redis
        exists = await redis_client.exists(full_cache_key)
        
        # Get the value if it exists
        cached_value = None
        if exists:
            cached_value = await redis_client.get(full_cache_key)
        
        # Get TTL
        ttl = await redis_client.ttl(full_cache_key) if exists else -1
        
        return {
            "item_id": item_id,
            "cache_key": cache_key,
            "full_cache_key": full_cache_key,
            "exists_in_cache": bool(exists),
            "cached_value": cached_value,
            "ttl_seconds": ttl,
            "cache_prefix": "fastapi-cache"
        }
    except Exception as e:
        return {
            "error": str(e),
            "item_id": item_id
        }


if __name__ == "__main__":
    # uvicorn.run("simple_app_with_caching:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
    uvicorn.run(app, host="0.0.0.0", port=8101, log_level="debug")
