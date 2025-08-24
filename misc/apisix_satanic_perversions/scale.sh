#!/bin/bash
# scale.sh - Скрипт для масштабирования hello world сервиса

set -e

REPLICAS=${1}

if [ -z "$REPLICAS" ]; then
    echo "❌ Использование: $0 <количество_реплик>"
    echo "   Количество реплик должно быть от 1 до 10"
    exit 1
fi

# Проверяем диапазон
if [ "$REPLICAS" -lt 1 ] || [ "$REPLICAS" -gt 10 ]; then
    echo "❌ Количество реплик должно быть от 1 до 10"
    exit 1
fi

echo "📈 Масштабирование hello-world StatefulSet до $REPLICAS реплик..."

# Масштабируем StatefulSet
kubectl scale statefulset hello-world --replicas=$REPLICAS

echo "⏳ Ожидание готовности подов..."
kubectl rollout status statefulset/hello-world --timeout=300s

echo "✅ Масштабирование завершено успешно!"

echo ""
echo "📊 Статус hello-world подов:"
kubectl get pods -l app=hello-world

echo ""
echo "🔍 Подробная информация:"
kubectl get statefulset hello-world
