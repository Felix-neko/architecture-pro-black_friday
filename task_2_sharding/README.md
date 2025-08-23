# Задание 2: только шардирование

```bash
docker compose up -d
```

Когда всё стартует открываем http://localhost:8080 и проверяем, что выдёт подобное: 

```json
{
  "mongo_topology_type": "Sharded",
  "mongo_replicaset_name": null,
  "mongo_db": "test_db",
  "read_preference": "Primary()",
  "mongo_nodes": [
    [
      "mongos",
      27017
    ]
  ],
  "mongo_primary_host": null,
  "mongo_secondary_hosts": [],
  "mongo_is_primary": true,
  "mongo_is_mongos": true,
  "collections": {},
  "shards": {
    "shard1rs": "shard1rs/shard1:27017",
    "shard2rs": "shard2rs/shard2:27017",
    "shard3rs": "shard3rs/shard3:27017"
  },
  "cache_enabled": false,
  "status": "OK",
  "replica_status": "No Replicas"
}
```

Дальше ставим newman и прогоняем набор тестов:

```bash
npm install newman
npx newman run pymongo_api_tests.postman_collection.json
```


## Что проверяется в Postman-тестах
В этих тестах мы делаем следующее:
- проверяем, что http://localhost:8080 что-то выдаёт;
- делаем POST-запрос на http://localhost:8080/helloDoc1/create и так создаём себе тестовую коллекцию;
- делаем GET-запрос на http://localhost:8080/helloDoc1/users и проверяем, что коллекция действительно загрузилась, и в ней действительно 1000 элементов;
- делаем GET-запрос на метод получения статистики по созданной тестовой колелкции http://localhost:8080/helloDoc1/stats и проверяем, что она точно шардирована, что в каждом шарде что-то лежит, и общее число документов в шардах 1000 
