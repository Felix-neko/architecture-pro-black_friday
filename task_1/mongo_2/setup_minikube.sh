
sudo sysctl fs.inotify.max_user_watches=524288
sudo sysctl fs.inotify.max_user_instances=512
# Чтобы не ловить ошибку https://kind.sigs.k8s.io/docs/user/known-issues/#pod-errors-due-to-too-many-open-files

minikube delete
minikube start --driver=docker  --cpus=6 --memory=32g --disk-size=60g --docker-opt default-ulimit=nofile=65536:65536

minikube addons enable metrics-server
# Чтобы не ловить ошибки с PVC
minikube addons enable default-storageclass
minikube addons enable storage-provisioner