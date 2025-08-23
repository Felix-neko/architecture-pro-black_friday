#!/bin/bash

echo 'Проверяем и инициализируем replica sets...'

# Функция для проверки и инициализации replica set
init_rs_if_needed() {
  local host=$1
  local rs_config=$2
  local rs_name=$3
  
  echo "Проверяем состояние $rs_name на $host..."
  
  # Проверяем, инициализирован ли replica set
  # Используем более надежную проверку - если rs.status() возвращает ошибку "no replset config", значит не инициализирован
  local status_check=$(mongosh --host $host --quiet --eval 'try { rs.status(); print("INITIALIZED"); } catch(e) { if (e.message.includes("no replset config")) { print("NOT_INITIALIZED"); } else { print("INITIALIZED"); } }' 2>/dev/null)
  
  if echo "$status_check" | grep -q 'NOT_INITIALIZED'; then
    echo " Инициализируем $rs_name..."
    mongosh --host $host --eval "$rs_config" && echo " $rs_name успешно инициализирован"
  else
    echo " $rs_name уже инициализирован"
  fi
}

# Функция для ожидания готовности replica set
wait_for_primary() {
  local host=$1
  local rs_name=$2
  local max_attempts=30
  local attempt=1
  
  echo "Ожидаем готовности PRIMARY для $rs_name..."
  
  while [ $attempt -le $max_attempts ]; do
    # Проверяем статус replica set и ищем PRIMARY
    if mongosh --host $host --quiet --eval 'try { var status = rs.status(); var primary = status.members.find(m => m.state === 1); if (primary) { print("PRIMARY_READY"); } else { print("NO_PRIMARY"); } } catch(e) { print("ERROR: " + e); }' | grep -q 'PRIMARY_READY'; then
      echo " PRIMARY готов для $rs_name"
      return 0
    fi
    echo " Попытка $attempt/$max_attempts: ожидаем PRIMARY для $rs_name..."
    sleep 2
    attempt=$((attempt + 1))
  done
  
  echo " Не удалось дождаться PRIMARY для $rs_name"
  return 1
}

# Инициализируем config server replica set
init_rs_if_needed 'configsvr:27017' 'rs.initiate({_id: "configrs", configsvr: true, members: [{_id: 0, host: "configsvr:27017"}]})' 'configrs'

# Ждем готовности config server (критично для mongos!)
wait_for_primary 'configsvr:27017' 'configrs'

# Инициализируем shard replica sets
init_rs_if_needed 'shard1:27017' 'rs.initiate({_id: "shard1rs", members: [{_id: 0, host: "shard1:27017"}]})' 'shard1rs'
init_rs_if_needed 'shard2:27017' 'rs.initiate({_id: "shard2rs", members: [{_id: 0, host: "shard2:27017"}]})' 'shard2rs'
init_rs_if_needed 'shard3:27017' 'rs.initiate({_id: "shard3rs", members: [{_id: 0, host: "shard3:27017"}]})' 'shard3rs'

# Ждем готовности всех shard replica sets
wait_for_primary 'shard1:27017' 'shard1rs'
wait_for_primary 'shard2:27017' 'shard2rs'
wait_for_primary 'shard3:27017' 'shard3rs'

echo ' Все replica sets проверены и готовы к работе'
