#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm uninstall my-redis-cluster -n redis
kubectl delete namespace redis
kubectl delete -f node_port_services.yaml