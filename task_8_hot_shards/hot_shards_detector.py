import asyncio
import pymongo
from pymongo import MongoClient
from pymongo.errors import OperationFailure, ConnectionFailure
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import json
from collections import defaultdict

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HotShardDetector:
    def __init__(self, connection_url: str, database_name: str = None):
        self.connection_url = connection_url
        self.database_name = database_name
        self.client = None
        self.admin_db = None
        self.is_sharded_cluster = False

    def connect(self):
        """Подключение к MongoDB"""
        try:
            self.client = MongoClient(self.connection_url, serverSelectionTimeoutMS=5000)
            self.admin_db = self.client.admin

            # Проверка подключения и типа кластера
            hello_result = self.admin_db.command("hello")
            self.is_sharded_cluster = hello_result.get("msg") == "isdbgrid"

            if not self.is_sharded_cluster:
                logger.warning("⚠️ Подключение не к шардированному кластеру. Некоторые функции будут недоступны.")
            else:
                logger.info("✅ Успешно подключились к шардированному кластеру MongoDB")

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
            raise

    def get_shard_info(self) -> Dict[str, Any]:
        """Получение информации о шардах"""
        if not self.is_sharded_cluster:
            logger.warning("Функция доступна только для шардированных кластеров")
            return {}

        try:
            # Получаем список шардов
            shards_result = self.admin_db.command("listShards")
            shards_info = {}

            for shard in shards_result["shards"]:
                shard_id = shard["_id"]
                shard_host = shard["host"]
                shard_state = shard.get("state", "unknown")

                shards_info[shard_id] = {
                    "id": shard_id,
                    "host": shard_host,
                    "state": shard_state,
                    "tags": shard.get("tags", {})
                }

            logger.info(f"📊 Найдено шардов: {len(shards_info)}")
            return shards_info

        except Exception as e:
            logger.error(f"❌ Ошибка при получении информации о шардах: {e}")
            return {}

    def get_shard_distribution(self, database_name: str = None) -> Dict[str, Any]:
        """Анализ распределения данных по шардам"""
        if not self.is_sharded_cluster:
            return {}

        db_name = database_name or self.database_name
        if not db_name:
            logger.error("❌ Не указана база данных для анализа")
            return {}

        try:
            db = self.client[db_name]
            distribution_data = {}

            # Получаем список шардированных коллекций
            config_db = self.client.config
            sharded_collections = config_db.collections.find({"_id": {"$regex": f"^{db_name}\."}})

            for collection_doc in sharded_collections:
                collection_full_name = collection_doc["_id"]
                collection_name = collection_full_name.split(".", 1)[1]
                shard_key = collection_doc["key"]

                logger.info(f"🔍 Анализируем коллекцию: {collection_name}")

                # Получаем статистику по шардам для коллекции
                try:
                    shard_stats = db.command("collStats", collection_name)
                    if "shards" in shard_stats:
                        collection_distribution = {}
                        total_docs = 0
                        total_size = 0

                        for shard_id, stats in shard_stats["shards"].items():
                            doc_count = stats.get("count", 0)
                            data_size = stats.get("size", 0)
                            avg_obj_size = stats.get("avgObjSize", 0)

                            collection_distribution[shard_id] = {
                                "documents": doc_count,
                                "dataSize": data_size,
                                "avgObjSize": avg_obj_size,
                                "storageSize": stats.get("storageSize", 0),
                                "indexSize": stats.get("totalIndexSize", 0)
                            }

                            total_docs += doc_count
                            total_size += data_size

                        # Вычисляем процентное распределение
                        for shard_id in collection_distribution:
                            docs = collection_distribution[shard_id]["documents"]
                            size = collection_distribution[shard_id]["dataSize"]

                            collection_distribution[shard_id]["docPercentage"] = (docs / total_docs * 100) if total_docs > 0 else 0
                            collection_distribution[shard_id]["sizePercentage"] = (size / total_size * 100) if total_size > 0 else 0

                        distribution_data[collection_name] = {
                            "shardKey": shard_key,
                            "totalDocuments": total_docs,
                            "totalDataSize": total_size,
                            "shardDistribution": collection_distribution
                        }

                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить статистику для коллекции {collection_name}: {e}")

            return distribution_data

        except Exception as e:
            logger.error(f"❌ Ошибка при анализе распределения данных: {e}")
            return {}

    def get_shard_operations_stats(self) -> Dict[str, Any]:
        """Получение статистики операций по шардам"""
        if not self.is_sharded_cluster:
            return {}

        try:
            shard_ops_stats = {}

            # Получаем статистику mongos
            mongos_stats = self.admin_db.command("serverStatus")

            if "sharding" in mongos_stats:
                sharding_stats = mongos_stats["sharding"]

                # Статистика по операциям
                if "lastSeenConfigServerOpTime" in sharding_stats:
                    shard_ops_stats["configServerOpTime"] = sharding_stats["lastSeenConfigServerOpTime"]

                # Статистика балансировщика
                if "balancer" in sharding_stats:
                    shard_ops_stats["balancerStats"] = sharding_stats["balancer"]

            # Получаем статистику по операциям из profiler (если включен)
            try:
                profiler_stats = self.get_profiler_stats()
                if profiler_stats:
                    shard_ops_stats["profilerStats"] = profiler_stats
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить статистику профайлера: {e}")

            # Получаем текущие операции
            try:
                current_ops = self.admin_db.command("currentOp")
                ops_by_shard = defaultdict(list)

                for op in current_ops.get("inprog", []):
                    shard_info = op.get("shard")
                    if shard_info:
                        ops_by_shard[shard_info].append({
                            "opid": op.get("opid"),
                            "op": op.get("op"),
                            "ns": op.get("ns"),
                            "duration": op.get("secs_running", 0),
                            "command": op.get("command", {}).get("find") or op.get("command", {}).get("update") or "other"
                        })

                shard_ops_stats["currentOperations"] = dict(ops_by_shard)

            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить текущие операции: {e}")

            return shard_ops_stats

        except Exception as e:
            logger.error(f"❌ Ошибка при получении статистики операций: {e}")
            return {}

    def get_profiler_stats(self) -> Dict[str, Any]:
        """Получение статистики из профайлера базы данных"""
        if not self.database_name:
            return {}

        try:
            db = self.client[self.database_name]

            # Проверяем, включен ли профайлер
            profiler_status = db.command("profile", -1)
            if profiler_status.get("was", 0) == 0:
                logger.info("📊 Профайлер отключен. Включите профайлер для более детальной статистики.")
                return {}

            # Получаем последние операции из системной коллекции профайлера
            profiler_collection = db.system.profile

            # Анализируем операции за последний час
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)

            pipeline = [
                {"$match": {"ts": {"$gte": one_hour_ago}}},
                {"$group": {
                    "_id": "$ns",
                    "count": {"$sum": 1},
                    "avgDuration": {"$avg": "$millis"},
                    "maxDuration": {"$max": "$millis"},
                    "totalDuration": {"$sum": "$millis"}
                }},
                {"$sort": {"totalDuration": -1}}
            ]

            profiler_stats = list(profiler_collection.aggregate(pipeline))
            return {"operations": profiler_stats}

        except Exception as e:
            logger.warning(f"⚠️ Ошибка при получении статистики профайлера: {e}")
            return {}

    def detect_hot_shards(self, distribution_data: Dict[str, Any], threshold_percentage: float = 30.0) -> Dict[str, Any]:
        """Обнаружение горячих шардов на основе распределения данных"""
        hot_shards_analysis = {
            "hotShards": [],
            "allShards": [],  # Новое поле для всех шардов
            "recommendations": [],
            "summary": {}
        }

        if not distribution_data:
            logger.warning("⚠️ Нет данных для анализа горячих шардов")
            return hot_shards_analysis

        all_shard_loads = defaultdict(lambda: {"documents": 0, "dataSize": 0, "collections": []})

        # Агрегируем данные по всем шардам и коллекциям
        for collection_name, collection_data in distribution_data.items():
            shard_distribution = collection_data.get("shardDistribution", {})

            for shard_id, shard_stats in shard_distribution.items():
                all_shard_loads[shard_id]["documents"] += shard_stats.get("documents", 0)
                all_shard_loads[shard_id]["dataSize"] += shard_stats.get("dataSize", 0)
                all_shard_loads[shard_id]["collections"].append({
                    "name": collection_name,
                    "documents": shard_stats.get("documents", 0),
                    "docPercentage": shard_stats.get("docPercentage", 0),
                    "sizePercentage": shard_stats.get("sizePercentage", 0)
                })

        if not all_shard_loads:
            return hot_shards_analysis

        # Вычисляем средние значения
        total_documents = sum(load["documents"] for load in all_shard_loads.values())
        total_data_size = sum(load["dataSize"] for load in all_shard_loads.values())
        num_shards = len(all_shard_loads)

        avg_documents_per_shard = total_documents / num_shards if num_shards > 0 else 0
        avg_size_per_shard = total_data_size / num_shards if num_shards > 0 else 0

        # Анализируем каждый шард
        hot_shards = []
        all_shards_analysis = []

        for shard_id, load_data in all_shard_loads.items():
            doc_percentage = (load_data["documents"] / total_documents * 100) if total_documents > 0 else 0
            size_percentage = (load_data["dataSize"] / total_data_size * 100) if total_data_size > 0 else 0

            is_hot = doc_percentage > threshold_percentage or size_percentage > threshold_percentage

            shard_analysis = {
                "shardId": shard_id,
                "isHot": is_hot,
                "documentCount": load_data["documents"],
                "documentPercentage": round(doc_percentage, 2),
                "dataSize": load_data["dataSize"],
                "dataSizePercentage": round(size_percentage, 2),
                "collections": load_data["collections"],
                "hotnessFactor": max(doc_percentage, size_percentage) / (100 / num_shards) if num_shards > 0 else 0,
                "documentsDeviationFromAvg": round(((load_data["documents"] - avg_documents_per_shard) / avg_documents_per_shard * 100), 1) if avg_documents_per_shard > 0 else 0,
                "sizeDeviationFromAvg": round(((load_data["dataSize"] - avg_size_per_shard) / avg_size_per_shard * 100), 1) if avg_size_per_shard > 0 else 0
            }

            # Добавляем во все шарды
            all_shards_analysis.append(shard_analysis)

            # Добавляем в горячие, если превышает порог
            if is_hot:
                hot_shards.append(shard_analysis)

        # Сортируем все шарды по фактору нагрузки
        all_shards_analysis.sort(key=lambda x: x["hotnessFactor"], reverse=True)
        hot_shards.sort(key=lambda x: x["hotnessFactor"], reverse=True)

        hot_shards_analysis["hotShards"] = hot_shards
        hot_shards_analysis["allShards"] = all_shards_analysis
        hot_shards_analysis["summary"] = {
            "totalShards": num_shards,
            "hotShardsCount": len(hot_shards),
            "totalDocuments": total_documents,
            "totalDataSize": total_data_size,
            "averageDocumentsPerShard": round(avg_documents_per_shard, 2),
            "averageDataSizePerShard": round(avg_size_per_shard, 2),
            "threshold": threshold_percentage
        }

        # Генерируем рекомендации
        recommendations = []
        if hot_shards:
            recommendations.append("🔥 Обнаружены горячие шарды! Рекомендации:")
            recommendations.append("1. Рассмотрите возможность изменения ключа шардирования")
            recommendations.append("2. Проверьте, нет ли монотонно возрастающих значений в ключе шардирования")
            recommendations.append("3. Рассмотрите использование хешированного шардирования")
            recommendations.append("4. Разделите большие чанки вручную, если автоматическое разделение не работает")

            # Специфичные рекомендации для каждого горячего шарда
            for hot_shard in hot_shards:
                recommendations.append(f"   - Шард {hot_shard['shardId']}: {hot_shard['hotnessFactor']:.1f}x превышение нормы")
        else:
            recommendations.append("✅ Горячие шарды не обнаружены. Распределение данных выглядит сбалансированным.")

        hot_shards_analysis["recommendations"] = recommendations

        return hot_shards_analysis

    def get_chunk_distribution(self) -> Dict[str, Any]:
        """Анализ распределения чанков по шардам"""
        if not self.is_sharded_cluster:
            return {}

        try:
            config_db = self.client.config
            chunks_collection = config_db.chunks

            # Группируем чанки по шардам
            pipeline = [
                {"$group": {
                    "_id": {"shard": "$shard", "ns": "$ns"},
                    "chunkCount": {"$sum": 1}
                }},
                {"$group": {
                    "_id": "$_id.shard",
                    "collections": {
                        "$push": {
                            "ns": "$_id.ns",
                            "chunks": "$chunkCount"
                        }
                    },
                    "totalChunks": {"$sum": "$chunkCount"}
                }},
                {"$sort": {"totalChunks": -1}}
            ]

            chunk_distribution = list(chunks_collection.aggregate(pipeline))

            return {
                "chunkDistribution": chunk_distribution,
                "totalShards": len(chunk_distribution)
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при анализе распределения чанков: {e}")
            return {}

    def print_analysis_report(self, shard_info: Dict, distribution_data: Dict, hot_shards_analysis: Dict, chunk_data: Dict, ops_stats: Dict):
        """Вывод детального отчета об анализе шардов"""
        print("\n" + "="*100)
        print("📊 ОТЧЕТ ПО АНАЛИЗУ ГОРЯЧИХ ШАРДОВ MONGODB")
        print("="*100)

        # Общая информация о кластере
        print(f"\n🏗️  ИНФОРМАЦИЯ О КЛАСТЕРЕ")
        print(f"   Тип: {'Шардированный кластер' if self.is_sharded_cluster else 'Одиночный экземпляр'}")
        if shard_info:
            print(f"   Количество шардов: {len(shard_info)}")
            for shard_id, info in shard_info.items():
                print(f"   - {shard_id}: {info['host']} ({info['state']})")

        # Детальное распределение документов по коллекциям и шардам
        if distribution_data:
            print(f"\n📋 ДЕТАЛЬНОЕ РАСПРЕДЕЛЕНИЕ ДОКУМЕНТОВ ПО КОЛЛЕКЦИЯМ И ШАРДАМ")
            print("-" * 100)

            # Сводная таблица по всем коллекциям
            print(f"\n📊 СВОДНАЯ ТАБЛИЦА ВСЕХ КОЛЛЕКЦИЙ")
            print(f"   {'Коллекция':<25} {'Всего документов':<18} {'Общий размер':<15} {'Ключ шардирования':<30}")
            print(f"   {'-'*25} {'-'*18} {'-'*15} {'-'*30}")

            for collection_name, collection_data in sorted(distribution_data.items()):
                total_docs = collection_data.get("totalDocuments", 0)
                total_size = collection_data.get("totalDataSize", 0)
                shard_key = str(collection_data.get("shardKey", {}))

                print(f"   {collection_name:<25} {total_docs:<18,} {self._format_bytes(total_size):<15} {shard_key:<30}")

            # Детальная информация по каждой коллекции
            for collection_name, collection_data in distribution_data.items():
                print(f"\n🗂️  Коллекция: {collection_name}")
                shard_distribution = collection_data.get("shardDistribution", {})
                total_docs = collection_data.get("totalDocuments", 0)
                total_size = collection_data.get("totalDataSize", 0)
                shard_key = collection_data.get("shardKey", {})

                print(f"   Ключ шардирования: {shard_key}")
                print(f"   Всего документов: {total_docs:,}")
                print(f"   Общий размер: {self._format_bytes(total_size)}")

                if shard_distribution:
                    print(f"\n   {'Шард':<20} {'Документы':<15} {'%':<8} {'Размер':<15} {'%':<8} {'Ср. размер':<12}")
                    print(f"   {'-'*20} {'-'*15} {'-'*8} {'-'*15} {'-'*8} {'-'*12}")

                    # Сортируем по количеству документов
                    sorted_shards = sorted(shard_distribution.items(),
                                           key=lambda x: x[1]['documents'], reverse=True)

                    for shard_id, stats in sorted_shards:
                        doc_count = stats.get("documents", 0)
                        doc_percentage = stats.get("docPercentage", 0)
                        data_size = stats.get("dataSize", 0)
                        size_percentage = stats.get("sizePercentage", 0)
                        avg_obj_size = stats.get("avgObjSize", 0)

                        # Маркируем неравномерное распределение
                        imbalance_marker = "⚠️" if doc_percentage > 40 or doc_percentage < 15 else "  "

                        print(f"{imbalance_marker} {shard_id:<18} {doc_count:<15,} {doc_percentage:<8.1f} "
                              f"{self._format_bytes(data_size):<15} {size_percentage:<8.1f} "
                              f"{self._format_bytes(avg_obj_size):<12}")

                print()

        # Сводная статистика
        if hot_shards_analysis.get("summary"):
            summary = hot_shards_analysis["summary"]
            print(f"\n📈 СВОДНАЯ СТАТИСТИКА")
            print(f"   Всего документов: {summary['totalDocuments']:,}")
            print(f"   Общий размер данных: {self._format_bytes(summary['totalDataSize'])}")
            print(f"   Среднее количество документов на шард: {summary['averageDocumentsPerShard']:,}")
            print(f"   Средний размер данных на шард: {self._format_bytes(summary['averageDataSizePerShard'])}")

        # Распределение чанков
        if chunk_data and chunk_data.get("chunkDistribution"):
            print(f"\n🧩 РАСПРЕДЕЛЕНИЕ ЧАНКОВ")
            chunk_distribution = chunk_data["chunkDistribution"]

            # Вычисляем общее количество чанков
            total_chunks = sum(shard_data.get("totalChunks", 0) for shard_data in chunk_distribution)
            avg_chunks_per_shard = total_chunks / len(chunk_distribution) if chunk_distribution else 0

            print(f"   Всего чанков: {total_chunks}")
            print(f"   Среднее количество чанков на шард: {avg_chunks_per_shard:.1f}")
            print(f"\n   {'Шард':<20} {'Чанки':<10} {'%':<8} {'Коллекции':<50}")
            print(f"   {'-'*20} {'-'*10} {'-'*8} {'-'*50}")

            for shard_data in sorted(chunk_distribution, key=lambda x: x.get("totalChunks", 0), reverse=True):
                shard_id = shard_data.get("_id", "unknown")
                total_chunks_shard = shard_data.get("totalChunks", 0)
                percentage = (total_chunks_shard / total_chunks * 100) if total_chunks > 0 else 0

                # Формируем список коллекций
                collections_info = []
                for coll in shard_data.get("collections", []):
                    ns = coll.get("ns", "unknown")
                    chunks_count = coll.get("chunks", 0)
                    if "." in ns:
                        ns = ns.split(".", 1)[1]
                    collections_info.append(f"{ns}({chunks_count})")

                collections_str = ", ".join(collections_info[:3])  # Первые 3 коллекции
                if len(shard_data.get("collections", [])) > 3:
                    collections_str += "..."

                print(f"   {shard_id:<20} {total_chunks_shard:<10} {percentage:<8.1f} {collections_str:<50}")

        # Анализ всех шардов
        all_shards = hot_shards_analysis.get("allShards", [])
        if all_shards:
            print(f"\n🔍 АНАЛИЗ ВСЕХ ШАРДОВ")
            print(f"   {'Шард':<15} {'Статус':<8} {'Документы':<15} {'% док':<8} {'Размер':<15} {'% размер':<10} {'Фактор':<8} {'Отклонение':<12}")
            print(f"   {'-'*15} {'-'*8} {'-'*15} {'-'*8} {'-'*15} {'-'*10} {'-'*8} {'-'*12}")

            for shard_analysis in all_shards:
                shard_id = shard_analysis['shardId']
                status = "🔥 ГОР" if shard_analysis['isHot'] else "✅ ОК"
                doc_count = shard_analysis['documentCount']
                doc_percentage = shard_analysis['documentPercentage']
                data_size = shard_analysis['dataSize']
                size_percentage = shard_analysis['dataSizePercentage']
                hotness_factor = shard_analysis['hotnessFactor']
                doc_deviation = shard_analysis['documentsDeviationFromAvg']

                # Определяем цветовой индикатор отклонения
                deviation_indicator = ""
                if abs(doc_deviation) > 50:
                    deviation_indicator = "⚠️"
                elif abs(doc_deviation) > 25:
                    deviation_indicator = "⚡"
                else:
                    deviation_indicator = "  "

                print(f"   {shard_id:<15} {status:<8} {doc_count:<15,} {doc_percentage:<8.1f} "
                      f"{self._format_bytes(data_size):<15} {size_percentage:<10.1f} "
                      f"{hotness_factor:<8.1f} {deviation_indicator}{doc_deviation:>+6.1f}%")

            print(f"\n   Легенда статусов:")
            print(f"   🔥 ГОР - Горячий шард (превышает {hot_shards_analysis['summary']['threshold']:.0f}% порог)")
            print(f"   ✅ ОК  - Нормальная нагрузка")
            print(f"   Отклонение: ⚠️ >50%, ⚡ >25% от среднего значения")

        # Горячие шарды
        hot_shards = hot_shards_analysis.get("hotShards", [])
        if hot_shards:
            print(f"\n🔥 ДЕТАЛЬНЫЙ АНАЛИЗ ГОРЯЧИХ ШАРДОВ ({len(hot_shards)})")
            for i, hot_shard in enumerate(hot_shards, 1):
                print(f"\n   {i}. Шард: {hot_shard['shardId']}")
                print(f"      Фактор нагрузки: {hot_shard['hotnessFactor']:.1f}x")
                print(f"      Документы: {hot_shard['documentCount']:,} ({hot_shard['documentPercentage']:.1f}%)")
                print(f"      Размер данных: {self._format_bytes(hot_shard['dataSize'])} ({hot_shard['dataSizePercentage']:.1f}%)")
                print(f"      Отклонение от среднего: документы {hot_shard['documentsDeviationFromAvg']:+.1f}%, размер {hot_shard['sizeDeviationFromAvg']:+.1f}%")

                if hot_shard['collections']:
                    print(f"      Коллекции с наибольшей нагрузкой:")
                    sorted_collections = sorted(hot_shard['collections'],
                                                key=lambda x: x['docPercentage'], reverse=True)
                    for coll in sorted_collections[:3]:  # Топ-3 коллекции
                        print(f"        - {coll['name']}: {coll['documents']:,} документов ({coll['docPercentage']:.1f}%)")
        else:
            print(f"\n✅ ГОРЯЧИЕ ШАРДЫ НЕ ОБНАРУЖЕНЫ")

        # Текущие операции
        if ops_stats.get("currentOperations"):
            current_ops = ops_stats["currentOperations"]
            print(f"\n⚡ ТЕКУЩИЕ ОПЕРАЦИИ ПО ШАРДАМ")
            for shard_id, operations in current_ops.items():
                if operations:
                    print(f"   {shard_id}: {len(operations)} активных операций")
                    long_running = [op for op in operations if op.get('duration', 0) > 10]
                    if long_running:
                        print(f"      ⚠️ Длительные операции (>10 сек): {len(long_running)}")

        # Рекомендации
        recommendations = hot_shards_analysis.get("recommendations", [])
        if recommendations:
            print(f"\n💡 РЕКОМЕНДАЦИИ")
            for recommendation in recommendations:
                print(f"   {recommendation}")

        print("\n" + "="*100)

    def _format_bytes(self, bytes_value: float) -> str:
        """Форматирование размера в удобочитаемый вид"""
        if bytes_value == 0:
            return "0 B"

        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                if unit == 'B':
                    return f"{int(bytes_value)} {unit}"
                else:
                    return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"

    def run_analysis(self, threshold_percentage: float = 30.0):
        """Запуск полного анализа горячих шардов"""
        try:
            logger.info("🚀 Начинаем анализ горячих шардов...")

            # Получаем информацию о шардах
            shard_info = self.get_shard_info()

            # Анализируем распределение данных
            distribution_data = self.get_shard_distribution()

            # Получаем статистику операций
            ops_stats = self.get_shard_operations_stats()

            # Анализируем распределение чанков
            chunk_data = self.get_chunk_distribution()

            # Обнаруживаем горячие шарды
            hot_shards_analysis = self.detect_hot_shards(distribution_data, threshold_percentage)

            # Выводим отчет
            self.print_analysis_report(shard_info, distribution_data, hot_shards_analysis, chunk_data, ops_stats)

            # Возвращаем результаты для программного использования
            return {
                "shardInfo": shard_info,
                "distributionData": distribution_data,
                "hotShardsAnalysis": hot_shards_analysis,
                "chunkData": chunk_data,
                "operationsStats": ops_stats
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при анализе: {e}")
            raise

    def close_connection(self):
        """Закрытие соединения"""
        if self.client:
            self.client.close()

def main():
    # Настройки подключения
    CONNECTION_URL = "mongodb://root:rootpass@minikube-docker:30000,minikube-docker:30001"  # URL для подключения к MongoDB
    DATABASE_NAME = "load_test_db"                # Имя базы данных для анализа
    THRESHOLD_PERCENTAGE = 25.0                   # Порог для определения горячих шардов (%)

    detector = HotShardDetector(CONNECTION_URL, DATABASE_NAME)

    try:
        # Подключение
        detector.connect()

        # Запуск анализа
        results = detector.run_analysis(THRESHOLD_PERCENTAGE)

        # Можно сохранить результаты в файл
        # with open(f"hot_shards_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
        #     json.dump(results, f, indent=2, default=str)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        detector.close_connection()

if __name__ == "__main__":
    main()