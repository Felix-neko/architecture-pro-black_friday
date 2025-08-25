#!/usr/bin/env bash
BASEDIR=$(dirname "$0")

bash $BASEDIR/install_mongo.sh
bash $BASEDIR/install_redis_helm.sh
bash $BASEDIR/install_pymongo_api.sh
