#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

kubectl create namespace mongo
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm install my-mongo -f my-mongo-values.yaml bitnami/mongodb-sharded -n mongo
kubectl apply -f $BASEDIR/mongo-services.yaml -n mongo
