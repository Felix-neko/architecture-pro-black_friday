helm repo add bitnami https://charts.bitnami.com/bitnami
kubectl create namespace redis
helm install my-redis-cluster bitnami/redis-cluster  --namespace redis  --values values-redis.yam