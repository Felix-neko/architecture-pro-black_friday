#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

kubectl create namespace pymongo-api
kubectl apply -f $BASEDIR/pymongo_api.yaml -n pymongo-api