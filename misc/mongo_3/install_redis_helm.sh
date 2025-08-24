#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

kubectl create namespace redis

helm install my-redis bitnami/redis-cluster --namespace redis --values $BASEDIR/values-redis-bitnami.yaml
kubectl apply -f $BASEDIR/redis-individual-nodeports-bitnami.yaml -n redis

kubectl apply -f $BASEDIR/haproxy-redis-config.yaml -n redis
kubectl apply -f $BASEDIR/haproxy-statefulset.yaml -n redis
