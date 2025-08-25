#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

kubectl create namespace anal-probe
kubectl apply -f $BASEDIR/anal-probe.yaml -n anal-probe