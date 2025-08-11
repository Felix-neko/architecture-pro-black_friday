#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm repo add bitnami https://charts.bitnami.com/bitnami
kubectl create namespace redis
kubectl apply -f $BASEDIR/node_port_services.yaml -n redishe
helm install my-redis-cluster bitnami/redis-cluster  --namespace redis  --values values-redis.yaml

