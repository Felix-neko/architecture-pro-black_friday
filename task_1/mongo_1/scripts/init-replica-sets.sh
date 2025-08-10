#!/bin/bash

echo 'Проверяем и инициализируем replica sets...'

# Функция для проверки и инициализации replica set
init_rs_if_needed() {
  local host=$1
  local rs_config=$2
  local rs_name=$3
  
  echo "Проверяем состояние $rs_name на $host..."
  
  # Проверяем, инициализирован ли replica set
  if mongosh --host $host --quiet --eval 'try { rs.status(); print("INITIALIZED"); } catch(e) { print("NOT_INITIALIZED"); }' | grep -q 'INITIALIZED'; then
    echo "✅ $rs_name уже инициализирован"
  else
    echo "🔧 Инициализируем $rs_name..."
    mongosh --host $host --eval "$rs_config" && echo "✅ $rs_name успешно инициализирован"
  fi
}

# Инициализируем config server replica set
init_rs_if_needed 'configsvr:27017' 'rs.initiate({_id: "configrs", configsvr: true, members: [{_id: 0, host: "configsvr:27017"}]})' 'configrs'

# Инициализируем shard replica sets
init_rs_if_needed 'shard1:27017' 'rs.initiate({_id: "shard1rs", members: [{_id: 0, host: "shard1:27017"}]})' 'shard1rs'
init_rs_if_needed 'shard2:27017' 'rs.initiate({_id: "shard2rs", members: [{_id: 0, host: "shard2:27017"}]})' 'shard2rs'
init_rs_if_needed 'shard3:27017' 'rs.initiate({_id: "shard3rs", members: [{_id: 0, host: "shard3:27017"}]})' 'shard3rs'

sleep 5
echo '🎉 Все replica sets проверены и готовы к работе'
