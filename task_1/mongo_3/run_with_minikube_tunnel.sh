# Проверим каждую ноду
for port in 30001 30002 30003 30004 30005 30006; do
  echo "Checking port $port:"
  redis-cli -h minikube-docker-p $port -a redis-dev-password ping 2>/dev/null || echo "  Failed"
done