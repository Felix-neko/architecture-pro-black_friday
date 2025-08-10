from typing import List, Dict
import os, sys
import time
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
        "shard1rs": {"shard1-primary": "localhost:27022", "shard1-secondary": "localhost:27023"},
        "shard2rs": {"shard2-primary": "localhost:27024", "shard2-secondary": "localhost:27025"},
        "shard3rs": {"shard3-primary": "localhost:27026", "shard3-secondary": "localhost:27027"},
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


def wait_for_primary_election(servers: List[str], timeout: int = 60) -> bool:
    """Дождаться выбора primary в replica set."""
    logger.info("Ожидание выбора primary узла...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Ищем primary узел
            primary_found = False

            for server in servers:
                # Используем replica set подключение с коротким таймаутом
                client = pymongo.MongoClient(
                    server, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000, directConnection=True
                )

                status = client.admin.command("replSetGetStatus")
                client.close()

                for member in status.get("members", []):
                    if member.get("stateStr") == "PRIMARY":
                        logger.info(f"Primary узел найден: {member.get('name')}")
                        return True
                logger.info(f"Primary узел еще не выбран, status: {status}")

        except (OperationFailure, ConnectionFailure, ServerSelectionTimeoutError) as ex:
            # Replica set еще не готов или primary не выбран
            logging.error(ex)
            pass

        logger.info("Ожидание выбора primary... (проверка через 2 секунды)")
        time.sleep(2)

    logger.error(f"Primary узел не был выбран за {timeout} секунд")
    return False


def initialize_shard_replica_set(servers: List[str], rs_name: str, connection_timeout_ms: int = 5000) -> None:
    """Инициализировать replica set для одного шарда."""
    logger.info(f"Инициализация shard replica set '{rs_name}'...")

    # Формируем конфигурацию replica set для шарда
    members = []
    for i, server in enumerate(servers):
        member_config = {"_id": i, "host": server}

        # Первый сервер в списке - предпочтительный primary
        if i == 0:
            member_config["priority"] = 2  # Высокий приоритет для primary
        else:
            member_config["priority"] = 1  # Обычный приоритет для secondary

        members.append(member_config)

    config = {
        "_id": rs_name,
        # БЕЗ configsvr: true - это обычный шард, не конфиг-сервер
        "members": members,
    }

    # Пробуем инициализировать на каждом сервере, пока не получится
    last_error = None
    for server in servers:
        try:
            logger.info(f"Попытка инициализации шарда {rs_name} через сервер {server}")
            client = pymongo.MongoClient(
                server,
                directConnection=True,
                serverSelectionTimeoutMS=connection_timeout_ms,
                connectTimeoutMS=connection_timeout_ms,
            )

            result = client.admin.command("replSetInitiate", config)
            logger.info(f"Shard replica set {rs_name} инициализирован через {server}: {result}")
            client.close()
            return  # Успешно инициализировали, выходим

        except OperationFailure as e:
            client.close()
            if "already initialized" in str(e).lower():
                logger.info(f"Shard replica set {rs_name} уже был инициализирован")
                return  # Уже инициализирован, это нормально
            else:
                logger.warning(f"Не удалось инициализировать {rs_name} через {server}: {e}")
                last_error = e
                continue  # Пробуем следующий сервер

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            client.close()
            logger.warning(f"Не удалось подключиться к {server} для шарда {rs_name}: {e}")
            last_error = e
            continue  # Пробуем следующий сервер

    # Если дошли сюда, значит ни один сервер не сработал
    logger.error(f"Не удалось инициализировать shard replica set {rs_name} ни через один сервер")
    if last_error:
        raise last_error


def check_shard_replica_set_compatibility(shards: Dict[str, Dict[str, str]], connection_timeout_ms: int = 5000) -> bool:
    """Проверить совместимость replica set ID для всех шардов."""
    logger.info("Проверка совместимости replica set ID для шардов...")

    all_compatible = True

    for rs_name, shard_servers in shards.items():
        logger.info(f"Проверка RS: {rs_name}...")
        replica_set_ids = {}

        for server in shard_servers.values():
            try:
                client = pymongo.MongoClient(
                    server,
                    directConnection=True,
                    serverSelectionTimeoutMS=connection_timeout_ms,
                    connectTimeoutMS=connection_timeout_ms,
                )

                try:
                    status = client.admin.command("replSetGetStatus")
                    rs_id = status.get("set")
                    if rs_id:
                        replica_set_ids[server] = rs_id
                        logger.info(f"  Сервер {server}: replica set = {rs_id}")
                    else:
                        logger.info(f"  Сервер {server}: нет replica set")

                except OperationFailure as e:
                    if "no replset config has been received" in str(e).lower():
                        logger.info(f"  Сервер {server}: не инициализирован")
                    else:
                        logger.warning(f"  Ошибка получения статуса {server}: {e}")

                client.close()

            except Exception as e:
                logger.error(f"  Ошибка подключения к {server}: {e}")
                all_compatible = False
                continue

        # Проверяем, что все replica set ID одинаковые или отсутствуют для этого шарда
        unique_ids = set(replica_set_ids.values())

        if len(unique_ids) <= 1:
            logger.info(f"  RS {rs_name}: все серверы совместимы")
        else:
            logger.error(f"  RS {rs_name}: найдены несовместимые replica set ID: {unique_ids}")
            all_compatible = False

    if all_compatible:
        logger.info("Все шарды совместимы для инициализации")
    else:
        logger.error("Найдены несовместимые конфигурации в шардах")

    return all_compatible


def initialize_all_shards() -> bool:
    """Инициализировать все шарды."""
    logger.info("Начало инициализации всех шардов...")

    # Проверяем доступность всех серверов шардов
    all_shard_servers = []
    for shard_name, servers in SHARDS.items():
        all_shard_servers.extend(servers)

    logger.info(f"Проверка доступности {len(all_shard_servers)} серверов шардов...")
    if not check_all_servers_availability(all_shard_servers):
        logger.error("Не все серверы шардов доступны")
        return False

    # Проверяем совместимость replica set ID
    if not check_shard_replica_set_compatibility(SHARDS, CONNECTION_TIMEOUT):
        logger.error("Обнаружены несовместимые replica set ID в шардах")
        logger.error("Требуется очистка конфигурации шардов аналогично конфиг-серверам")
        return False

    # Инициализируем каждый шард
    initialized_shards = []
    failed_shards = []

    for shard_name, servers in SHARDS.items():
        try:
            # Проверяем, инициализирован ли уже этот шард
            shard_initialized = False
            for server in servers:
                try:
                    client = pymongo.MongoClient(
                        server, directConnection=True, serverSelectionTimeoutMS=CONNECTION_TIMEOUT
                    )
                    shard_initialized = is_replica_set_initialized(client)
                    client.close()
                    break  # Если получили ответ, выходим из цикла
                except Exception as e:
                    logger.warning(f"Не удалось проверить статус шарда {shard_name} через {server}: {e}")
                    client.close()
                    continue

            if not shard_initialized:
                # Инициализируем replica set для этого шарда
                initialize_shard_replica_set(servers, shard_name, CONNECTION_TIMEOUT)

            # Ждем выбора primary для этого шарда
            if wait_for_primary_election(servers, shard_name, timeout=30):
                logger.info(f"Шард {shard_name} успешно инициализирован")
                initialized_shards.append(shard_name)
            else:
                logger.error(f"Не удалось дождаться выбора primary для шарда {shard_name}")
                failed_shards.append(shard_name)

        except Exception as e:
            logger.error(f"Ошибка инициализации шарда {shard_name}: {e}")
            failed_shards.append(shard_name)

    # Проверяем результаты
    logger.info(f"Инициализировано шардов: {len(initialized_shards)}/{len(SHARDS)}")
    if initialized_shards:
        logger.info(f"Успешные шарды: {', '.join(initialized_shards)}")
    if failed_shards:
        logger.error(f"Неудачные шарды: {', '.join(failed_shards)}")
        return False

    logger.info("Все шарды успешно инициализированы")
    return True


if __name__ == "__main__":

    running_in_docker = os.environ.get("CONTAINER") == "docker"
    conn_settings = internal_connection_settings if running_in_docker else external_connection_settings
    ####################################
    # Настройка конфиг-серверов
    ####################################
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

    ####################################
    # Настройка шардов
    ####################################
    all_shard_servers = []
    for v in conn_settings.shard_servers.values():
        for server in v.values():
            all_shard_servers.append(server)
    shards_available = get_all_servers_available(all_shard_servers, 5000)
    logging.info(f"Shard servers available: {shards_available}")
    # wait_for_primary_election(conn_settings.config_servers)
    check_shard_replica_set_compatibility(conn_settings.shard_servers)
    for rs_name, rs_shard_servers_dict in conn_settings.shard_servers.items():
        for shard_server in rs_shard_servers_dict.value():
            is_replica_set_initialized()
