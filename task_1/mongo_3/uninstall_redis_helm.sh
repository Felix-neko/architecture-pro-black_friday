#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm uninstall my-redis -n redis
helm uninstall redis-operator -n redis
kubectl delete -f $BASEDIR/haproxy-statefulset.yaml -n redis
kubectl delete -f $BASEDIR/haproxy-redis-config.yaml -n redis
kubectl delete -f $BASEDIR/redis-individual-nodeports.yaml -n redis
kubectl delete namespace redis