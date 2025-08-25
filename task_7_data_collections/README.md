# Задание 7. Проектирование схем коллекций для шардирования данных


В этом задании я сделал прототип коллекций данных на `beanie` (см. [`models.py`](./models.py)), а также сделал логическую ER-схему для них (генерация Claude Sonnet 4 + небольшая доработка).

![ER-диаграмма для коллекций данных](https://www.plantuml.com/plantuml/png/fLR9Rjim4BthArXViW3E1mI1BsbJ14MRe3cqDuEHnXORcgEIewHkd7_la9HaMPONDITncNcpFSxev0Fbi01HQAbCufwKAQIL2w6L0LeM8D1IZabo8ZuPKgJ09U0NIp7w37YFoj18I2VcWE8r4U9SJ5KcBiNTuoz8wJOJLrVtNoOJ_jn-_3cPiCHu7CHO8PSkPr57LfbvEDII-62cKLBSesdsRqbZ-OUqa6Ff89X-gNV3732Imzwmde5BhIf81QlDXSPK-hCjt1l6RRjrBGdcQ9V1gxJQlCEfrlKEvzh6jOAg5cbOlZSRi91Az_bIv6WwiXRcoX5OoAQXWXa7JueHQwsMe_SMipADdXPn_LvN2wjIg8dIKjXHqBeqlGLjgSCVidAgp0nPxADAgIUC1yBqgHtBrFcJOH7LgWVyELzJ_R3exr96Joy5lz5mL1Q-BaUKwCvcO4DGw5V3WediE-nWQc6FDrx2aQJIUHZlnKFOXGj2adhgoiL6iqZH45jsTR52_MawuFdQwltmOaZCnqNimBa-DthYzPx4S3SpjXNWCLdihNfWTw4ikACVx9eKDLt_Wnn7CprWxnTxyrFfE-XGNPUhWaU1ebnSMtmvSU86aOHXflXhBrhFAwQFQ2Q8EBqpC2OSVvLcUPRuCRPQZSVusXehbs8KI1IIEF9GTQVtK5LwEa1D-w_Gwax7MDML-WikWiLspL0XnLsWU5l1n9Gp2C_hT4lVysQlUc0sQ-EBYRgry-iuGaFhWDJERyPITJg6uq4UDm5pdTlzgEi4xyBbXQs2R1UlBqsjmZKvoa2hvp2K27T4smUr8ze6LfbKbncZAXDG8yP-pAYy2z4_RFxzyf7Mnj_muk9YjGeLyqQ-8O4JCxJ2vT9cVYBpFFDCMYPCSX1MpNCIE6ipxS6BGYOUb_vzZZg2ZVcMsBgLdVg_CyZEkberXGOfRKNSqcvU-Y7bXXQSYvW51XWBjv1QYsVKvGAwgXjlU5FDmeofOVY_WNkVx2fwEWrKgLxQ8F-QBd7GLfBy0m00)
_ER-диаграмма для коллекций данных_


Шардируемые коллекции:
* `Product` -- хеш-шардирование по `_id`
* `Order` -- хеш-шардирование по `client_id` (hashed) - заказы распределяются по пользователям
* `Cart` -- хеш-шардирование по `client_id`
* `ProductOrder` → хэш-шардирование по `order_id`

Нешардируемые коллекции:
* `ProductStock` (т.к. малый объем и частые обновления);
* `Client` (малый объём);
* `Category`, `Warehouse`, `GeoPoint` -- справочники, тоже малый объём.


Для более равномерного распределения данных по шардам постараемся избегать шардирования по диапазонам.