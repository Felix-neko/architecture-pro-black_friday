#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

kubectl delete -f $BASEDIR/anal-probe.yaml -n anal-probe
kubectl delete namespace anal-probe