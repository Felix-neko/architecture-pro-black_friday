#!/bin/bash
# deploy.sh - Основной скрипт развёртывания

set -e

echo "🚀 Развёртывание APISIX + Consul + Hello World на Kubernetes"

# Проверяем доступность kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl не найден. Установите kubectl и настройте доступ к кластеру."
    exit 1
fi

# Проверяем подключение к кластеру
echo "📡 Проверка подключения к Kubernetes кластеру..."
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Не удается подключиться к Kubernetes кластеру."
    exit 1
fi

echo "✅ Подключение к кластеру установлено"

# Создаем namespace (опционально)
NAMESPACE=${1:-default}
if [ "$NAMESPACE" != "default" ]; then
    echo "📝 Создание namespace: $NAMESPACE"
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    kubectl config set-context --current --namespace=$NAMESPACE
fi

# Применяем все манифесты
echo "📦 Развёртывание компонентов..."

# 1. Сначала etcd (нужен для APISIX)
echo "  - Развёртывание etcd..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: etcd
spec:
  ports:
  - port: 2379
    name: client
  - port: 2380
    name: peer
  clusterIP: None
  selector:
    app: etcd
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: etcd
spec:
  serviceName: etcd
  replicas: 1
  selector:
    matchLabels:
      app: etcd
  template:
    metadata:
      labels:
        app: etcd
    spec:
      containers:
      - name: etcd
        image: quay.io/coreos/etcd:v3.5.9
        ports:
        - containerPort: 2379
          name: client
        - containerPort: 2380
          name: peer
        env:
        - name: ETCD_DATA_DIR
          value: /etcd-data
        - name: ETCD_LISTEN_CLIENT_URLS
          value: http://0.0.0.0:2379
        - name: ETCD_ADVERTISE_CLIENT_URLS
          value: http://etcd:2379
        - name: ETCD_LISTEN_PEER_URLS
          value: http://0.0.0.0:2380
        - name: ETCD_INITIAL_ADVERTISE_PEER_URLS
          value: http://etcd:2380
        - name: ETCD_INITIAL_CLUSTER
          value: etcd=http://etcd:2380
        - name: ETCD_NAME
          value: etcd
        volumeMounts:
        - name: etcd-data
          mountPath: /etcd-data
  volumeClaimTemplates:
  - metadata:
      name: etcd-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 1Gi
EOF

# 2. Consul
echo "  - Развёртывание Consul..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: consul
  labels:
    app: consul
spec:
  ports:
    - port: 8500
      name: http
    - port: 8300
      name: server
  clusterIP: None
  selector:
    app: consul
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: consul
spec:
  serviceName: consul
  replicas: 1
  selector:
    matchLabels:
      app: consul
  template:
    metadata:
      labels:
        app: consul
    spec:
      containers:
      - name: consul
        image: consul:1.19
        ports:
        - containerPort: 8500
          name: http
        - containerPort: 8300
          name: server
        env:
        - name: CONSUL_BIND_INTERFACE
          value: eth0
        - name: CONSUL_CLIENT_INTERFACE
          value: eth0
        args:
        - "agent"
        - "-server"
        - "-bootstrap"
        - "-ui"
        - "-client=0.0.0.0"
        - "-bind=0.0.0.0"
        - "-data-dir=/consul/data"
        volumeMounts:
        - name: consul-data
          mountPath: /consul/data
  volumeClaimTemplates:
  - metadata:
      name: consul-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 1Gi
EOF

# 3. Hello World сервис
echo "  - Развёртывание Hello World сервиса..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: hello-world-nginx-config
data:
  nginx.conf: |
    events {
        worker_connections 1024;
    }
    http {
        server {
            listen 8080;
            location / {
                root /usr/share/nginx/html;
                index index.html;
            }
            location /health {
                access_log off;
                return 200 "healthy\n";
                add_header Content-Type text/plain;
            }
        }
    }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: hello-world-html
