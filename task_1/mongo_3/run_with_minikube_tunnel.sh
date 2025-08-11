# Проверим каждую ноду
for port in 30001 30002 30003 30004 30005 30006; do
  echo "Checking port $port:"
  redis-cli -h 192.168.49.2 -p $port -a redis-dev-password ping 2>/dev/null || echo "  Failed"
done