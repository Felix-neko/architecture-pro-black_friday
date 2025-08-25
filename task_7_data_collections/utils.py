import logging
from typing import Dict, Any

from pymongo import AsyncMongoClient
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


async def check_sharding_support(client: AsyncMongoClient) -> bool:
    """
    Проверяет, поддерживает ли MongoDB-конфигурация шардирование.

    Returns:
        bool: True если шардирование поддерживается, False иначе
    """
    try:
        # Попытка выполнить команду, доступную только в шардированной среде
        result = await client.admin.command("listShards")
        logger.info("✓ Шардирование поддерживается")
        return True
    except OperationFailure as e:
        if "not running with --shardsvr" in str(e) or "no such command" in str(e):
            logger.info("× Шардирование не поддерживается (standalone/replica set)")
            return False
        else:
            logger.error(f"Ошибка при проверке шардирования: {e}")
            return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке шардирования: {e}")
        return False


async def check_database_sharded(client: AsyncMongoClient, db_name: str) -> bool:
    """
    Проверяет, включено ли шардирование для конкретной БД.

    Args:
        client: MongoDB клиент
        db_name: Имя базы данных

    Returns:
        bool: True если шардирование включено для БД
    """
    try:
        result = await client.config.databases.find_one({"_id": db_name})
        return result is not None and result.get("partitioned", False)
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса шардирования БД {db_name}: {e}")
        return False


async def enable_database_sharding(client: AsyncMongoClient, db_name: str) -> bool:
    """
    Включает шардирование для базы данных.

    Args:
        client: MongoDB клиент
        db_name: Имя базы данных

    Returns:
        bool: True если шардирование успешно включено или уже было включено
    """
    try:
        # Проверяем, не включено ли уже
        if await check_database_sharded(client, db_name):
            logger.info(f"✓ Шардирование для БД '{db_name}' уже включено")
            return True

        # Включаем шардирование
        await client.admin.command("enableSharding", db_name)
        logger.info(f"✓ Шардирование для БД '{db_name}' успешно включено")
        return True

    except OperationFailure as e:
        if "already enabled" in str(e):
            logger.info(f"✓ Шардирование для БД '{db_name}' уже было включено")
            return True
        else:
            logger.error(f"✗ Ошибка при включении шардирования для БД '{db_name}': {e}")
            return False
    except Exception as e:
        logger.error(f"✗ Неожиданная ошибка при включении шардирования для БД '{db_name}': {e}")
        return False


async def check_collection_sharded(client: AsyncMongoClient, db_name: str, collection_name: str) -> bool:
    """
    Проверяет, шардирована ли конкретная коллекция.

    Args:
        client: MongoDB клиент
        db_name: Имя базы данных
        collection_name: Имя коллекции

    Returns:
        bool: True если коллекция шардирована
    """
    try:
        namespace = f"{db_name}.{collection_name}"
        result = await client.config.collections.find_one({"_id": namespace})
        return result is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса шардирования коллекции {namespace}: {e}")
        return False


async def enable_collection_sharding(
    client: AsyncMongoClient, db_name: str, collection_name: str, shard_key: Dict[str, Any]
) -> bool:
    """
    Включает шардирование для коллекции.

    Args:
        client: MongoDB клиент
        db_name: Имя базы данных
        collection_name: Имя коллекции
        shard_key: Ключ шардирования

    Returns:
        bool: True если шардирование успешно включено или уже было включено
    """
    try:
        namespace = f"{db_name}.{collection_name}"

        # Проверяем, не шардирована ли уже коллекция
        if await check_collection_sharded(client, db_name, collection_name):
            logger.info(f"✓ Коллекция '{namespace}' уже шардирована")
            return True

        # Шардируем коллекцию
        await client.admin.command({"shardCollection": namespace, "key": shard_key})
        logger.info(f"✓ Коллекция '{namespace}' успешно шардирована с ключом {shard_key}")
        return True

    except OperationFailure as e:
        if "already sharded" in str(e):
            logger.info(f"✓ Коллекция '{namespace}' уже была шардирована")
            return True
        else:
            logger.error(f"✗ Ошибка при шардировании коллекции '{namespace}': {e}")
            return False
    except Exception as e:
        logger.error(f"✗ Неожиданная ошибка при шардировании коллекции '{namespace}': {e}")
        return False