data:
  index.html: |
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hello World Service</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 600px; margin: 0 auto; }
            .info { background: #f0f0f0; padding: 20px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Hello World Service</h1>
            <div class="info">
                <p><strong>Service:</strong> StatefulSet Hello World</p>
                <p><strong>Time:</strong> <span id="time"></span></p>
                <p><strong>Status:</strong> ✅ Running</p>
                <p><strong>Version:</strong> 1.0.0</p>
            </div>
            <p>This service is running in a Kubernetes StatefulSet and accessible through APISIX API Gateway.</p>
        </div>
        <script>
            function updateTime() {
                document.getElementById('time').textContent = new Date().toISOString();
            }
            updateTime();
            setInterval(updateTime, 1000);
        </script>
    </body>
    </html>
---
apiVersion: v1
kind: Service
metadata:
  name: hello-world
spec:
  ports:
  - port: 80
    targetPort: 8080
  selector:
    app: hello-world
  clusterIP: None
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: hello-world
spec:
  serviceName: hello-world
  replicas: 3
  selector:
    matchLabels:
      app: hello-world
  template:
    metadata:
      labels:
        app: hello-world
    spec:
      containers:
      - name: hello-world
        image: nginx:alpine
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: nginx-config
          mountPath: /etc/nginx/nginx.conf
          subPath: nginx.conf
        - name: html-content
          mountPath: /usr/share/nginx/html
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_IP
          valueFrom:
            fieldRef:
              fieldPath: status.podIP
      volumes:
      - name: nginx-config
        configMap:
          name: hello-world-nginx-config
      - name: html-content
        configMap:
          name: hello-world-html
EOF

# Ожидаем готовности etcd
echo "⏳ Ожидание готовности etcd..."
kubectl wait --for=condition=ready pod -l app=etcd --timeout=300s

# 4. APISIX
echo "  - Развёртывание APISIX API Gateway..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: apisix-config
data:
  config.yaml: |
    apisix:
      node_listen: 9080
      admin_listen:
        ip: 0.0.0.0
        port: 9180
      enable_admin: true
      admin_key:
        - name: "admin"
          key: edd1c9f034335f136f87ad84b625c8f1
          role: admin

    deployment:
      admin:
        admin_key:
          - name: "admin"
            key: edd1c9f034335f136f87ad84b625c8f1
            role: admin
        enable_admin_cors: true
        admin_listen:
          ip: 0.0.0.0
          port: 9180
      etcd:
        host:
          - "http://etcd:2379"
      config_center: etcd
---
apiVersion: v1
kind: Service
metadata:
  name: apisix
spec:
  selector:
    app: apisix
  ports:
  - name: http
    port: 9080
    targetPort: 9080
    nodePort: 30080
  - name: admin
    port: 9180
    targetPort: 9180
    nodePort: 30180
  type: NodePort
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: apisix
spec:
  replicas: 2
  selector:
    matchLabels:
      app: apisix
  template:
    metadata:
      labels:
        app: apisix
    spec:
      containers:
      - name: apisix
        image: apache/apisix:3.2.0-debian
        ports:
        - containerPort: 9080
        - containerPort: 9180
        volumeMounts:
        - name: apisix-config
          mountPath: /usr/local/apisix/conf/config.yaml
          subPath: config.yaml
        env:
        - name: APISIX_STAND_ALONE
          value: "false"
        readinessProbe:
          httpGet:
            path: /apisix/admin/routes
            port: 9180
            httpHeaders:
            - name: X-API-KEY
              value: edd1c9f034335f136f87ad84b625c8f1
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /apisix/admin/routes
            port: 9180
            httpHeaders:
            - name: X-API-KEY
              value: edd1c9f034335f136f87ad84b625c8f1
          initialDelaySeconds: 30
          periodSeconds: 10
      volumes:
      - name: apisix-config
        configMap:
          name: apisix-config
EOF

echo "⏳ Ожидание готовности всех компонентов..."

# Ожидаем готовности всех подов
kubectl wait --for=condition=ready pod -l app=consul --timeout=300s
kubectl wait --for=condition=ready pod -l app=hello-world --timeout=300s
kubectl wait --for=condition=ready pod -l app=apisix --timeout=300s

echo "✅ Все компоненты развёрнуты успешно!"

# Показываем информацию о развёртывании
echo ""
echo "📋 Информация о развёртывании:"
echo "================================"

# Получаем NodePort информацию
NODEPORT_HTTP=$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}')
NODEPORT_ADMIN=$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="admin")].nodePort}')

