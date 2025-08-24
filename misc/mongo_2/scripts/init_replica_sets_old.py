#!/usr/bin/env python3
"""
MongoDB Replica Set Initializer with Connection Management

This script initializes MongoDB replica sets with support for both internal
(Docker) and external (localhost) connection settings.
"""

import os
import time
import logging
from typing import Dict, List, Optional, TypedDict, Any
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure, ConnectionFailure


class MongoConnectionSettings:
    """
    Manages MongoDB connection settings for different environments.

    Attributes:
        config_servers: List of config server connection strings
        shard_servers: Dictionary mapping shard names to their primary connection strings
        mongos_servers: List of mongos router connection strings
        connection_timeout: Connection timeout in milliseconds
        server_selection_timeout: Server selection timeout in milliseconds
    """

    def __init__(
        self,
        config_servers: List[str],
        shard_servers: Dict[str, str],
        mongos_servers: List[str],
        connection_timeout: int = 2000,
        server_selection_timeout: int = 2000,
    ):
        self.config_servers = config_servers
        self.shard_servers = shard_servers
        self.mongos_servers = mongos_servers
        self.connection_timeout = connection_timeout
        self.server_selection_timeout = server_selection_timeout

    def get_client(self, host: str, port: int = 27017) -> MongoClient:
        """Create a MongoDB client with the current settings."""
        return MongoClient(
            host=host,
            port=port,
            connectTimeoutMS=self.connection_timeout,
            serverSelectionTimeoutMS=self.server_selection_timeout,
        )

    def __str__(self) -> str:
        """String representation of the connection settings."""
        return (
            f"MongoConnectionSettings(\n"
            f"  config_servers={self.config_servers},\n"
            f"  shard_servers={self.shard_servers},\n"
            f"  mongos_servers={self.mongos_servers},\n"
            f"  timeouts=({self.connection_timeout}ms, {self.server_selection_timeout}ms)\n"
            f")"
        )


# Internal connection settings (Docker container names and ports)
MONGO_INTERNAL = MongoConnectionSettings(
    config_servers=["configsvr1:27017", "configsvr2:27017", "configsvr3:27017"],
    shard_servers={
        "shard1rs": "shard1-primary:27017",
        "shard2rs": "shard2-primary:27017",
        "shard3rs": "shard3-primary:27017",
    },
    mongos_servers=["mongos1:27017", "mongos2:27018"],
)

