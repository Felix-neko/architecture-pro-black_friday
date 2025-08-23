#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm uninstall my-redis -n redis
kubectl delete -f $BASEDIR/redis-individual-nodeports-bitnami.yaml -n redis
kubectl delete namespace redis