# Получаем IP узлов
NODE_IPS=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="ExternalIP")].address}')
if [ -z "$NODE_IPS" ]; then
    NODE_IPS=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}')
fi

echo "🌐 APISIX доступен на:"
for ip in $NODE_IPS; do
    echo "   HTTP: http://$ip:$NODEPORT_HTTP"
    echo "   Admin: http://$ip:$NODEPORT_ADMIN"
done

echo ""
echo "📊 Статус подов:"
kubectl get pods -l app=consul
kubectl get pods -l app=etcd
kubectl get pods -l app=apisix
kubectl get pods -l app=hello-world

echo ""
echo "🔧 Следующие шаги:"
echo "1. Настройте маршруты в APISIX: ./setup-routes.sh"
echo "2. Масштабируйте hello-world сервис: ./scale.sh <количество_реплик>"
echo "3. Проверьте доступность: curl http://<node-ip>:$NODEPORT_HTTP/hello"

---

# scale.sh - Скрипт для масштабирования hello world сервиса
#!/bin/bash

set -e

REPLICAS=${1}

if [ -z "$REPLICAS" ]; then
    echo "❌ Использование: $0 <количество_реплик>"
    echo "   Количество реплик должно быть от 1 до 10"
    exit 1
fi

# Проверяем диапазон
if [ "$REPLICAS" -lt 1 ] || [ "$REPLICAS" -gt 10 ]; then
    echo "❌ Количество реплик должно быть от 1 до 10"
    exit 1
fi

echo "📈 Масштабирование hello-world StatefulSet до $REPLICAS реплик..."

# Масштабируем StatefulSet
kubectl scale statefulset hello-world --replicas=$REPLICAS

echo "⏳ Ожидание готовности подов..."
kubectl rollout status statefulset/hello-world --timeout=300s

echo "✅ Масштабирование завершено успешно!"

echo ""
echo "📊 Статус hello-world подов:"
kubectl get pods -l app=hello-world

echo ""
echo "🔍 Подробная информация:"
kubectl get statefulset hello-world

---

# setup-routes.sh - Настройка маршрутов в APISIX
#!/bin/bash

set -e

echo "🔧 Настройка маршрутов в APISIX..."

# Получаем информацию о сервисе APISIX
NODEPORT_ADMIN=$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="admin")].nodePort}')
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

APISIX_ADMIN_URL="http://$NODE_IP:$NODEPORT_ADMIN"
API_KEY="edd1c9f034335f136f87ad84b625c8f1"

echo "📡 APISIX Admin URL: $APISIX_ADMIN_URL"

# Проверяем доступность APISIX Admin API
echo "🔍 Проверка доступности APISIX Admin API..."
if ! curl -s -o /dev/null -w "%{http_code}" \
     -H "X-API-KEY: $API_KEY" \
     "$APISIX_ADMIN_URL/apisix/admin/routes" | grep -q "200"; then
    echo "❌ APISIX Admin API недоступен. Проверьте, что все поды запущены."
    exit 1
fi

echo "✅ APISIX Admin API доступен"

# Создаем upstream для hello-world сервиса
echo "🌐 Создание upstream для hello-world..."
curl -s -X PUT "$APISIX_ADMIN_URL/apisix/admin/upstreams/1" \
     -H "X-API-KEY: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "roundrobin",
       "discovery_type": "dns",
       "service_name": "hello-world.default.svc.cluster.local:80",
       "pass_host": "pass"
     }' | jq .

