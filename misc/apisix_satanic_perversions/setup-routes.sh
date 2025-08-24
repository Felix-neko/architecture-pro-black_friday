#!/bin/bash
# setup-routes.sh - Настройка маршрутов в APISIX

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
