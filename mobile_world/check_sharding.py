# Generated with Claude Sonnet 4

import asyncio
from typing import Optional
import random
from datetime import datetime

from pydantic import Field
from beanie import Document, init_beanie, PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient


class TestDocument(Document):
    """Тестовая модель документа для проверки шардирования"""
    id: PydanticObjectId = Field(default_factory=PydanticObjectId)
    name: str
    age: int
    city: str
    score: float
    created_at: datetime
    
    class Settings:
        name = "test_collection"  # Имя коллекции в MongoDB


async def init_database():
    """Инициализация подключения к MongoDB и Beanie"""
    # Подключаемся к mongos роутеру (порт 27017)
    client = AsyncIOMotorClient("mongodb://localhost:27017/")
    
    # Инициализируем Beanie с тестовой базой данных
    await init_beanie(
        database=client.test_sharding_db,
        document_models=[TestDocument]
    )
    
    return client


def setup_sharding():
    """Настройка шардирования для базы данных и коллекции"""
    # Используем синхронный клиент для административных команд
    client = MongoClient("mongodb://localhost:27017/")
    admin_db = client.admin
    
    try:
        # Включаем шардирование для базы данных
        print("🔧 Включаем шардирование для базы данных test_sharding_db...")
        result = admin_db.command("enableSharding", "test_sharding_db")
        print(f"✅ Результат: {result}")
        
        print("📊 Используем встроенный индекс для поля '_id'")
        
        # Включаем ХЕШИРОВАННОЕ шардирование для коллекции по полю '_id'
        print("🔧 Включаем ХЕШИРОВАННОЕ шардирование для коллекции test_collection...")
        print("💡 Это обеспечит мгновенное распределение новых документов!")
        
        result = admin_db.command(
            "shardCollection", 
            "test_sharding_db.test_collection",
            key={"_id": "hashed"}  # ХЕШИРОВАННОЕ шардирование!
        )
        print(f"✅ Результат: {result}")
        
        # При хешированном шардировании MongoDB автоматически создает chunks
        print("🎯 MongoDB автоматически создаст chunks для равномерного распределения")
        
    except Exception as e:
        print(f"⚠️ Ошибка при настройке шардирования: {e}")
    
    finally:
        client.close()


async def insert_test_data():
    """Вставка 1000 тестовых документов"""
    print("📝 Создаем 1000 тестовых документов...")
    
    cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
    names = ["Алексей", "Мария", "Дмитрий", "Анна", "Сергей", "Елена", "Андрей", "Ольга"]
    
    documents = []
    for i in range(1000):
        doc = TestDocument(
            name=random.choice(names),
            age=random.randint(18, 80),  # Возраст от 18 до 80 лет
            city=random.choice(cities),
            score=round(random.uniform(0, 100), 2),
            created_at=datetime.now()
        )
        documents.append(doc)
    
    # Массовая вставка документов
    await TestDocument.insert_many(documents)
    print("✅ Все документы успешно вставлены!")


def check_shard_distribution():
    """Проверка распределения документов по шардам через прямое подключение"""
    # Порты шардов из docker-compose.yml
    shard_configs = [
        {"name": "shard1", "port": 27018, "replica_set": "shard1rs"},
        {"name": "shard2", "port": 27020, "replica_set": "shard2rs"}, 
        {"name": "shard3", "port": 27021, "replica_set": "shard3rs"}
    ]
    
    print("\n🗂️ Подключаемся к каждому шарду напрямую:")
    total_docs_on_shards = 0
    
    for shard in shard_configs:
        try:
            # Подключаемся к конкретному шарду (грямое подключение, игнорируем replica set))
            shard_client = MongoClient(f"mongodb://localhost:{shard['port']}/", directConnection=True)
            shard_db = shard_client.test_sharding_db
            collection = shard_db.test_collection
            
            # Считаем документы на этом шарде
            doc_count = collection.count_documents({})
            total_docs_on_shards += doc_count
            
            # Получаем примеры документов для анализа
            sample_docs = list(collection.find({}, {"age": 1, "_id": 0}).limit(5))
            ages = [doc.get("age", "N/A") for doc in sample_docs]
            
            percentage = (doc_count / 1000) * 100 if doc_count > 0 else 0
            
            print(f"   📊 {shard['name']} (порт {shard['port']}): {doc_count} документов ({percentage:.1f}%)")
            if ages:
                print(f"      Примеры возрастов: {ages}")
            
            shard_client.close()
            
        except Exception as e:
            print(f"   ❌ Ошибка подключения к {shard['name']}: {e}")
    
    print(f"\n✅ Всего документов на шардах: {total_docs_on_shards}")
    
    # Дополнительно получаем общую статистику через mongos
    try:
        mongos_client = MongoClient("mongodb://localhost:27017/")
        admin_db = mongos_client.admin
        
        # Информация о шардах
        shards_info = admin_db.command("listShards")
        print(f"\n🔧 Информация о кластере через mongos:")
        for shard in shards_info['shards']:
            print(f"   Шард: {shard['_id']} -> {shard['host']}")
        
        # Общая статистика коллекции
        test_db = mongos_client.test_sharding_db
        stats = test_db.command("collStats", "test_collection")
        total_via_mongos = stats.get('count', 0)
        print(f"   Всего документов через mongos: {total_via_mongos}")
        
        mongos_client.close()
        
    except Exception as e:
        print(f"❌ Ошибка при получении статистики через mongos: {e}")



def clean_existing_collection():
    """Простая очистка существующей коллекции для тестирования"""
    client = MongoClient("mongodb://localhost:27017/")
    
    try:
        test_db = client.test_sharding_db
        collection_name = "test_collection"
        
        # Проверяем существование коллекции
        existing_collections = test_db.list_collection_names()
        
        if collection_name in existing_collections:
            print(f"⚠️ Коллекция '{collection_name}' существует, удаляем...")
            
            # Просто удаляем коллекцию
            test_db[collection_name].drop()
            print("✅ Коллекция удалена")
            
            # Быстрая очистка метаданных шардирования (на всякий случай)
            try:
                config_db = client.config
                config_db.chunks.delete_many({"ns": f"test_sharding_db.{collection_name}"})
                config_db.collections.delete_many({"_id": f"test_sharding_db.{collection_name}"})
                print("🧹 Метаданные очищены")
            except Exception as e:
                print(f"⚠️ Не критично: {e}")
                
        else:
            print(f"✅ Коллекция '{collection_name}' не существует")
            
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
    
    finally:
        client.close()


async def main():
    """Основная функция"""
    print("🚀 Запуск проверки шардирования MongoDB")
    print("=" * 50)
    
    # Инициализация подключения
    client = await init_database()
    
    try:
        # Очистка существующей коллекции
        clean_existing_collection()
        
        # Настройка шардирования
        setup_sharding()
        
        # Вставка тестовых данных
        await insert_test_data()
        
        # Проверка распределения
        check_shard_distribution()
        
        print("\n🎉 Проверка завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