# External connection settings (localhost and exposed ports)
MONGO_EXTERNAL = MongoConnectionSettings(
    config_servers=["localhost:27027", "localhost:27028", "localhost:27029"],
    shard_servers={"shard1rs": "localhost:27019", "shard2rs": "localhost:27022", "shard3rs": "localhost:27025"},
    mongos_servers=["localhost:27017", "localhost:27018"],
)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MongoReplicaSetInitializer:
    def __init__(self, connection_settings: MongoConnectionSettings):
        """
        Initialize the replica set initializer with connection settings.

        Args:
            connection_settings: MongoConnectionSettings object with connection details
        """
        self.connection_settings = connection_settings
        self.max_wait_attempts = 15
        self.max_init_attempts = 5

    def wait_for_mongo(self, host: str, port: int = 27017) -> bool:
        """
        Wait for MongoDB server to become ready.

        Args:
            host: MongoDB host
            port: MongoDB port

        Returns:
            bool: True if MongoDB is ready, False otherwise
        """
        logger.info(f"Waiting for MongoDB at {host}:{port}...")

        for attempt in range(1, self.max_wait_attempts + 1):
            try:
                client = self.connection_settings.get_client(host, port)
                # Test the connection
                client.admin.command("ping")
                client.close()
                logger.info(f"✅ MongoDB at {host}:{port} is ready (attempt {attempt})")
                return True

            except (ServerSelectionTimeoutError, ConnectionFailure) as e:
                logger.info(
                    f"⏳ Attempt {attempt}/{self.max_wait_attempts}: MongoDB at {host}:{port} not ready, waiting..."
                )
                time.sleep(2)

        logger.error(f"❌ MongoDB на {host}:{port} не готов после {self.max_wait_attempts} попыток (30 секунд)")
        return False

    def check_replica_set_status(self, host: str, port: int = 27017) -> Dict[str, bool]:
        """Проверка состояния replica set"""
        try:
            client = MongoClient(
                host=host,
                port=port,
                connectTimeoutMS=self.connection_timeout,
                serverSelectionTimeoutMS=self.server_selection_timeout,
            )

            try:
                status = client.admin.command("replSetGetStatus")
                is_initialized = status.get("ok") == 1 and len(status.get("members", [])) > 0
                has_primary = any(member.get("stateStr") == "PRIMARY" for member in status.get("members", []))

                client.close()
                return {"initialized": is_initialized, "has_primary": has_primary}
            except OperationFailure:
                # Replica set не инициализирован
                client.close()
                return {"initialized": False, "has_primary": False}

        except (ServerSelectionTimeoutError, ConnectionFailure):
            return {"initialized": False, "has_primary": False}

    def initialize_replica_set(self, host: str, config: Dict, port: int = 27017) -> bool:
        """Инициализация replica set"""
        try:
            client = MongoClient(
                host=host,
                port=port,
                connectTimeoutMS=self.connection_timeout,
                serverSelectionTimeoutMS=self.server_selection_timeout,
            )

            result = client.admin.command("replSetInitiate", config)
            client.close()

            return result.get("ok") == 1

        except (ServerSelectionTimeoutError, ConnectionFailure, OperationFailure) as e:
            logger.error(f"❌ Ошибка при инициализации replica set: {e}")
            return False

    def init_rs_if_needed(self, host: str, config: Dict, rs_name: str, port: int = 27017) -> bool:
        """Проверка и инициализация replica set с retry логикой"""
        logger.info(f"Проверяем состояние {rs_name} на {host}:{port}...")

        # Сначала ждем готовности MongoDB
        if not self.wait_for_mongo(host, port):
            logger.error(f"❌ Не удалось дождаться готовности {host}:{port} для {rs_name}")
            return False

        for attempt in range(1, self.max_init_attempts + 1):
            logger.info(f"Попытка {attempt}/{self.max_init_attempts} для {rs_name}...")

            # Проверяем текущий статус
            status = self.check_replica_set_status(host, port)

            if status["initialized"]:
                logger.info(f"✅ {rs_name} уже инициализирован")

                # Проверяем наличие PRIMARY с ожиданием
                primary_wait_attempts = 4  # 20 секунд ожидания выборов

                for primary_attempt in range(1, primary_wait_attempts + 1):
                    status = self.check_replica_set_status(host, port)

                    if status["has_primary"]:
                        logger.info(f"✅ {rs_name} имеет PRIMARY узел")
                        return True
                    else:
                        if primary_attempt == 1:
                            logger.warning(f"⚠️ {rs_name} инициализирован, но нет PRIMARY. Ждем выборы...")

                        remaining = primary_wait_attempts - primary_attempt
                        logger.info(
                            f"⏳ Ожидание выборов PRIMARY ({primary_attempt}/{primary_wait_attempts}) - осталось {remaining} попыток..."
                        )
                        time.sleep(5)

                logger.warning(
                    f"⚠️ {rs_name} инициализирован, но PRIMARY не выбран за 20 секунд. Возможна повторная инициализация."
                )
                # Переходим к следующей попытке полной инициализации
            else:
                logger.info(f"🔧 Инициализируем {rs_name}...")
                if self.initialize_replica_set(host, config, port):
                    logger.info(f"✅ Команда инициализации {rs_name} выполнена успешно")
                    time.sleep(5)  # Даем время на инициализацию
                else:
                    logger.error(f"❌ Ошибка при инициализации {rs_name}")

            if attempt < self.max_init_attempts:
                logger.info("⏳ Ждем 5 секунд перед следующей попыткой...")
                time.sleep(5)

        logger.error(f"❌ Не удалось инициализировать {rs_name} после {self.max_init_attempts} попыток")
        return False

    def get_replica_set_status(self, host: str, port: int = 27017) -> Optional[List[Dict]]:
        """Получение статуса replica set для отображения"""
        try:
            client = MongoClient(
                host=host,
                port=port,
                connectTimeoutMS=self.connection_timeout,
                serverSelectionTimeoutMS=self.server_selection_timeout,
            )

            status = client.admin.command("replSetGetStatus")
            members = []

            for member in status.get("members", []):
                members.append({"name": member.get("name"), "state": member.get("stateStr")})

            client.close()
            return members

        except (ServerSelectionTimeoutError, ConnectionFailure, OperationFailure):
            return None

    def run(self):
        """Основная логика инициализации"""
        logger.info("🚀 Начинаем инициализацию replica sets...")

        # Конфигурация config server replica set (3 узла для кворума)
        logger.info("📋 Инициализируем config server replica set...")
        config_rs_config = {
            "_id": "configrs",
            "configsvr": True,
            "members": [
                {"_id": 0, "host": "configsvr1:27017"},
                {"_id": 1, "host": "configsvr2:27017"},
                {"_id": 2, "host": "configsvr3:27017"},
            ],
        }

        if not self.init_rs_if_needed("configsvr1", config_rs_config, "configrs"):
            logger.error("❌ Критическая ошибка: не удалось инициализировать config server replica set")
            return False

        # Ждем стабилизации config servers
        logger.info("⏳ Ждем стабилизации config server replica set...")
        time.sleep(15)

        # Инициализируем shard replica sets (каждый с primary и secondary)
        logger.info("📊 Инициализируем shard replica sets...")

        shard_configs = [
            {
                "host": "shard1-primary",
                "config": {
                    "_id": "shard1rs",
                    "members": [
                        {"_id": 0, "host": "shard1-primary:27017"},
                        {"_id": 1, "host": "shard1-secondary:27017"},
                    ],
                },
                "name": "shard1rs",
            },
            {
                "host": "shard2-primary",
                "config": {
                    "_id": "shard2rs",
                    "members": [
                        {"_id": 0, "host": "shard2-primary:27017"},
                        {"_id": 1, "host": "shard2-secondary:27017"},
                    ],
                },
                "name": "shard2rs",
            },
            {
                "host": "shard3-primary",
                "config": {
                    "_id": "shard3rs",
                    "members": [
                        {"_id": 0, "host": "shard3-primary:27017"},
                        {"_id": 1, "host": "shard3-secondary:27017"},
                    ],
                },
                "name": "shard3rs",
            },
        ]

        success = True
        for shard in shard_configs:
            if not self.init_rs_if_needed(shard["host"], shard["config"], shard["name"]):
                success = False

        # Финальная проверка всех replica sets
        logger.info("🔍 Финальная проверка всех replica sets...")
        time.sleep(10)

        logger.info("📋 Config Server Status:")
        config_status = self.get_replica_set_status("configsvr1")
        if config_status:
            for member in config_status:
                logger.info(f"{member['name']}: {member['state']}")
        else:
            logger.error("❌ Ошибка получения статуса configrs")

        logger.info("📊 Shard Status:")
        for shard in ["shard1-primary", "shard2-primary", "shard3-primary"]:
            logger.info(f"--- {shard} ---")
            shard_status = self.get_replica_set_status(shard)
            if shard_status:
                for member in shard_status:
                    logger.info(f"{member['name']}: {member['state']}")
            else:
                logger.error(f"❌ Ошибка получения статуса {shard}")

        if success:
            logger.info("🎉 Инициализация replica sets завершена!")
            return True
        else:
            logger.error("❌ Инициализация завершена с ошибками!")
            return False


def main():
    """
    Main entry point for the MongoDB replica set initializer.

    The connection mode is determined by the MONGO_USE_EXTERNAL environment variable:
    - If MONGO_USE_EXTERNAL is 'true', '1', or 'yes', uses external connection settings (localhost with exposed ports)
    - Otherwise, uses internal Docker network settings (container names)

    Example usage with Docker Compose:
    ```yaml
    services:
      init-replicas:
        environment:
          - MONGO_USE_EXTERNAL=true  # Use external connection settings
    ```
    """
    # Select appropriate connection settings based on environment variable
    use_external = bool(os.environ.get("MONGO_USE_EXTERNAL", True))
    connection_settings = MONGO_EXTERNAL if use_external else MONGO_INTERNAL

    logger.info(f"Using {'external' if use_external else 'internal'} connection settings")
    logger.debug(f"Connection settings: {connection_settings}")

    # Initialize and run the replica set initializer
    initializer = MongoReplicaSetInitializer(connection_settings)
    success = initializer.run()

    exit(0 if success else 1)


if __name__ == "__main__":
    main()
