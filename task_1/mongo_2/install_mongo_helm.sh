kubectl create namespace mongo
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm install my-mongo -f values-mycluster.yaml bitnami/mongodb-sharded -n mongo