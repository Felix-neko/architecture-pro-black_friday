#!/bin/bash

echo 'Проверяем и добавляем шарды в кластер...'

# Функция ожидания готовности mongos
wait_for_mongos() {
  local host=$1
  local max_attempts=60  # Увеличиваем время ожидания для mongos
  local attempt=1
  
  echo "Ожидаем готовности mongos на $host..."
  
  while [ $attempt -le $max_attempts ]; do
    # Проверяем, что mongos может подключиться к config servers
    local mongos_status=$(mongosh --host $host --quiet --eval 'try { 
      db.adminCommand("ismaster"); 
      print("READY"); 
    } catch(e) { 
      print("NOT_READY"); 
    }' 2>/dev/null)
    
    if echo "$mongos_status" | grep -q 'READY'; then
      echo "✅ Mongos на $host готов (попытка $attempt)"
      return 0
    fi
    echo "⏳ Попытка $attempt/$max_attempts: mongos на $host не готов, ждем..."
    sleep 3
    attempt=$((attempt + 1))
  done
  
  echo "❌ Mongos на $host не готов после $max_attempts попыток"
  return 1
}

# Функция для проверки и добавления шарда с retry
add_shard_if_needed() {
  local shard_name=$1
  local shard_connection=$2
  local max_attempts=5
  local attempt=1

  echo "Проверяем шард $shard_name..."

  while [ $attempt -le $max_attempts ]; do
    echo "Попытка $attempt/$max_attempts для шарда $shard_name..."
    
    # Проверяем, добавлен ли уже этот шард
    local shard_exists=$(mongosh --host mongos1:27017 --quiet --eval 'try { 
      var shards = db.adminCommand("listShards"); 
      var exists = shards.shards.some(s => s._id === "'$shard_name'");
      print(exists ? "EXISTS" : "NOT_EXISTS");
    } catch(e) { 
      print("ERROR"); 
    }' 2>/dev/null)
    
    if echo "$shard_exists" | grep -q 'EXISTS'; then
      echo "✅ Шард $shard_name уже добавлен в кластер"
      return 0
    elif echo "$shard_exists" | grep -q 'ERROR'; then
      echo "❌ Ошибка при проверке шарда $shard_name"
    else
      echo "🔧 Добавляем шард $shard_name..."
      local add_result=$(mongosh --host mongos1:27017 --quiet --eval 'try { 
        var result = sh.addShard("'$shard_connection'"); 
        print(result.ok === 1 ? "SUCCESS" : "FAILED");
      } catch(e) { 
        print("ERROR: " + e.message); 
      }' 2>/dev/null)
      
      if echo "$add_result" | grep -q 'SUCCESS'; then
        echo "✅ Шард $shard_name успешно добавлен"
        return 0
      else
        echo "❌ Ошибка при добавлении шарда $shard_name: $add_result"
      fi
    fi
    
    attempt=$((attempt + 1))
    if [ $attempt -le $max_attempts ]; then
      echo "⏳ Ждем 5 секунд перед следующей попыткой..."
      sleep 5
    fi
  done
  
  echo "❌ Не удалось добавить шард $shard_name после $max_attempts попыток"
  return 1
}

echo "🚀 Начинаем настройку шардированного кластера..."

# Ждем готовности mongos роутеров
echo "⏳ Ждем готовности mongos роутеров..."
if ! wait_for_mongos "mongos1:27017"; then
  echo "❌ Критическая ошибка: mongos1 не готов"
  exit 1
fi

if ! wait_for_mongos "mongos2:27017"; then
  echo "⚠️ Предупреждение: mongos2 не готов, но продолжаем с mongos1"
fi

# Дополнительная пауза для стабилизации
echo "⏳ Дополнительная пауза для стабилизации кластера..."
sleep 10

# Добавляем все шарды (теперь каждый шард - это replica set с primary и secondary)
echo "📊 Добавляем шарды в кластер..."

add_shard_if_needed 'shard1rs' 'shard1rs/shard1-primary:27017,shard1-secondary:27017'
add_shard_if_needed 'shard2rs' 'shard2rs/shard2-primary:27017,shard2-secondary:27017'
add_shard_if_needed 'shard3rs' 'shard3rs/shard3-primary:27017,shard3-secondary:27017'

echo '📊 Текущий статус кластера:'
mongosh --host mongos1:27017 --quiet --eval 'try { 
  sh.status(); 
} catch(e) { 
  print("Error getting cluster status: " + e.message); 
}' 2>/dev/null || echo "❌ Ошибка получения статуса кластера"

echo '🔍 Проверяем доступность через оба mongos роутера:'

echo 'Mongos1 (порт 27017):'
mongosh --host mongos1:27017 --quiet --eval 'try { 
  var result = db.adminCommand("listShards"); 
  if (result.ok === 1) {
    result.shards.forEach(s => print("✅ " + s._id + ": " + s.host + " (state: " + s.state + ")"));
  } else {
    print("❌ Ошибка получения списка шардов");
  }
} catch(e) { 
  print("❌ Ошибка подключения к mongos1: " + e.message); 
}' 2>/dev/null

echo 'Mongos2 (порт 27017):'
mongosh --host mongos2:27017 --quiet --eval 'try { 
  var result = db.adminCommand("listShards"); 
  if (result.ok === 1) {
    result.shards.forEach(s => print("✅ " + s._id + ": " + s.host + " (state: " + s.state + ")"));
  } else {
    print("❌ Ошибка получения списка шардов");
  }
} catch(e) { 
  print("❌ Ошибка подключения к mongos2: " + e.message); 
}' 2>/dev/null

# Финальная проверка кластера
echo "🎯 Финальная проверка кластера:"
mongosh --host mongos1:27017 --quiet --eval 'try { 
  var config = db.getSiblingDB("config");
  var shards = config.shards.find().toArray();
  var mongoses = config.mongos.find().toArray();
  
  print("📊 Шарды в кластере: " + shards.length);
  shards.forEach(s => print("  - " + s._id + ": " + s.host));
  
  print("🔀 Активные mongos: " + mongoses.length);
  mongoses.forEach(m => print("  - " + m._id + " (ping: " + m.ping + ")"));
  
} catch(e) { 
  print("❌ Ошибка финальной проверки: " + e.message); 
}' 2>/dev/null || echo "❌ Ошибка финальной проверки кластера"

echo '🎉 Настройка шардированного кластера завершена!'
