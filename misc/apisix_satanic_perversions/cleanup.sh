#!/bin/bash
# cleanup.sh - Очистка развёртывания

set -e

echo "🧹 Очистка развёртывания APISIX + Consul + Hello World..."

NAMESPACE=${1:-default}

if [ "$NAMESPACE" != "default" ]; then
    kubectl config set-context --current --namespace=$NAMESPACE
fi

echo "🗑️  Удаление компонентов..."

# Удаляем в обратном порядке
kubectl delete deployment apisix --ignore-not-found=true
kubectl delete statefulset hello-world --ignore-not-found=true
kubectl delete statefulset consul --ignore-not-found=true
kubectl delete statefulset etcd --ignore-not-found=true

kubectl delete service apisix --ignore-not-found=true
kubectl delete service hello-world --ignore-not-found=true
kubectl delete service consul --ignore-not-found=true
kubectl delete service etcd --ignore-not-found=true

kubectl delete configmap apisix-config --ignore-not-found=true
kubectl delete configmap hello-world-nginx-config --ignore-not-found=true
kubectl delete configmap hello-world-html --ignore-not-found=true

# Удаляем PVC
echo "🗑️  Удаление постоянных томов..."
kubectl delete pvc --all --ignore-not-found=true

echo "✅ Очистка завершена!"
