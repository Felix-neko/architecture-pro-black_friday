import asyncio
import enum
from datetime import datetime
from typing import Optional, Dict, Tuple, Any

import pymongo
from pydantic import BaseModel

from beanie import init_beanie, Document, Indexed, PydanticObjectId, Link
from pymongo import AsyncMongoClient


class Category(BaseModel):
    name: str
    description: str


class GeoPoint(Document):
    geohash: str
    lat: float
    lon: float


class Warehouse(Document):
    location: Optional[Link[GeoPoint]] = None
    name: str
    description: str = ""


class Product(Document):
    """
    хранит сведения о товарах

    Атрибуты:
    - Уникальный идентификатор товара
    - Наименование
    - Категория товара
    - Цена
    - Остаток товара в каждой геозоне (например, в Екатеринбурге есть в наличии 50 штук товара «Смартфон X», а в Калининграде — 30)
    - Дополнительные атрибуты (цвет, размер)

    """

    name: str
    description: Optional[str] = None
    price: float
    category: Optional[Link[Category]] = None
    extra_info: Dict[str, Any] = {}

    class Settings:
        indexes = [[("price", pymongo.DESCENDING)]]


class OrderStatus(str, enum.Enum):
    CREATED = "CREATED"
    CANCELLED = "CANCELLED"
    PAID = "PAID"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    REFUNDED = "REFUNDED"


class Order(Document):
    """
    Заказы клиентов.

    Атрибуты:
    - Уникальный идентификатор заказа
    - Идентификатор клиента
    - Дата и время оформления заказа
    - Список заказанных товаров и их цену
    - Статус заказа
    - Общая сумма заказа
    - Геозона заказа (например, заказ пользователя из Москвы может включать товары из категорий «Электроника» и «Книги»)

    Основные операции:
    - Быстрое создание заказов с одновременным списанием остатков
    - Поиск истории заказов конкретного пользователя
    - Отображение статуса заказа

    """

    client_id: PydanticObjectId
    created_at: datetime = datetime.now()

    contents: Dict[PydanticObjectId, Tuple[int, float]] = {}  # {product_id: (quantity, price_per_item)}
    status: OrderStatus = OrderStatus.CREATED
    total_sum: float

    dest_location: Optional[Link[GeoPoint]] = None

    class Settings:
        indexes = [[("client_id", pymongo.HASHED)], [("created_at", pymongo.DESCENDING)]]


class CartStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    ORDERED = "ORDERED"
    ABANDONED = "ABANDONED"


class Cart(Document):
    """
    хранит данные о текущих корзинах (как гостевых, так и пользовательских) и включает атрибуты.

    Атрибуты:
    - Уникальный идентификатор корзины (_id)
    - Идентификатор пользователя (user_id) и session_id для гостей
    - Список товаров (items): массив документов { product_id, quantity }
    - Статус корзины (status): "active" | "ordered" | "abandoned"
    - Дата и время создания (created_at)
    - Дата и время последнего обновления (updated_at)
    - Время удаления (TTL) (expires_at) — для автоматической очистки старых корзин

    Основные операции:
    - Создание корзины, когда заходит гость или новый пользователь
    - Получение текущей корзины по фильтру { session_id, status:"active" } или { user_id, status:"active" }
    - Добавление или замена товара в корзине
    - Удаление товара из корзины
    - Слияние гостевой корзины в пользовательскую, если пользователь залогинится:
        - прочитать гостевую { session_id, status:"active" }
        - добавить её items в корзину { user_id, status:"active" }
        - отметить гостевую как abandoned
    - Отметка корзины как заказанной
    """

    client_id: Optional[PydanticObjectId] = None
    session_id: Optional[PydanticObjectId] = None
    contents: Dict[PydanticObjectId, int] = {}  # {product_id: quantity}
    status: CartStatus = CartStatus.ACTIVE
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    expires_at: Optional[datetime] = None

    class Settings:
        indexes = [
            [("status", pymongo.HASHED)],
            [("client_id", pymongo.HASHED)],
            [("session_id", pymongo.HASHED)],
            [("created_at", pymongo.DESCENDING)],
        ]


class ProductOrder(Document):
    """Дополнительная ассоциативная таблица "Товары-Заказы" (для удобства поиска)"""

    product_id: PydanticObjectId
    order_id: PydanticObjectId

    class Settings:
        indexes = [[("product_id", pymongo.HASHED)], [("order_id", pymongo.HASHED)]]


class ProductStock(Document):
    """
    Дополительная таблица "Запас товара на складе"

    Атрибуты:
    - Уникальный идентификатор товара
    - Уникальный идентификатор склада
    - Количество товара
    - Время последнего обновления

    """

    product_id: PydanticObjectId
    warehouse_id: PydanticObjectId
    quantity: int
    updated_at: datetime = datetime.now()

    class Settings:
        indexes = [
            [("product_id", pymongo.HASHED)],
            [("warehouse_id", pymongo.HASHED)],
            [("updated_at", pymongo.DESCENDING)],
        ]


class Sample(Document):
    name: str


async def init_mongo_db():
    # Create Async PyMongo client
    client = AsyncMongoClient("mongodb://localhost:27017")

    # Initialize beanie with the Sample document class and a database
    await init_beanie(
        database=client.mega_shop,
        document_models=[GeoPoint, Product, Cart, Order, ProductOrder, Warehouse, ProductStock],
    )


