# APISIX + Consul + HelloWorld на Kubernetes

Минимальный пример развёртывания API Gateway (APISIX) с Consul для service discovery и масштабируемого hello world сервиса на Kubernetes.

## 🏗️ Архитектура

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   APISIX API    │    │     Consul      │    │   Hello World   │
│    Gateway      │───▶│ Service Discovery│    │   StatefulSet   │
│ (NodePort:30080)│    │                 │    │   (1-10 pods)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                         ┌─────────────────┐
                         │      etcd       │
                         │ (конфиг APISIX) │
                         └─────────────────┘
```

## 📦 Компоненты

- **APISIX**: API Gateway с админ-панелью
- **Consul**: Service Discovery и конфигурация
- **etcd**: Хранилище конфигурации для APISIX
- **Hello World**: Масштабируемый StatefulSet (1-10 реплик)

## 🚀 Быстрый старт

### 1. Развёртывание

```bash
# Сделать скрипты исполняемыми
chmod +x *.sh

# Развернуть все компоненты
./deploy.sh

# Или в отдельном namespace
./deploy.sh my-namespace
```

### 2. Настройка маршрутов

```bash
# Настроить маршруты в APISIX
./setup-routes.sh
```

### 3. Тестирование

```bash
# Получить IP узла и порт
kubectl get nodes -o wide
kubectl get svc apisix

# Тестировать hello world сервис
curl http://<NODE_IP>:30080/hello
curl http://<NODE_IP>:30080/health
```

## 📈 Масштабирование

```bash
# Масштабировать hello-world до 5 реплик
./scale.sh 5

# Масштабировать до 1 реплики
./scale.sh 1

# Максимум 10 реплик
./scale.sh 10
```

## 📊 Мониторинг

```bash
# Проверить статус всех компонентов
./status.sh

# Посмотреть логи APISIX
kubectl logs -l app=apisix

# Посмотреть логи hello-world
kubectl logs -l app=hello-world
```

## 🔧 Управление

### Доступ к админ-панели APISIX
- URL: `http://<NODE_IP>:30180`
- API Key: `edd1c9f034335f136f87ad84b625c8f1`

### Доступ к Consul UI
```bash
# Port forward для доступа к Consul UI
kubectl port-forward svc/consul 8500:8500
# Затем откройте http://localhost:8500
```

### Проверка маршрутов APISIX
```bash
# Получить все маршруты
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
curl -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" \
     http://$NODE_IP:30180/apisix/admin/routes
```

## 📝 Конфигурация

### Изменение количества реплик APISIX
```bash
kubectl scale deployment apisix --replicas=3
```

### Изменение конфигурации hello-world
```bash
# Редактировать ConfigMap
kubectl edit configmap hello-world-html

# Перезапустить поды для применения изменений
kubectl rollout restart statefulset/hello-world
```

## 🐛 Troubleshooting

### Проблемы с развёртыванием

1. **APISIX не стартует**
   ```bash
   # Проверить логи
   kubectl logs -l app=apisix
   
   # Проверить доступность etcd
   kubectl exec -it etcd-0 -- etcdctl endpoint health
   ```

2. **Hello World недоступен**
   ```bash
   # Проверить статус подов
   kubectl get pods -l app=hello-world
   
   # Проверить endpoints
   kubectl get endpoints hello-world
   ```

3. **Маршруты не работают**
   ```bash
   # Пересоздать маршруты
   ./setup-routes.sh
   
   # Проверить upstream
   NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
   curl -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" \
        http://$NODE_IP:30180/apisix/admin/upstreams
   ```

### Проверка состояния кластера
```bash
# Убедиться что кластер доступен
kubectl cluster-info

# Проверить ресурсы узлов
kubectl top nodes

# Проверить события
kubectl get events --sort-by=.metadata.creationTimestamp
```

## 🧹 Очистка

```bash
# Удалить все компоненты
./cleanup.sh

# Или в конкретном namespace
./cleanup.sh my-namespace
```

## 📋 Файлы проекта

- `deploy.sh` - Основной скрипт развёртывания
- `scale.sh` - Масштабирование hello-world сервиса
- `setup-routes.sh` - Настройка маршрутов APISIX
- `status.sh` - Проверка статуса развёртывания
- `cleanup.sh` - Очистка всех ресурсов

## 🔐 Безопасность

⚠️ **Внимание**: Данная конфигурация предназначена для тестирования. Для продакшена:

1. Измените API ключи APISIX
2. Настройте TLS
3. Ограничьте доступ к админ-панели
4. Настройте authentication/authorization
5. Используйте LoadBalancer вместо NodePort

## 📚 Полезные ссылки

- [APISIX Documentation](https://apisix.apache.org/docs/apisix/getting-started/)
- [Consul Documentation](https://www.consul.io/docs)
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)

## 🤝 Использование

1. Склонируйте репозиторий или скопируйте файлы
2. Убедитесь что у вас есть доступ к Kubernetes кластеру
3. Запустите `./deploy.sh`
4. Настройте маршруты с помощью `./setup-routes.sh`
5. Тестируйте и масштабируйте по необходимости