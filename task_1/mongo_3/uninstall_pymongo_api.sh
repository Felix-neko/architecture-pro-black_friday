#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

kubectl delete -f $BASEDIR/pymongo_api.yaml -n pymongo-api
kubectl delete namespace pymongo-api