async def upload_some_products():
    # 1. Создаем геоточки для складов
    moscow_geo = GeoPoint(geohash="ucfv0j", lat=55.7558, lon=37.6176)
    novosibirsk_geo = GeoPoint(geohash="v2e8k7", lat=55.0084, lon=82.9357)
    await moscow_geo.insert()
    await novosibirsk_geo.insert()
    print("Созданы геоточки для городов")

    # 2. Создаем склады
    moscow_warehouse = Warehouse(location=moscow_geo, name="Склад Москва", description="Основной склад в Москве")
    novosibirsk_warehouse = Warehouse(
        location=novosibirsk_geo, name="Склад Новосибирск", description="Региональный склад в Новосибирске"
    )
    await moscow_warehouse.insert()
    await novosibirsk_warehouse.insert()
    print("Созданы склады в Москве и Новосибирске")

    # 3. Создаем 5-6 продуктов
    products = [
        Product(
            name="iPhone 15 Pro",
            description="Флагманский смартфон Apple с чипом A17 Pro",
            price=99999.0,
            extra_info={"color": "Natural Titanium", "storage": "256GB"},
        ),
        Product(
            name="MacBook Air M2",
            description="Ультрабук Apple с процессором M2",
            price=129999.0,
            extra_info={"color": "Space Gray", "ram": "16GB", "storage": "512GB"},
        ),
        Product(
            name="AirPods Pro 2",
            description="Беспроводные наушники с активным шумоподавлением",
            price=24999.0,
            extra_info={"color": "White", "features": ["ANC", "Spatial Audio"]},
        ),
        Product(
            name="iPad Pro 12.9",
            description="Профессиональный планшет с M2 чипом",
            price=89999.0,
            extra_info={"color": "Space Gray", "storage": "512GB", "cellular": True},
        ),
        Product(
            name="Apple Watch Series 9",
            description="Умные часы с GPS и Cellular",
            price=39999.0,
            extra_info={"color": "Midnight", "size": "45mm", "band": "Sport Loop"},
        ),
        Product(
            name="Magic Keyboard",
            description="Беспроводная клавиатура для Mac",
            price=12999.0,
            extra_info={"color": "Silver", "layout": "RU", "backlight": True},
        ),
    ]

    # Сохраняем продукты в базу данных
    for product in products:
        await product.insert()
        print(f"Создан продукт: {product.name} - {product.price} руб.")

    # 4. Создаем информацию о запасах на складах
    stock_data = [
        # Продукты только в Москве
        {"product": products[0], "warehouse": moscow_warehouse, "quantity": 50},  # iPhone
        {"product": products[1], "warehouse": moscow_warehouse, "quantity": 25},  # MacBook
        # Продукты только в Новосибирске
        {"product": products[2], "warehouse": novosibirsk_warehouse, "quantity": 30},  # AirPods
        {"product": products[3], "warehouse": novosibirsk_warehouse, "quantity": 15},  # iPad
        # Продукты на обоих складах
        {"product": products[4], "warehouse": moscow_warehouse, "quantity": 40},  # Apple Watch
        {"product": products[4], "warehouse": novosibirsk_warehouse, "quantity": 20},  # Apple Watch
        {"product": products[5], "warehouse": moscow_warehouse, "quantity": 60},  # Magic Keyboard
        {"product": products[5], "warehouse": novosibirsk_warehouse, "quantity": 35},  # Magic Keyboard
    ]

    for stock in stock_data:
        product_stock = ProductStock(
            product_id=stock["product"].id, warehouse_id=stock["warehouse"].id, quantity=stock["quantity"]
        )
        await product_stock.insert()
        print(f"Запас: {stock['product'].name} на складе {stock['warehouse'].name} - {stock['quantity']} шт.")

    # 5. Создаем 2-3 заказа
    orders = [
        Order(
            client_id=PydanticObjectId(),
            contents={
                products[0].id: (2, products[0].price),  # 2 iPhone
                products[2].id: (1, products[2].price),  # 1 AirPods
            },
            total_sum=2 * products[0].price + products[2].price,
            dest_location=moscow_geo,
        ),
        Order(
            client_id=PydanticObjectId(),
            contents={
                products[1].id: (1, products[1].price),  # 1 MacBook
                products[4].id: (1, products[4].price),  # 1 Apple Watch
            },
            total_sum=products[1].price + products[4].price,
            dest_location=novosibirsk_geo,
        ),
        Order(
            client_id=PydanticObjectId(),
            contents={
                products[3].id: (1, products[3].price),  # 1 iPad
                products[5].id: (2, products[5].price),  # 2 Magic Keyboard
            },
            total_sum=products[3].price + 2 * products[5].price,
            dest_location=moscow_geo,
        ),
    ]

    for i, order in enumerate(orders, 1):
        await order.insert()
        print(f"Создан заказ #{i} на сумму {order.total_sum} руб.")

        # 6. Создаем записи в ProductOrder для каждого товара в заказе
        for product_id in order.contents.keys():
            product_order = ProductOrder(product_id=product_id, order_id=order.id)
            await product_order.insert()
            print(f"  - Связь товар-заказ: {product_id} -> {order.id}")


async def main():
    await init_mongo_db()
    print("БД инициализирована")
    await upload_some_products()
    print("Данные загружены в БД")


if __name__ == "__main__":
    asyncio.run(main())
