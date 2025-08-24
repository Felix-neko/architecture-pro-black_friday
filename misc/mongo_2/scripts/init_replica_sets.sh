#!/bin/bash

echo 'Проверяем и инициализируем replica sets...'

# Функция ожидания готовности MongoDB
wait_for_mongo() {
  local host=$1
  local max_attempts=15
  local attempt=1

  echo "Ожидаем готовности MongoDB на $host..."

  while [ $attempt -le $max_attempts ]; do
    if mongosh --host $host --quiet --eval 'db.runCommand("ping")' >/dev/null 2>&1; then
      echo "✅ MongoDB на $host готов (попытка $attempt)"
      return 0
    fi
    echo "⏳ Попытка $attempt/$max_attempts: MongoDB на $host не готов, ждем..."
    sleep 2
    attempt=$((attempt + 1))
  done

  echo "❌ MongoDB на $host не готов после $max_attempts попыток (30 секунд)"
  return 1
}

# Функция для проверки и инициализации replica set с retry
init_rs_if_needed() {
  local host=$1
  local rs_config=$2
  local rs_name=$3
  local max_attempts=5
  local attempt=1

  echo "Проверяем состояние $rs_name на $host..."

  # Сначала ждем готовности MongoDB
  if ! wait_for_mongo "$host"; then
    echo "❌ Не удалось дождаться готовности $host для $rs_name"
    return 1
  fi

  while [ $attempt -le $max_attempts ]; do
    echo "Попытка $attempt/$max_attempts для $rs_name..."

    # Проверяем, инициализирован ли replica set
    local rs_status=$(mongosh --host $host --quiet --eval 'try {
      var status = rs.status();
      if (status.ok === 1 && status.members && status.members.length > 0) {
        print("INITIALIZED");
      } else {
        print("NOT_INITIALIZED");
      }
    } catch(e) {
      print("NOT_INITIALIZED");
    }' 2>/dev/null)

    if echo "$rs_status" | grep -q 'INITIALIZED'; then
      echo "✅ $rs_name уже инициализирован"

      # Проверяем наличие PRIMARY с ожиданием (в рамках той же попытки)
      local primary_wait_attempts=4  # 20 секунд ожидания выборов
      local primary_attempt=1

      while [ $primary_attempt -le $primary_wait_attempts ]; do
        local has_primary=$(mongosh --host $host --quiet --eval 'try {
          var status = rs.status();
          var hasPrimary = status.members.some(m => m.stateStr === "PRIMARY");
          print(hasPrimary ? "HAS_PRIMARY" : "NO_PRIMARY");
        } catch(e) {
          print("NO_PRIMARY");
        }' 2>/dev/null)

        if echo "$has_primary" | grep -q 'HAS_PRIMARY'; then
          echo "✅ $rs_name имеет PRIMARY узел"
          return 0
        else
          if [ $primary_attempt -eq 1 ]; then
            echo "⚠️ $rs_name инициализирован, но нет PRIMARY. Ждем выборы..."
          fi
          echo "⏳ Ожидание выборов PRIMARY ($primary_attempt/$primary_wait_attempts) - осталось $((primary_wait_attempts - primary_attempt)) попыток..."
          sleep 5
          primary_attempt=$((primary_attempt + 1))
        fi
      done

      echo "⚠️ $rs_name инициализирован, но PRIMARY не выбран за 20 секунд. Возможно нужна повторная инициализация."
      # Переходим к следующей попытке полной инициализации
    else
      echo "🔧 Инициализируем $rs_name..."
      if mongosh --host $host --eval "$rs_config" 2>/dev/null; then
        echo "✅ Команда инициализации $rs_name выполнена успешно"
        sleep 5  # Даем время на инициализацию
        # Не делаем continue - проверяем результат в следующей итерации
      else
        echo "❌ Ошибка при инициализации $rs_name"
      fi
    fi

    attempt=$((attempt + 1))
    if [ $attempt -le $max_attempts ]; then
      echo "⏳ Ждем 5 секунд перед следующей попыткой..."
      sleep 5
    fi
  done

  echo "❌ Не удалось инициализировать $rs_name после $max_attempts попыток"
  return 1
}

echo "🚀 Начинаем инициализацию replica sets..."

# Инициализируем config server replica set (3 узла для кворума)
echo "📋 Инициализируем config server replica set..."
init_rs_if_needed 'configsvr1:27017' 'rs.initiate({
  _id: "configrs",
  configsvr: true,
  members: [
    {_id: 0, host: "configsvr1:27017"},
    {_id: 1, host: "configsvr2:27017"},
    {_id: 2, host: "configsvr3:27017"}
  ]
})' 'configrs'

if [ $? -ne 0 ]; then
  echo "❌ Критическая ошибка: не удалось инициализировать config server replica set"
  exit 1
fi

# Ждем стабилизации config servers
echo "⏳ Ждем стабилизации config server replica set..."
sleep 15

# Инициализируем shard replica sets (каждый с primary и secondary)
echo "📊 Инициализируем shard replica sets..."

init_rs_if_needed 'shard1-primary:27017' 'rs.initiate({
  _id: "shard1rs",
  members: [
    {_id: 0, host: "shard1-primary:27017"},
    {_id: 1, host: "shard1-secondary:27017"}
  ]
})' 'shard1rs'

init_rs_if_needed 'shard2-primary:27017' 'rs.initiate({
  _id: "shard2rs",
  members: [
    {_id: 0, host: "shard2-primary:27017"},
    {_id: 1, host: "shard2-secondary:27017"}
  ]
})' 'shard2rs'

init_rs_if_needed 'shard3-primary:27017' 'rs.initiate({
  _id: "shard3rs",
  members: [
    {_id: 0, host: "shard3-primary:27017"},
    {_id: 1, host: "shard3-secondary:27017"}
  ]
})' 'shard3rs'

# Финальная проверка всех replica sets
echo "🔍 Финальная проверка всех replica sets..."
sleep 10

echo "📋 Config Server Status:"
mongosh --host configsvr1:27017 --quiet --eval 'try {
  rs.status().members.forEach(m => print(m.name + ": " + m.stateStr));
} catch(e) {
  print("Error: " + e.message);
}' 2>/dev/null || echo "❌ Ошибка получения статуса configrs"

echo "📊 Shard Status:"
for shard in "shard1-primary" "shard2-primary" "shard3-primary"; do
  echo "--- $shard ---"
  mongosh --host $shard:27017 --quiet --eval 'try {
    rs.status().members.forEach(m => print(m.name + ": " + m.stateStr));
  } catch(e) {
    print("Error: " + e.message);
  }' 2>/dev/null || echo "❌ Ошибка получения статуса $shard"
done

echo '🎉 Инициализация replica sets завершена!'
