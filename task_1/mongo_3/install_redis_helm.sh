#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

#helm repo add ot-helm https://ot-container-kit.github.io/helm-charts/

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

kubectl create namespace redis

helm install my-redis bitnami/redis-cluster --namespace redis --values $BASEDIR/values-redis-bitnami.yaml


#helm upgrade redis-operator ot-helm/redis-operator --install --namespace redis

#helm install my-redis ot-helm/redis-cluster --namespace redis --values $BASEDIR/values-redis-ot.yaml

#kubectl apply -f $BASEDIR/haproxy-redis-config.yaml -n redis
#kubectl apply -f $BASEDIR/haproxy-statefulset.yaml -n redis

#kubectl apply -f $BASEDIR/redis-individual-nodeports.yaml -n redis