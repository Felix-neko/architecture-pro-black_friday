#!/bin/bash
# status.sh - Проверка статуса развёртывания

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
