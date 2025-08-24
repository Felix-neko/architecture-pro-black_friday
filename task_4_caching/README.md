# Задание 4. Кэширование
Здесь мы добавим к предыдущему заданию ещё и Redis-кэширование.

Ключевые файлы:
- `values-redis-bitnami.yaml` -- параметры для helm chart'а `bitnami/redis-cluster`
- `redis-individual-nodeports.yaml` -- NodePort-сервисы для всех хостов Redis, чтобы `pymongo_api` могло к нему подключиться.
- `postman-collection.json` -- коллекция Postman-тестов для проверки работоспособности нашей системы.

## Установка

```bash
bash setup_minikube.sh
```
В конце должно вывестись:
```
Проверяем статус minikube:
minikube
type: Control Plane
host: Running
kubelet: Running
apiserver: Running
kubeconfig: Configured
```

Устанавливаем MongoDB, Redis и тестовое веб-приложение `pymongo-api`:
```bash
bash install.sh
kubectl wait --for=condition=Ready pod -l app=pymongo-api -n pymongo-api --timeout=600s 
```
Минут через 5 напечатает: `pod/pymongo-api-0 condition met`


## Тестирование

Запускаем тесты:
```bash
npm install newman
npx newman run postman_collection.json --disable-unicode \
  --env-var "host=$(minikube ip)" \
  --env-var "port=30100" \
```

Здесь всё тестируется как в предыдущем задании, только эндпоинт просмотра коллекции вызывается 2 раза:
- в первый раз проверяем, что запрос занял > 1000 мсек, 
- во второй раз -- что запрос занял < 100 мсек.

Трижды проклятый `newman` добавляет в header'ы `cache-control: no-cache`, пришлось это мучительно отлавливать -- и отключать уже в самой тест- коллекции ))