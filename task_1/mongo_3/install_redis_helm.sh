#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm repo add ot-helm https://ot-container-kit.github.io/helm-charts/
helm repo update
helm create namespace redis
helm upgrade redis-operator ot-helm/redis-operator \
  --install --create-namespace --namespace redis

helm install my-redis ot-helm/redis-cluster --namespace redis --values $BASEDIR/values-redis-ot.yaml

kubectl apply -f $BASEDIR/haproxy-redis-config.yaml -n redis
kubectl apply -f $BASEDIR/haproxy-statefulset.yaml -n redis