# Создаем маршрут для hello-world
echo "🛣️  Создание маршрута /hello..."
curl -s -X PUT "$APISIX_ADMIN_URL/apisix/admin/routes/1" \
     -H "X-API-KEY: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "uri": "/hello*",
       "methods": ["GET", "POST"],
       "upstream_id": 1,
       "name": "hello-world-route"
     }' | jq .

# Создаем маршрут для health check
echo "🏥 Создание маршрута /health..."
curl -s -X PUT "$APISIX_ADMIN_URL/apisix/admin/routes/2" \
     -H "X-API-KEY: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "uri": "/health",
       "methods": ["GET"],
       "upstream_id": 1,
       "name": "health-check-route"
     }' | jq .

echo "✅ Маршруты настроены успешно!"

echo ""
echo "📋 Созданные маршруты:"
curl -s -H "X-API-KEY: $API_KEY" "$APISIX_ADMIN_URL/apisix/admin/routes" | jq '.list[] | {id: .value.id, name: .value.name, uri: .value.uri}'

# Получаем NodePort для HTTP
NODEPORT_HTTP=$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}')

echo ""
echo "🌐 Тестирование маршрутов:"
echo "curl http://$NODE_IP:$NODEPORT_HTTP/hello"
echo "curl http://$NODE_IP:$NODEPORT_HTTP/health"

---

# cleanup.sh - Очистка развёртывания
#!/bin/bash

set -e

echo "🧹 Очистка развёртывания APISIX + Consul + Hello World..."

NAMESPACE=${1:-default}

if [ "$NAMESPACE" != "default" ]; then
    kubectl config set-context --current --namespace=$NAMESPACE
fi

echo "🗑️  Удаление компонентов..."

# Удаляем в обратном порядке
kubectl delete deployment apisix --ignore-not-found=true
kubectl delete statefulset hello-world --ignore-not-found=true
kubectl delete statefulset consul --ignore-not-found=true
kubectl delete statefulset etcd --ignore-not-found=true

kubectl delete service apisix --ignore-not-found=true
kubectl delete service hello-world --ignore-not-found=true
kubectl delete service consul --ignore-not-found=true
kubectl delete service etcd --ignore-not-found=true

kubectl delete configmap apisix-config --ignore-not-found=true
kubectl delete configmap hello-world-nginx-config --ignore-not-found=true
kubectl delete configmap hello-world-html --ignore-not-found=true

# Удаляем PVC
kubectl delete pvc --all --ignore-not-found=true

echo "✅ Очистка завершена!"

---

# status.sh - Проверка статуса развёртывания
#!/bin/bash

echo "📊 Статус развёртывания APISIX + Consul + Hello World"
echo "===================================================="

# Проверяем поды
echo ""
echo "🟢 Поды:"
kubectl get pods -l app=etcd
kubectl get pods -l app=consul
kubectl get pods -l app=apisix
kubectl get pods -l app=hello-world

# Проверяем сервисы
echo ""
echo "🌐 Сервисы:"
kubectl get services

# Проверяем StatefulSets
echo ""
echo "📈 StatefulSets:"
kubectl get statefulsets

# Получаем информацию о доступности
echo ""
echo "🔗 Точки доступа:"
NODEPORT_HTTP=$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}' 2>/dev/null || echo "N/A")
NODEPORT_ADMIN=$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="admin")].nodePort}' 2>/dev/null || echo "N/A")
NODE_IPS=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null)

if [ ! -z "$NODE_IPS" ] && [ "$NODEPORT_HTTP" != "N/A" ]; then
    for ip in $NODE_IPS; do
        echo "   HTTP: http://$ip:$NODEPORT_HTTP"
        echo "   Admin: http://$ip:$NODEPORT_ADMIN"
        break # Показываем только первый IP
    done
else
    echo "   APISIX сервис еще не готов"
fi

echo ""
echo "🔧 Полезные команды:"
echo "   Масштабирование: ./scale.sh <1-10>"
echo "   Настройка маршрутов: ./setup-routes.sh"
echo "   Очистка: ./cleanup.sh"