# Задание 7. Проектирование схем коллекций для шардирования данных


В этом задании я сделал прототип коллекций данных на `beanie` (см. [`models.py`](./models.py)), а также сделал логическую ER-схему для них (генерация Claude Sonnet 4 + небольшая доработка).

![ER-диаграмма для коллекций данных](https://www.plantuml.com/plantuml/png/fLR9Sjim3BthArXViime7v39-98sdKodJQOvj3SF8y4M6vfGIIYf6-VV2rAB9LbUr9nCaS33zW3uv0Dbi0IHQwbCv9wKoQMLIw6L0Lhb8D1IXb5q8ZuPKgJ0HU0FAp7v37YFoj14I2SMWE8r4k9Sp5GgBiNTuoz8w3OLLrVtNwPJ_hdz-7CwPOau3cAia4cNiQWZgymYN6f9V37NAAdyHjDylqMDvH_IGeQ5Ws3wfVuQvu2H77R7UWekiIed5Qms3neJwU-sS6yOj-tMjIHOe5q5hvBgunrEjPvtEDSshXLKjKZ2yRtPWALKUiYNF4FJaxMmK8x0GZeB5KmvU5ACM6kr7Bstc1P9wMbUdj_hQcvL0ZLHEbbZYirSaUUS4SS2ZuYwzRwZu7Nf1WlUKeS_PELCcJcos4ULq42O3uJ9KplMcVCtuoAkLG_uSxvfXSEYlmjPUdefk8V3LP7xkXrHmZkRWWr1eJ-D2wPavs474mjxlF4IZYGLlgp1duVm5Hu8IMgk-x8pJ18qn9PTNQnGVvgDQ6zRzHSVniHyNCGEd1joOo1UxqaPRZTZMm4UayN1gWTsvyg2ExgXDwIewVeVv3YQwG5xlzYRtrhVGOVgkapbl2eKPUBQuik94pU890mpnJzxqNgVCNr4is74wPs1c33-AitgBF9hRhsEOtnjhPrBCGaa2acSUAXw4tYeAZqze6OzL6Zr96Iiwadz1LU2bUESeKAA-q3bQmLJffn1U9ydM_gUDtlL0xDP6rzCgLixluaZ3BGUIEryDvPgqZ5ScC9X47hCJMxtesuIl0kN3xOAibsyeJIr2jVaA0MjdiFI8jmHxH3KZcWRM6KINQICgan0BJ7sOvRAkn1zO_FVCnzfRVmDBoukrkjGCM_a6n9lk3bQuJ9fKx-nUPzv9gqY9Za8gnOP2PotcVRWHI4LZolVdvEUO6E-9ROPPQV-tnkaPtsjcaAZbBOYRcatdNv8kQ45vwBC0WF4mYsbrk8PTR64lcgdXxjg5kPC3SF_AtZsoRwYfzD8bQhJHldNJ8c3jgBe7m00)
_ER-диаграмма для коллекций данных_


## Описание коллекций

### Основные коллекции данных:

* **`Product`** -- хранит сведения о товарах (наименование, цена, категория, наличие поставок, дополнительные атрибуты)
* **`Order`** -- заказы клиентов с информацией о товарах, статусе, сумме и геозоне доставки
* **`Cart`** -- данные о текущих корзинах (как гостевых, так и пользовательских) с поддержкой TTL для автоочистки
* **`Client`** -- клиенты магазина с контактной информацией и датой регистрации
* **`Category`** -- категории товаров для классификации продукции

### Вспомогательные коллекции:

* **`ProductOrder`** -- ассоциативная таблица "Товары-Заказы" для удобства поиска
* **`ProductStock`** -- запас товара на складе с информацией о количестве и времени обновления
* **`Warehouse`** -- склады с географическим расположением
* **`GeoPoint`** -- географические точки с координатами и geohash

## Стратегия шардирования

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