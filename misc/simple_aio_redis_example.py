import asyncio
import logging
import json
from datetime import datetime
import redis.asyncio as redis

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

redis_logger = logging.getLogger("redis")
redis_logger.setLevel(logging.DEBUG)


async def test_redis_operations():
    # Basic redis operations testing...
    logger.info("Starting Redis operations test with built-in logging")

    import logging_tree.format

    logger.info(logging_tree.format.build_description())  # As we can see, all loggers are set to DEBUG mode...

    logger.info("Connecting to Redis at localhost:6379...")
    redis_client = redis.from_url(
        "redis://localhost:6379",
        encoding="utf8",
        decode_responses=True,
        socket_keepalive=True,
        socket_keepalive_options={},
        health_check_interval=30,
    )

    try:
        result = await redis_client.ping()

        test_key = "test:user:123"
        test_value = json.dumps(
            {"id": 123, "name": "John Doe", "email": "john@example.com", "created_at": datetime.now().isoformat()}
        )

        result = await redis_client.get(test_key)
        set_result = await redis_client.set(test_key, test_value, ex=300)

        get_result = await redis_client.get(test_key)

        if get_result:
            parsed_data = json.loads(get_result)

        ttl = await redis_client.ttl(test_key)

        result2 = await redis_client.get(test_key)

        for i in range(3):
            key = f"test:item:{i}"
            value = json.dumps({"id": i, "name": f"Item {i}", "value": i * 10})
            result = await redis_client.set(key, value, ex=600)

        all_test_keys = await redis_client.keys("test:*")

        for key in all_test_keys:
            value = await redis_client.get(key)
            if value:
                data = json.loads(value)

        deleted_count = await redis_client.delete(*all_test_keys)

        result_after_delete = await redis_client.get(test_key)

        logger.info("Process finished. Disconnecting from localhost:6379...")

    except Exception as e:
        raise
    finally:
        await redis_client.aclose()  # Используем aclose() вместо close()


async def main():
    try:
        await test_redis_operations()

    except Exception as e:
        logger.error(f"Application failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
