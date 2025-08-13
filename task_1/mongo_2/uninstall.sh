#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

helm uninstall my-mongo -n mongo
kubectl delete -f $BASEDIR/mongo-services.yaml -n mongo
kubectl delete namespace mongo
kubectl delete -f $BASEDIR/pymongo_api.yaml -n pymongo-api
kubectl delete namespace pymongo-api
