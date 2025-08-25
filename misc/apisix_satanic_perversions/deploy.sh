#!/bin/bash
# deploy.sh - Основной скрипт развёртывания

set -e

echo "🚀 Развёртывание APISIX + Consul + Hello World на Kubernetes"

# Проверяем доступность kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl не найден. Установите kubectl и настройте доступ к кластеру."
    exit 1
fi

# Проверяем подключение к кластеру
echo "📡 Проверка подключения к Kubernetes кластеру..."
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Не удается подключиться к Kubernetes кластеру."
    exit 1
fi

echo "✅ Подключение к кластеру установлено"

# Создаем namespace (опционально)
NAMESPACE=${1:-default}
if [ "$NAMESPACE" != "default" ]; then
    echo "📝 Создание namespace: $NAMESPACE"
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    kubectl config set-context --current --namespace=$NAMESPACE
fi

# Применяем все манифесты
echo "📦 Развёртывание компонентов..."

# 1. Разворачиваем etcd
echo "  - Развёртывание etcd..."
kubectl apply -f etcd.yaml

# 2. Разворачиваем Consul
echo "  - Развёртывание Consul..."
kubectl apply -f consul.yaml

# 3. Разворачиваем Hello World сервис
echo "  - Развёртывание Hello World сервиса..."
kubectl apply -f hello-world-configmaps.yaml
kubectl apply -f hello-world-service.yaml
kubectl apply -f hello-world-statefulset.yaml

# Ожидаем готовности etcd
echo "⏳ Ожидание готовности etcd..."
kubectl wait --for=condition=ready pod -l app=etcd --timeout=300s

# 4. Разворачиваем APISIX
echo "  - Развёртывание APISIX API Gateway..."
kubectl apply -f apisix-configmap.yaml
kubectl apply -f apisix-service.yaml
kubectl apply -f apisix-deployment.yaml

echo "⏳ Ожидание готовности всех компонентов..."

# Ожидаем готовности всех подов
kubectl wait --for=condition=ready pod -l app=consul --timeout=300s
kubectl wait --for=condition=ready pod -l app=hello-world --timeout=300s
kubectl wait --for=condition=ready pod -l app=apisix --timeout=300s

echo "✅ Все компоненты развёрнуты успешно!"

# Показываем информацию о развёртывании
echo ""
echo "📋 Информация о развёртывании:"
echo "================================"

# Запускаем скрипт проверки статуса
./status.sh
