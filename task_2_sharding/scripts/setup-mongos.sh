#!/bin/bash

echo 'Проверяем и добавляем шарды в кластер...'

# Функция для проверки и добавления шарда
add_shard_if_needed() {
  local shard_name=$1
  local shard_connection=$2
  
  echo "Проверяем шард $shard_name..."
  
  # Проверяем, добавлен ли уже этот шард
  if mongosh --host mongos:27017 --quiet --eval 'sh.status()' | grep -q "$shard_name"; then
    echo "✅ Шард $shard_name уже добавлен в кластер"
  else
    echo "🔧 Добавляем шард $shard_name..."
    mongosh --host mongos:27017 --eval "sh.addShard(\"$shard_connection\")" && echo "✅ Шард $shard_name успешно добавлен"
  fi
}

# Добавляем все шарды
add_shard_if_needed 'shard1rs' 'shard1rs/shard1:27017'
add_shard_if_needed 'shard2rs' 'shard2rs/shard2:27017'
add_shard_if_needed 'shard3rs' 'shard3rs/shard3:27017'

echo '📊 Текущий статус кластера:'
mongosh --host mongos:27017 --eval 'sh.status()'
echo '🎉 Настройка шардированного кластера завершена!'
