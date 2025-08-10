from typing import List, Dict
import os, sys
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


import pymongo
from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError


class MongoConnnectionSettings(BaseSettings):
    config_servers: List[str] = ["localhost:27019", "localhost:27020", "localhost:27021"]
    config_rs_name: str = "configrs"
    shard_servers: Dict[str, Dict[str, str]] = {
        "shard1rs": {"shard1-primary": "localhost:27019", "shard1-secondary": "localhost:27020"},
        "shard2rs": {"shard2-primary": "localhost:27022", "shard2-secondary": "localhost:27023"},
        "shard3rs": {"shard3-primary": "localhost:27025", "shard3-secondary": "localhost:27026"},
    }
    mongos_servers: List[str] = ["localhost:27017", "localhost:27018"]
    connection_timeout: int = 2000
    server_selection_timeout: int = 2000


external_connection_settings = MongoConnnectionSettings()

internal_connection_settings = MongoConnnectionSettings(
    config_servers=["configsvr1:27017", "configsvr2:27017", "configsvr3:27017"],
    shard_servers={
        "shard1rs": {"shard1-primary": "shard1-primary:27017", "shard1-secondary": "shard1-secondary:27017"},
        "shard2rs": {"shard2-primary": "shard2-primary:27017", "shard2-secondary": "shard2-secondary:27017"},
        "shard3rs": {"shard3-primary": "shard3-primary:27017", "shard3-secondary": "shard3-secondary:27017"},
    },
    mongos_servers=["mongos1:27017", "mongos2:27017"],
)


def get_server_available(host: str, connection_timeout_ms: int = 5000) -> bool:
    """Проверить доступность одного конфиг-сервера."""
    try:
        client = pymongo.MongoClient(
            host,
            serverSelectionTimeoutMS=connection_timeout_ms,
            connectTimeoutMS=connection_timeout_ms,
            directConnection=True,
        )
        # Используем hello вместо ping - работает в состоянии RSGhost
        result = client.admin.command("hello")
        client.close()

        # Проверяем статус сервера
        if result.get("ismaster") or result.get("secondary") or result.get("arbiterOnly"):
            logger.info(f"Конфиг-сервер {host} доступен (состояние: {result.get('msg', 'ok')})")
        else:
            logger.info(f"Конфиг-сервер {host} доступен, но в состоянии RSGhost (ожидает инициализации)")

        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"Конфиг-сервер {host} недоступен: {e}")
        return False


def get_all_servers_available(servers: List[str], connection_timeout_ms: int = 5000) -> bool:
    """Проверить доступность всех конфиг-серверов."""
    logger.info("Проверка доступности всех конфиг-серверов...")

    available = []
    for server in servers:
        if get_server_available(server, connection_timeout_ms):
            available.append(server)

    if len(available) == len(servers):
        logger.info("Все конфиг-сервера доступны")
        return True
    else:
        logger.error(f"Доступно {len(available)} из {len(servers)} серверов")
        return False


def initialize_replica_set(client: MongoClient, servers: List[str], rs_name: str) -> None:
    """Инициализировать replica set для конфиг-серверов."""
    logger.info(f"Инициализация replica set '{rs_name}'...")

    # Формируем конфигурацию replica set
    members = []
    for i, server in enumerate(servers):
        members.append({"_id": i, "host": server})  # Помечаем как конфиг-сервер

    config = {"_id": rs_name, "configsvr": True, "members": members}  # Обязательно для конфиг-серверов

    logger.info(f"Попытка инициализации через клиент {client.host}:{client.port}")
    result = client.admin.command("replSetInitiate", config)
    logger.info(f"Replica set инициализирован, result: {result}")


def is_replica_set_initialized(client: pymongo.MongoClient) -> bool:
    """Проверить, инициализирован ли replica set."""
    status = client.admin.command("isMaster")
    return "setName" in status


if __name__ == "__main__":

    running_in_docker = os.environ.get("CONTAINER") == "docker"
    conn_settings = internal_connection_settings if running_in_docker else external_connection_settings
    get_all_servers_available(conn_settings.config_servers, 5000)

    for config_server in conn_settings.config_servers:
        rs_uri = f"mongodb://{config_server}"
        client = pymongo.MongoClient(
            rs_uri, directConnection=True, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000
        )
        if is_replica_set_initialized(client):
            logging.info("Replica set уже инициализирован")
            continue
        else:
            initialize_replica_set(client, internal_connection_settings.config_servers, conn_settings.config_rs_name)
            client.close()
            break  # Считаем, что если удалось хотя бы на одном конфиг-сервере, то инициализация и так произойдёт
        client.close()
