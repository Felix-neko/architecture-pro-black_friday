# Makefile для управления APISIX + Consul + HelloWorld развёртыванием

.PHONY: help deploy setup-routes scale status test clean logs

# Параметры по умолчанию
NAMESPACE ?= default
REPLICAS ?= 3
API_KEY = edd1c9f034335f136f87ad84b625c8f1

help: ## Показать справку
	@echo "Доступные команды:"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Использование:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Основные команды

deploy: ## Развернуть все компоненты (NAMESPACE=default)
	@echo "🚀 Развёртывание в namespace: $(NAMESPACE)"
	@chmod +x *.sh
	@./deploy.sh $(NAMESPACE)

setup-routes: ## Настроить маршруты в APISIX
	@echo "🔧 Настройка маршрутов APISIX"
	@./setup-routes.sh

scale: ## Масштабировать hello-world (REPLICAS=3)
	@echo "📈 Масштабирование до $(REPLICAS) реплик"
	@if [ $(REPLICAS) -lt 1 ] || [ $(REPLICAS) -gt 10 ]; then \
		echo "❌ REPLICAS должно быть от 1 до 10"; \
		exit 1; \
	fi
	@./scale.sh $(REPLICAS)

##@ Мониторинг и тестирование

status: ## Показать статус всех компонентов
	@./status.sh

test: ## Протестировать развёртывание
	@echo "🧪 Тестирование развёртывания..."
	@NODE_IP=$$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}' 2>/dev/null || echo "localhost"); \
	NODEPORT=$$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}' 2>/dev/null || echo "30080"); \
	echo "📡 Тестирование HTTP endpoint:"; \
	echo "   URL: http://$$NODE_IP:$$NODEPORT/hello"; \
	if command -v curl >/dev/null 2>&1; then \
		echo "   Ответ:"; \
		curl -s "http://$$NODE_IP:$$NODEPORT/hello" | head -10 || echo "❌ Endpoint недоступен"; \
		echo ""; \
		echo "   Health check:"; \
		curl -s "http://$$NODE_IP:$$NODEPORT/health" || echo "❌ Health check недоступен"; \
	else \
		echo "   curl не установлен, проверьте вручную"; \
	fi

logs: ## Показать логи всех компонентов
	@echo "📜 Логи APISIX:"
	@kubectl logs -l app=apisix --tail=20 || true
	@echo ""
	@echo "📜 Логи Hello World:"
	@kubectl logs -l app=hello-world --tail=20 || true
	@echo ""
	@echo "📜 Логи Consul:"
	@kubectl logs -l app=consul --tail=20 || true
	@echo ""
	@echo "📜 Логи etcd:"
	@kubectl logs -l app=etcd --tail=20 || true

##@ Очистка

clean: ## Удалить все компоненты
	@echo "🧹 Очистка развёртывания"
	@./cleanup.sh $(NAMESPACE)

##@ Дополнительные команды

info: ## Показать информацию о доступе
	@echo "📋 Информация о доступе:"
	@echo "========================="
	@NODE_IP=$$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}' 2>/dev/null || echo "N/A"); \
	HTTP_PORT=$$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}' 2>/dev/null || echo "N/A"); \
	ADMIN_PORT=$$(kubectl get svc apisix -o jsonpath='{.spec.ports[?(@.name=="admin")].nodePort}' 2>/dev/null || echo "N/A"); \
	echo "🌐 APISIX Gateway:"; \
	echo "   HTTP:  http://$$NODE_IP:$$HTTP_PORT"; \
	echo "   Admin: http://$$NODE_IP:$$ADMIN_PORT"; \
	echo ""; \
	echo "🔑 API Key: $(API_KEY)"; \
	echo ""; \
	echo "📊 Команды для тестирования:"; \
	echo "   curl http://$$NODE_IP:$$HTTP_PORT/hello"; \
	echo "   curl http://$$NODE_IP:$$HTTP_PORT/health"; \
	echo ""; \
	echo "🔧 Админ API:"; \
	echo "   curl -H 'X-API-KEY: $(API_KEY)' http://$$NODE_IP:$$ADMIN_PORT/apisix/admin/routes"

forward-consul: ## Port forward для Consul UI (localhost:8500)
	@echo "🌐 Открытие Consul UI на http://localhost:8500"
	@echo "   Нажмите Ctrl+C для остановки"
	@kubectl port-forward svc/consul 8500:8500

forward-apisix: ## Port forward для APISIX Admin (localhost:9180)
	@echo "🔧 Открытие APISIX Admin на http://localhost:9180"
	@echo "   API Key: $(API_KEY)"
	@echo "   Нажмите Ctrl+C для остановки"
	@kubectl port-forward svc/apisix 9180:9180

##@ Быстрые команды

all: deploy setup-routes test ## Развернуть всё и протестировать

restart-apisix: ## Перезапустить APISIX
	@kubectl rollout restart deployment/apisix
	@kubectl rollout status deployment/apisix

restart-hello: ## Перезапустить Hello World
	@kubectl rollout restart statefulset/hello-world
	@kubectl rollout status statefulset/hello-world

##@ Разработка

dev-setup: deploy setup-routes forward-consul ## Настройка для разработки (с Consul UI)

check-deps: ## Проверить зависимости
	@echo "🔍 Проверка зависимостей..."
	@command -v kubectl >/dev/null 2>&1 || (echo "❌ kubectl не найден" && exit 1)
	@command -v curl >/dev/null 2>&1 || echo "⚠️  curl не найден - тестирование будет ограничено"
	@command -v jq >/dev/null 2>&1 || echo "⚠️  jq не найден - JSON не будет форматироваться"
	@kubectl cluster-info >/dev/null 2>&1 || (echo "❌ Нет доступа к Kubernetes кластеру" && exit 1)
	@echo "✅ Все зависимости в порядке"

##@ Примеры использования

examples: ## Показать примеры использования
	@echo "📚 Примеры использования:"
	@echo "========================"
	@echo ""
	@echo "1. Быстрый старт:"
	@echo "   make all"
	@echo ""
	@echo "2. Развёртывание в своём namespace:"
	@echo "   make deploy NAMESPACE=my-app"
	@echo ""
	@echo "3. Масштабирование до 5 реплик:"
	@echo "   make scale REPLICAS=5"
	@echo ""
	@echo "4. Полная очистка:"
	@echo "   make clean"
	@echo ""
	@echo "5. Мониторинг:"
	@echo "   make status"
	@echo "   make logs"
	@echo "   make test"
	@echo ""
	@echo "6. Доступ к UI:"
	@echo "   make forward-consul  # Consul на localhost:8500"
	@echo "   make forward-apisix  # APISIX Admin на localhost:9180"