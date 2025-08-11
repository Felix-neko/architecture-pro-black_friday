#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm uninstall my-mongo -n mongo
kubectl delete -f $BASEDIR/mongo-services.yaml -n mongo
kubectl delete namespace mongo
