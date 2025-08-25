import asyncio
import random
from datetime import datetime
from typing import Optional, List
import motor.motor_asyncio
from beanie import Document, Indexed, init_beanie, Link
from pydantic import BaseModel
import pymongo
from pymongo import MongoClient
from pymongo.errors import OperationFailure
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Модели данных
class Category(Document):
    name: str = Indexed(unique=True)
    description: Optional[str] = None
    created_at: datetime = datetime.now()

    class Settings:
        name = "categories"


class Product(Document):
    name: str
    description: Optional[str] = None
    price: float
    category: Optional[Link[Category]] = Indexed()  # Поле для шардирования
    brand: Optional[str] = None
    model: Optional[str] = None
    specifications: Optional[dict] = None
    in_stock: bool = True
    stock_quantity: int = 0
    created_at: datetime = datetime.now()

    class Settings:
        name = "products"


class MongoDBLoadTester:
    def __init__(self, connection_url: str, database_name: str):
        self.connection_url = connection_url
        self.database_name = database_name
        self.client = None
        self.motor_client = None

    async def connect(self):
        """Подключение к MongoDB"""
        try:
            # Motor client для async операций
            self.motor_client = motor.motor_asyncio.AsyncIOMotorClient(self.connection_url)

            # PyMongo client для административных операций
            self.client = MongoClient(self.connection_url)

            # Проверка подключения
            await self.motor_client.admin.command("ping")
            logger.info("Успешно подключились к MongoDB")

        except Exception as e:
            logger.error(f"Ошибка подключения к MongoDB: {e}")
            raise

    async def setup_database(self):
        """Создание базы данных и настройка шардирования"""
        try:
            # Создаем базу данных (создается автоматически при первом использовании)
            db = self.motor_client[self.database_name]

            # Проверяем, является ли это шардированным кластером
            try:
                admin_db = self.client.admin
                is_mongos = admin_db.command("hello").get("msg") == "isdbgrid"

                if is_mongos:
                    logger.info("Обнаружен шардированный кластер")
                    await self.enable_sharding()
                else:
                    logger.warning("Не обнаружен шардированный кластер. Шардирование будет пропущено.")

            except Exception as e:
                logger.warning(f"Не удалось проверить тип кластера: {e}")

            # Инициализация Beanie
            await init_beanie(database=db, document_models=[Category, Product])
            logger.info(f"База данных '{self.database_name}' готова к работе")

        except Exception as e:
            logger.error(f"Ошибка при настройке базы данных: {e}")
            raise

    async def enable_sharding(self):
        """Включение шардирования для базы данных и коллекций"""
        try:
            admin_db = self.client.admin

            # Включаем шардирование для базы данных
            try:
                result = admin_db.command("enableSharding", self.database_name)
                logger.info(f"Шардирование включено для БД '{self.database_name}': {result}")
            except OperationFailure as e:
                if "already enabled" in str(e):
                    logger.info(f"Шардирование уже включено для БД '{self.database_name}'")
                else:
                    raise

            # Шардирование коллекции products по полю category
            try:
                result = admin_db.command("shardCollection", f"{self.database_name}.products", key={"category": 1})
                logger.info(f"Коллекция products шардирована: {result}")
            except OperationFailure as e:
                if "already sharded" in str(e):
                    logger.info("Коллекция products уже шардирована")
                else:
                    raise

        except Exception as e:
            logger.error(f"Ошибка при настройке шардирования: {e}")
            raise

    async def create_categories(self):
        """Создание категорий товаров"""
        categories_data = [
            {"name": "Электроника", "description": "Электронные устройства и гаджеты"},
            {"name": "Одежда", "description": "Мужская и женская одежда"},
            {"name": "Дом и сад", "description": "Товары для дома и садоводства"},
            {"name": "Спорт", "description": "Спортивные товары и оборудование"},
            {"name": "Книги", "description": "Художественная и техническая литература"},
            {"name": "Автомобили", "description": "Автозапчасти и аксессуары"},
        ]

        created_count = 0
        for cat_data in categories_data:
            try:
                # Проверяем, существует ли уже такая категория
                existing_category = await Category.find_one(Category.name == cat_data["name"])
                if not existing_category:
                    category = Category(**cat_data)
                    await category.insert()
                    created_count += 1
                    logger.info(f"Создана категория: {cat_data['name']}")
                else:
                    logger.info(f"Категория '{cat_data['name']}' уже существует")
            except Exception as e:
                logger.error(f"Ошибка при создании категории {cat_data['name']}: {e}")

        logger.info(f"Создано новых категорий: {created_count}")

    async def generate_electronic_products(self, count: int, electronics_category: Category) -> List[dict]:
        """Генерация данных для электронных товаров"""
        brands = ["Samsung", "Apple", "Sony", "LG", "Xiaomi", "Huawei", "Dell", "HP", "Lenovo", "ASUS"]
        product_types = [
            "Смартфон",
            "Ноутбук",
            "Планшет",
            "Наушники",
            "Телевизор",
            "Камера",
            "Монитор",
            "Клавиатура",
            "Мышь",
            "Колонки",
        ]

        products = []
        for i in range(count):
            brand = random.choice(brands)
            product_type = random.choice(product_types)
            model_num = random.randint(100, 9999)

            product_data = {
                "name": f"{brand} {product_type} {model_num}",
                "description": f"Высококачественный {product_type.lower()} от {brand}",
                "price": round(random.uniform(1000, 150000), 2),
                "category": electronics_category,  # Передаем объект Category для создания Link
                "brand": brand,
                "model": f"Model-{model_num}",
                "specifications": {
                    "warranty": f"{random.randint(1, 3)} года",
                    "color": random.choice(["Черный", "Белый", "Серый", "Синий", "Красный"]),
                    "weight": f"{random.randint(100, 5000)}г",
                },
                "in_stock": random.choice([True, True, True, False]),  # 75% в наличии
                "stock_quantity": random.randint(0, 1000),
                "created_at": datetime.now(),
            }
            products.append(product_data)

        return products

    async def create_products_batch(self, products_data: List[dict], batch_size: int = 1000):
        """Создание товаров батчами для лучшей производительности"""
        total_created = 0

        for i in range(0, len(products_data), batch_size):
            batch = products_data[i : i + batch_size]
            try:
                # Создаем документы Product
                products = [Product(**data) for data in batch]

                # Вставляем батч
                await Product.insert_many(products)
                total_created += len(batch)
                logger.info(f"Создано товаров: {total_created}/{len(products_data)}")

            except Exception as e:
                logger.error(f"Ошибка при создании батча товаров: {e}")

        logger.info(f"Всего создано товаров: {total_created}")

    async def load_test_electronics(self, product_count: int = 100000):
        """Создание большого количества товаров категории 'Электроника' для нагрузочного тестирования"""
        logger.info(f"Начинаем создание {product_count} товаров категории 'Электроника'")

        # Находим категорию "Электроника"
        electronics_category = await Category.find_one(Category.name == "Электроника")
        if not electronics_category:
            logger.error("Категория 'Электроника' не найдена. Убедитесь, что категории созданы.")
            return

        # Проверяем, сколько товаров уже есть
        existing_count = await Product.find(Product.category.id == electronics_category.id).count()
        logger.info(f"Уже существует товаров 'Электроника': {existing_count}")

        # Генерируем данные
        logger.info("Генерируем данные товаров...")
        products_data = await self.generate_electronic_products(product_count, electronics_category)

        # Создаем товары батчами
        await self.create_products_batch(products_data)

        # Проверяем финальное количество
        final_count = await Product.find(Product.category.id == electronics_category.id).count()
        logger.info(f"Итоговое количество товаров 'Электроника': {final_count}")

    async def get_database_stats(self):
        """Получение статистики по базе данных"""
        try:
            # Статистика по коллекциям
            categories_count = await Category.count()
            products_count = await Product.count()

            # Найдем категорию "Электроника" для подсчета её товаров
            electronics_category = await Category.find_one(Category.name == "Электроника")
            electronics_count = 0
            if electronics_category:
                electronics_count = await Product.find(Product.category.id == electronics_category.id).count()

            logger.info("=== Статистика базы данных ===")
            logger.info(f"Категорий: {categories_count}")
            logger.info(f"Всего товаров: {products_count}")
            logger.info(f"Товаров 'Электроника': {electronics_count}")

            # Статистика по категориям
            categories = await Category.find_all().to_list()
            for category in categories:
                count = await Product.find(Product.category.id == category.id).count()
                logger.info(f"Товаров в категории '{category.name}': {count}")

        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")

    async def close_connection(self):
        """Закрытие соединений"""
        if self.motor_client:
            self.motor_client.close()
        if self.client:
            self.client.close()


async def main():
    # Настройки подключения
    CONNECTION_URL = "mongodb://root:rootpass@minikube-docker:30000,minikube-docker:30001"  # Измените на ваш URL
    DATABASE_NAME = "load_test_db"
    PRODUCTS_COUNT = 5000_000  # Количество товаров для создания

    tester = MongoDBLoadTester(CONNECTION_URL, DATABASE_NAME)

    try:
        # Подключение
        await tester.connect()

        # Настройка БД и шардирования
        await tester.setup_database()

        # Создание категорий
        await tester.create_categories()

        # Нагрузочное тестирование - создание множества товаров
        await tester.load_test_electronics(PRODUCTS_COUNT)

        # Получение статистики
        await tester.get_database_stats()

    except Exception as e:
        logger.error(f"Ошибка в main: {e}")
    finally:
        await tester.close_connection()


if __name__ == "__main__":
    asyncio.run(main())
