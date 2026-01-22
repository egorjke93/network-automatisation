# Kubernetes для начинающих — Практический учебник

> **Цель:** Подготовиться к курсу по Observability (Prometheus, Grafana, ELK, Jaeger)
> **Предварительные знания:** Базовый Docker

---

## Содержание

1. [Что такое Kubernetes и зачем он нужен](#1-что-такое-kubernetes-и-зачем-он-нужен)
2. [Архитектура Kubernetes](#2-архитектура-kubernetes)
3. [Основные объекты](#3-основные-объекты-kubernetes)
4. [kubectl — главный инструмент](#4-kubectl--главный-инструмент)
5. [Практика: первое приложение](#5-практика-первое-приложение)
6. [Конфигурация и секреты](#6-конфигурация-и-секреты)
7. [Сеть в Kubernetes](#7-сеть-в-kubernetes)
8. [Хранение данных](#8-хранение-данных)
9. [Мониторинг и логи (подготовка к курсу)](#9-мониторинг-и-логи)
10. [Практические задания](#10-практические-задания)
11. [Шпаргалка команд](#11-шпаргалка-команд)

---

## 1. Что такое Kubernetes и зачем он нужен

### Docker vs Kubernetes

| Docker | Kubernetes |
|--------|------------|
| Запускает **один контейнер** | Управляет **тысячами контейнеров** |
| На одном сервере | На кластере серверов |
| Ручное управление | Автоматизация |
| `docker run` | Декларативные манифесты YAML |

### Проблемы, которые решает Kubernetes

```
Без Kubernetes:                     С Kubernetes:
┌─────────────────────┐            ┌─────────────────────┐
│ Server 1            │            │ Kubernetes Cluster  │
│  └─ nginx (упал!)   │            │  ├─ nginx ✓         │
│                     │            │  ├─ nginx ✓ (авто)  │
│ Server 2            │            │  ├─ nginx ✓ (авто)  │
│  └─ nginx (вручную) │            │  └─ автобалансировка│
└─────────────────────┘            └─────────────────────┘
```

**Kubernetes автоматически:**
- Перезапускает упавшие контейнеры
- Масштабирует (добавляет копии при нагрузке)
- Балансирует трафик
- Обновляет приложения без простоя
- Управляет конфигурацией и секретами

### Аналогия

> **Docker** = грузовик (перевозит один контейнер)
> **Kubernetes** = логистическая компания (управляет флотом грузовиков)

---

## 2. Архитектура Kubernetes

### Компоненты кластера

```
┌─────────────────────────────────────────────────────────────────┐
│                    KUBERNETES CLUSTER                            │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  CONTROL PLANE (Master)                  │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │    │
│  │  │ API Server   │ │ Scheduler    │ │ Controller       │ │    │
│  │  │ (вход/выход) │ │ (размещение) │ │ Manager          │ │    │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘ │    │
│  │  ┌──────────────────────────────────────────────────────┐│    │
│  │  │ etcd (база данных состояния кластера)                ││    │
│  │  └──────────────────────────────────────────────────────┘│    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │   WORKER 1    │  │   WORKER 2    │  │   WORKER 3    │        │
│  │  ┌─────────┐  │  │  ┌─────────┐  │  │  ┌─────────┐  │        │
│  │  │ kubelet │  │  │  │ kubelet │  │  │  │ kubelet │  │        │
│  │  └─────────┘  │  │  └─────────┘  │  │  └─────────┘  │        │
│  │  ┌─────────┐  │  │  ┌─────────┐  │  │  ┌─────────┐  │        │
│  │  │ Pod     │  │  │  │ Pod     │  │  │  │ Pod     │  │        │
│  │  │ Pod     │  │  │  │ Pod     │  │  │  │ Pod     │  │        │
│  │  └─────────┘  │  │  └─────────┘  │  │  └─────────┘  │        │
│  └───────────────┘  └───────────────┘  └───────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### Что делает каждый компонент

| Компонент | Роль | Аналогия |
|-----------|------|----------|
| **API Server** | Принимает команды, единственная точка входа | Ресепшн в отеле |
| **etcd** | Хранит состояние кластера (key-value БД) | Журнал регистрации |
| **Scheduler** | Решает, на какую ноду поставить Pod | Менеджер, распределяющий задачи |
| **Controller Manager** | Следит, чтобы желаемое = реальное | Контролёр качества |
| **kubelet** | Агент на каждой ноде, запускает контейнеры | Работник на складе |
| **kube-proxy** | Сетевой прокси на каждой ноде | Маршрутизатор |

---

## 3. Основные объекты Kubernetes

### Иерархия объектов

```
Namespace (изоляция)
  └── Deployment (управление репликами)
        └── ReplicaSet (поддержание N копий)
              └── Pod (минимальная единица)
                    └── Container (Docker-контейнер)
```

### Pod — минимальная единица

**Pod** = один или несколько контейнеров с общим IP и storage.

```yaml
# pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-nginx
  labels:
    app: nginx
spec:
  containers:
  - name: nginx
    image: nginx:latest
    ports:
    - containerPort: 80
```

**Важно:** Pod — эфемерный (временный). Не создавай Pod напрямую, используй Deployment!

### Deployment — управление приложением

**Deployment** = декларативное описание желаемого состояния.

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3                    # Хочу 3 копии
  selector:
    matchLabels:
      app: nginx                 # Управляю Pod'ами с этим label
  template:                      # Шаблон для создания Pod'ов
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.21
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "128Mi"
            cpu: "500m"
```

**Что делает Deployment:**
- Создаёт ReplicaSet
- Поддерживает 3 копии Pod'ов
- При падении — автоматически пересоздаёт
- При обновлении image — rolling update (без простоя)

### Service — доступ к приложению

**Проблема:** IP Pod'ов меняются при перезапуске.
**Решение:** Service даёт стабильный IP и DNS-имя.

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
spec:
  selector:
    app: nginx              # Ищет Pod'ы с label app=nginx
  ports:
  - port: 80                # Порт Service
    targetPort: 80          # Порт контейнера
  type: ClusterIP           # Тип (см. ниже)
```

**Типы Service:**

| Тип | Доступ | Использование |
|-----|--------|---------------|
| `ClusterIP` | Только внутри кластера | Внутренние сервисы |
| `NodePort` | Через IP любой ноды:порт | Разработка, тестирование |
| `LoadBalancer` | Внешний балансировщик | Production в облаке |

```
                    Internet
                        │
                        ▼
┌─────────────────────────────────────┐
│            LoadBalancer             │  ← Внешний IP
└─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────┐
│     Service (nginx-service)         │  ← Стабильный внутренний IP
│     ClusterIP: 10.96.0.100          │
└─────────────────────────────────────┘
           │         │         │
           ▼         ▼         ▼
        ┌─────┐   ┌─────┐   ┌─────┐
        │Pod 1│   │Pod 2│   │Pod 3│    ← Эфемерные IP
        └─────┘   └─────┘   └─────┘
```

### Namespace — изоляция

**Namespace** = виртуальный кластер внутри кластера.

```bash
# Стандартные namespace
kubectl get namespaces

# NAME              STATUS
# default           Active    ← Твои приложения
# kube-system       Active    ← Системные компоненты K8s
# kube-public       Active    ← Публичные ресурсы
# monitoring        Active    ← Prometheus, Grafana (для курса!)
```

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-app
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: my-app         # Создаётся в этом namespace
spec:
  # ...
```

---

## 4. kubectl — главный инструмент

### Установка

```bash
# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Проверка
kubectl version --client
```

### Формат команд

```
kubectl [КОМАНДА] [ТИП] [ИМЯ] [ФЛАГИ]

kubectl get pods                    # Список Pod'ов
kubectl get pods -n kube-system     # В namespace kube-system
kubectl get pods -o wide            # С дополнительной информацией
kubectl get pods -o yaml            # В формате YAML
```

### Основные команды

```bash
# === ПОЛУЧЕНИЕ ИНФОРМАЦИИ ===
kubectl get pods                    # Список Pod'ов
kubectl get deployments             # Список Deployment'ов
kubectl get services                # Список Service'ов
kubectl get all                     # Всё в namespace
kubectl get all -A                  # Всё во всех namespace

# === ДЕТАЛЬНАЯ ИНФОРМАЦИЯ ===
kubectl describe pod <name>         # Подробности о Pod
kubectl describe deployment <name>  # Подробности о Deployment
kubectl logs <pod-name>             # Логи контейнера
kubectl logs <pod-name> -f          # Логи в реальном времени
kubectl logs <pod-name> --previous  # Логи упавшего контейнера

# === СОЗДАНИЕ И ПРИМЕНЕНИЕ ===
kubectl apply -f deployment.yaml    # Создать/обновить из файла
kubectl apply -f ./manifests/       # Применить всю папку
kubectl create deployment nginx --image=nginx  # Быстрое создание

# === УДАЛЕНИЕ ===
kubectl delete pod <name>           # Удалить Pod
kubectl delete -f deployment.yaml   # Удалить по файлу
kubectl delete deployment --all     # Удалить все Deployment'ы

# === ОТЛАДКА ===
kubectl exec -it <pod-name> -- /bin/bash   # Зайти в контейнер
kubectl exec -it <pod-name> -- sh          # Если нет bash
kubectl port-forward <pod-name> 8080:80    # Проброс порта на localhost
kubectl top pods                            # Потребление ресурсов

# === МАСШТАБИРОВАНИЕ ===
kubectl scale deployment nginx --replicas=5  # Изменить количество реплик

# === РЕДАКТИРОВАНИЕ ===
kubectl edit deployment nginx        # Открыть в редакторе
```

### Полезные alias'ы

```bash
# Добавь в ~/.bashrc
alias k='kubectl'
alias kgp='kubectl get pods'
alias kgs='kubectl get services'
alias kgd='kubectl get deployments'
alias kga='kubectl get all'
alias kd='kubectl describe'
alias kl='kubectl logs'
alias kaf='kubectl apply -f'
```

---

## 5. Практика: первое приложение

### Шаг 1: Установка K3s (лёгкий production-ready кластер)

```bash
# Установка K3s (один узел, все роли)
curl -sfL https://get.k3s.io | sh -

# K3s автоматически установит kubectl
# Kubeconfig находится в /etc/rancher/k3s/k3s.yaml

# Настройка kubectl для обычного пользователя
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config

# Проверка
kubectl cluster-info
kubectl get nodes
```

**Почему K3s, а не Minikube:**
- K3s — production-ready, сертифицирован CNCF
- Бинарник < 100MB, потребляет ~512MB RAM
- Включает Traefik (Ingress), CoreDNS, local-path-provisioner
- Используется в Rancher для управления кластерами

### Шаг 2: Создание приложения

```bash
# Создай папку для манифестов
mkdir -p ~/k8s-demo && cd ~/k8s-demo
```

**Файл `deployment.yaml`:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hello
  template:
    metadata:
      labels:
        app: hello
    spec:
      containers:
      - name: hello
        image: gcr.io/google-samples/hello-app:1.0
        ports:
        - containerPort: 8080
```

**Файл `service.yaml`:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: hello-service
spec:
  selector:
    app: hello
  ports:
  - port: 80
    targetPort: 8080
  type: NodePort
```

### Шаг 3: Запуск

```bash
# Применяем манифесты
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Проверяем
kubectl get all

# Смотрим логи
kubectl logs -l app=hello

# Получаем URL для доступа (NodePort)
kubectl get svc hello-service
# Будет показан порт типа 80:3XXXX/TCP
# Доступ: http://<NODE-IP>:<NodePort>

# Или через port-forward (удобнее для разработки)
kubectl port-forward svc/hello-service 8080:80 &
curl http://localhost:8080
```

### Шаг 4: Эксперименты

```bash
# Убей один Pod — смотри как K8s создаст новый
kubectl delete pod -l app=hello --wait=false
kubectl get pods -w  # Смотри в реальном времени

# Масштабирование
kubectl scale deployment hello-app --replicas=5
kubectl get pods

# Обновление версии (rolling update)
kubectl set image deployment/hello-app hello=gcr.io/google-samples/hello-app:2.0
kubectl rollout status deployment/hello-app

# Откат
kubectl rollout undo deployment/hello-app
```

---

## 6. Конфигурация и секреты

### ConfigMap — конфигурация

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  DATABASE_HOST: "postgres.default.svc"
  DATABASE_PORT: "5432"
  LOG_LEVEL: "info"
  config.json: |
    {
      "feature_flag": true,
      "timeout": 30
    }
```

**Использование в Pod:**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app
spec:
  containers:
  - name: app
    image: myapp
    # Вариант 1: Как переменные окружения
    envFrom:
    - configMapRef:
        name: app-config
    # Вариант 2: Отдельные переменные
    env:
    - name: DB_HOST
      valueFrom:
        configMapKeyRef:
          name: app-config
          key: DATABASE_HOST
    # Вариант 3: Как файл
    volumeMounts:
    - name: config-volume
      mountPath: /etc/config
  volumes:
  - name: config-volume
    configMap:
      name: app-config
```

### Secret — секреты

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
type: Opaque
data:
  # Значения в base64!
  username: YWRtaW4=        # echo -n "admin" | base64
  password: cGFzc3dvcmQ=    # echo -n "password" | base64
```

```bash
# Создание из командной строки
kubectl create secret generic db-credentials \
  --from-literal=username=admin \
  --from-literal=password=password
```

**Использование:**
```yaml
env:
- name: DB_USER
  valueFrom:
    secretKeyRef:
      name: db-credentials
      key: username
- name: DB_PASS
  valueFrom:
    secretKeyRef:
      name: db-credentials
      key: password
```

---

## 7. Сеть в Kubernetes

### DNS внутри кластера

Kubernetes автоматически создаёт DNS-записи для Service'ов:

```
<service-name>.<namespace>.svc.cluster.local

# Примеры:
nginx-service.default.svc.cluster.local
postgres.database.svc.cluster.local
prometheus.monitoring.svc.cluster.local
```

```bash
# Из Pod'а можно обращаться:
curl http://nginx-service              # В том же namespace
curl http://nginx-service.default      # Полное имя
curl http://postgres.database          # Другой namespace
```

### Ingress — внешний доступ

**Ingress** = HTTP(S) роутер для внешнего трафика.

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: hello-service
            port:
              number: 80
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: api-service
            port:
              number: 8080
```

```
Internet → Ingress Controller → Service → Pod
              │
              ├─ myapp.com/     → hello-service
              └─ myapp.com/api  → api-service
```

---

## 8. Хранение данных

### Проблема

Pod'ы эфемерные — при перезапуске данные теряются.

### Решение: PersistentVolume (PV) и PersistentVolumeClaim (PVC)

```
┌─────────────────┐    запрос    ┌─────────────────┐    привязка    ┌─────────────────┐
│      Pod        │ ──────────── │      PVC        │ ────────────── │       PV        │
│                 │              │   (заявка)      │                │ (реальный диск) │
│  /data ────────────────────────┘                 │                │                 │
└─────────────────┘                                └────────────────└─────────────────┘
```

```yaml
# pvc.yaml — заявка на storage
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
spec:
  accessModes:
    - ReadWriteOnce      # Один Pod может писать
  resources:
    requests:
      storage: 10Gi      # Хочу 10GB
  storageClassName: standard
```

```yaml
# deployment с volume
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:14
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: postgres-data
```

---

## 9. Мониторинг и логи

> **Это то, что изучается на курсе по Observability!**

### Prometheus — сбор метрик

```yaml
# Prometheus собирает метрики с Pod'ов через annotations
apiVersion: v1
kind: Pod
metadata:
  name: myapp
  annotations:
    prometheus.io/scrape: "true"     # Собирать метрики
    prometheus.io/port: "8080"       # С какого порта
    prometheus.io/path: "/metrics"   # Endpoint метрик
```

### Grafana — визуализация

```
Prometheus (сбор) → Grafana (графики) → Alertmanager (алерты)
```

### ELK Stack — логи

```
App → Filebeat/Fluentd → Logstash → Elasticsearch → Kibana
        (сбор)           (обработка)   (хранение)   (UI)
```

### Типичный observability namespace

```bash
kubectl get pods -n monitoring

# NAME                                   READY   STATUS
# prometheus-server-xxx                  1/1     Running
# alertmanager-xxx                       1/1     Running
# grafana-xxx                            1/1     Running
# node-exporter-xxx                      1/1     Running

kubectl get pods -n logging

# NAME                                   READY   STATUS
# elasticsearch-master-0                 1/1     Running
# kibana-xxx                             1/1     Running
# fluentd-xxx                            1/1     Running
```

---

## 10. Практические задания

### Задание 1: Базовое развёртывание
1. Создай Deployment с nginx (3 реплики)
2. Создай Service типа NodePort
3. Убедись, что приложение доступно

### Задание 2: ConfigMap и Secret
1. Создай ConfigMap с настройками
2. Создай Secret с паролем
3. Примонтируй их к Pod'у
4. Проверь что переменные доступны внутри контейнера

### Задание 3: Масштабирование и обновление
1. Увеличь реплики до 5
2. Обнови image на новую версию
3. Наблюдай за rolling update
4. Откати обновление

### Задание 4: Debugging
1. Посмотри логи Pod'а
2. Зайди внутрь контейнера
3. Посмотри events в describe
4. Найди Pod, который потребляет много CPU

### Задание 5: Подготовка к курсу
1. Разверни Prometheus через Helm
2. Разверни Grafana
3. Настрой сбор метрик с nginx
4. Создай простой dashboard

---

## 11. Шпаргалка команд

```bash
# ===== ИНФОРМАЦИЯ О КЛАСТЕРЕ =====
kubectl cluster-info                    # Информация о кластере
kubectl get nodes                       # Список нод
kubectl get nodes -o wide               # С IP и версией

# ===== PODS =====
kubectl get pods                        # Все Pod'ы
kubectl get pods -A                     # Во всех namespace
kubectl get pods -o wide                # С IP и нодой
kubectl get pods -w                     # Watch (обновление)
kubectl describe pod <name>             # Детали
kubectl logs <pod> [-f] [--previous]    # Логи
kubectl exec -it <pod> -- /bin/sh       # Shell в контейнер
kubectl delete pod <name>               # Удалить
kubectl top pods                        # CPU/Memory

# ===== DEPLOYMENTS =====
kubectl get deployments                 # Список
kubectl describe deployment <name>      # Детали
kubectl scale deployment <name> --replicas=N
kubectl rollout status deployment <name>
kubectl rollout undo deployment <name>
kubectl set image deployment/<name> <container>=<image>

# ===== SERVICES =====
kubectl get services                    # Список
kubectl describe service <name>         # Детали
kubectl port-forward svc/<name> 8080:80 # Проброс порта

# ===== КОНФИГУРАЦИЯ =====
kubectl get configmaps                  # Список ConfigMap
kubectl get secrets                     # Список Secret
kubectl create configmap <name> --from-file=<path>
kubectl create secret generic <name> --from-literal=key=value

# ===== NAMESPACE =====
kubectl get namespaces                  # Список
kubectl create namespace <name>         # Создать
kubectl config set-context --current --namespace=<name>  # Переключить

# ===== ОБЩЕЕ =====
kubectl apply -f <file.yaml>            # Применить манифест
kubectl delete -f <file.yaml>           # Удалить по манифесту
kubectl get all                         # Все ресурсы
kubectl api-resources                   # Список всех типов ресурсов
kubectl explain <resource>              # Документация по ресурсу
```

---

## Дополнительные ресурсы

1. **Официальная документация:** https://kubernetes.io/docs/
2. **Интерактивный туториал:** https://kubernetes.io/docs/tutorials/kubernetes-basics/
3. **Katacoda (бесплатные лабы):** https://www.katacoda.com/courses/kubernetes
4. **Play with Kubernetes:** https://labs.play-with-k8s.com/

---

## Чек-лист готовности к курсу

- [ ] Понимаю разницу между Docker и Kubernetes
- [ ] Знаю основные компоненты (API Server, etcd, kubelet, etc.)
- [ ] Могу создать Deployment, Service, ConfigMap, Secret
- [ ] Умею использовать kubectl (get, describe, logs, exec)
- [ ] Понимаю как работает Service discovery (DNS)
- [ ] Знаю что такое Namespace и зачем нужен
- [ ] Могу отлаживать проблемы (logs, describe, events)
- [ ] Понимаю концепцию PV/PVC для storage
- [ ] Знаю что такое Ingress

**Если все галочки стоят — ты готов к курсу по Observability!**

---

# ЧАСТЬ 2: Продвинутые концепции

---

## 12. Полный каталог объектов Kubernetes

### Карта всех сущностей

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        KUBERNETES OBJECTS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         WORKLOADS (Нагрузки)                        │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │    │
│  │  │    Pod       │ │  Deployment  │ │  StatefulSet │ │  DaemonSet │  │    │
│  │  │  (базовый)   │ │  (stateless) │ │  (stateful)  │ │  (на ноду) │  │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │    │
│  │  │  ReplicaSet  │ │     Job      │ │   CronJob    │                 │    │
│  │  │  (реплики)   │ │ (однократно) │ │ (по расписан)│                 │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          NETWORKING (Сеть)                          │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │    │
│  │  │   Service    │ │   Ingress    │ │ NetworkPolicy│ │  Endpoints │  │    │
│  │  │  (доступ)    │ │  (HTTP роут) │ │  (firewall)  │ │  (адреса)  │  │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      CONFIGURATION (Конфигурация)                   │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │    │
│  │  │  ConfigMap   │ │    Secret    │ │ ServiceAccount│                │    │
│  │  │ (настройки)  │ │  (секреты)   │ │  (identity)  │                 │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         STORAGE (Хранение)                          │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │    │
│  │  │PersistentVol │ │     PVC      │ │ StorageClass │                 │    │
│  │  │   (диск)     │ │  (заявка)    │ │  (тип диска) │                 │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                           RBAC (Доступ)                             │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │    │
│  │  │     Role     │ │ ClusterRole  │ │ RoleBinding  │ │ClusterRole │  │    │
│  │  │ (namespace)  │ │  (кластер)   │ │  (привязка)  │ │  Binding   │  │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      CLUSTER (Кластер)                              │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │    │
│  │  │  Namespace   │ │    Node      │ │ResourceQuota │ │ LimitRange │  │    │
│  │  │ (изоляция)   │ │  (сервер)    │ │  (лимиты)    │ │ (дефолты)  │  │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Таблица всех объектов

| Объект | Сокращение | Описание | Scope |
|--------|------------|----------|-------|
| **Pod** | po | Минимальная единица, один или несколько контейнеров | Namespace |
| **ReplicaSet** | rs | Поддерживает N копий Pod'ов | Namespace |
| **Deployment** | deploy | Управляет ReplicaSet, rolling updates | Namespace |
| **StatefulSet** | sts | Для stateful приложений (БД) | Namespace |
| **DaemonSet** | ds | По одному Pod на каждую ноду | Namespace |
| **Job** | job | Однократное выполнение задачи | Namespace |
| **CronJob** | cj | Задачи по расписанию | Namespace |
| **Service** | svc | Стабильный доступ к Pod'ам | Namespace |
| **Endpoints** | ep | Список IP адресов для Service | Namespace |
| **Ingress** | ing | HTTP/HTTPS роутинг | Namespace |
| **NetworkPolicy** | netpol | Сетевые правила (firewall) | Namespace |
| **ConfigMap** | cm | Конфигурация (не секретная) | Namespace |
| **Secret** | secret | Секретные данные (base64) | Namespace |
| **PersistentVolume** | pv | Физический/виртуальный диск | Cluster |
| **PersistentVolumeClaim** | pvc | Запрос на storage | Namespace |
| **StorageClass** | sc | Тип storage (SSD, HDD, etc.) | Cluster |
| **ServiceAccount** | sa | Identity для Pod'ов | Namespace |
| **Role** | role | Права в namespace | Namespace |
| **ClusterRole** | clusterrole | Права на весь кластер | Cluster |
| **RoleBinding** | rolebinding | Привязка Role к пользователю | Namespace |
| **ClusterRoleBinding** | clusterrolebinding | Привязка ClusterRole | Cluster |
| **Namespace** | ns | Изоляция ресурсов | Cluster |
| **Node** | no | Сервер в кластере | Cluster |
| **ResourceQuota** | quota | Лимиты на namespace | Namespace |
| **LimitRange** | limits | Дефолтные лимиты для Pod'ов | Namespace |

```bash
# Посмотреть все доступные ресурсы
kubectl api-resources

# Документация по любому ресурсу
kubectl explain pod
kubectl explain pod.spec.containers
```

---

## 13. Типы Workloads — подробно

### Deployment vs StatefulSet vs DaemonSet

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORKLOAD TYPES                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DEPLOYMENT (Stateless)              STATEFULSET (Stateful)                 │
│  ┌─────────────────────┐             ┌─────────────────────┐                │
│  │ nginx-abc123        │             │ postgres-0          │ ← Стабильное   │
│  │ nginx-def456        │             │ postgres-1          │   имя!         │
│  │ nginx-ghi789        │             │ postgres-2          │                │
│  └─────────────────────┘             └─────────────────────┘                │
│  • Случайные имена                   • Порядковые имена (0, 1, 2)           │
│  • Взаимозаменяемые                  • Уникальная идентичность              │
│  • Любой порядок запуска             • Строгий порядок (0→1→2)              │
│  • Shared storage (или нет)          • Персональный PVC для каждого         │
│                                                                              │
│  DAEMONSET (На каждой ноде)          JOB / CRONJOB (Задачи)                 │
│  ┌─────────────────────┐             ┌─────────────────────┐                │
│  │ Node1: fluentd      │             │ Job: backup-db      │                │
│  │ Node2: fluentd      │             │   └─ Pod (завершён) │                │
│  │ Node3: fluentd      │             │                     │                │
│  └─────────────────────┘             │ CronJob: "0 2 * * *"│                │
│  • Ровно 1 Pod на ноду               │   └─ Job (каждую    │                │
│  • Мониторинг, логи, сеть            │       ночь в 2:00)  │                │
│                                      └─────────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### StatefulSet — для баз данных

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: "postgres"      # Headless Service
  replicas: 3
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:14
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:        # Каждому Pod свой PVC!
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi
```

**Особенности StatefulSet:**
- Pod'ы: `postgres-0`, `postgres-1`, `postgres-2` (стабильные имена)
- DNS: `postgres-0.postgres.default.svc.cluster.local`
- Запуск строго по порядку: 0 → 1 → 2
- Удаление в обратном порядке: 2 → 1 → 0
- Каждый Pod получает свой PVC

### DaemonSet — на каждую ноду

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
  namespace: logging
spec:
  selector:
    matchLabels:
      name: fluentd
  template:
    metadata:
      labels:
        name: fluentd
    spec:
      containers:
      - name: fluentd
        image: fluentd:latest
        volumeMounts:
        - name: varlog
          mountPath: /var/log
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
```

**Используется для:**
- Сбор логов (Fluentd, Filebeat)
- Мониторинг нод (node-exporter)
- Сетевые плагины (CNI)
- Storage драйверы

### Job и CronJob

```yaml
# Однократная задача
apiVersion: batch/v1
kind: Job
metadata:
  name: backup-database
spec:
  template:
    spec:
      containers:
      - name: backup
        image: postgres:14
        command: ["pg_dump", "-h", "postgres", "-U", "admin", "mydb"]
      restartPolicy: Never    # Важно!
  backoffLimit: 3             # Попытки при ошибке
---
# По расписанию (cron синтаксис)
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
spec:
  schedule: "0 2 * * *"       # Каждый день в 2:00
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:14
            command: ["pg_dump", "-h", "postgres", "-U", "admin", "mydb"]
          restartPolicy: Never
```

---

## 14. Labels и Selectors — система связей

### Как объекты находят друг друга

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LABELS & SELECTORS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐                                                    │
│  │     Deployment      │                                                    │
│  │  selector:          │                                                    │
│  │    app: nginx ──────┼──────────────┐                                    │
│  │    env: prod        │              │                                    │
│  └─────────────────────┘              │ matchLabels                        │
│                                       ▼                                    │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│  │       Pod 1         │  │       Pod 2         │  │       Pod 3         │ │
│  │  labels:            │  │  labels:            │  │  labels:            │ │
│  │    app: nginx  ✓    │  │    app: nginx  ✓    │  │    app: redis  ✗    │ │
│  │    env: prod   ✓    │  │    env: prod   ✓    │  │    env: prod   ✓    │ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘ │
│         ▲                        ▲                                         │
│         │                        │                                         │
│         └────────────────────────┘                                         │
│                      │                                                      │
│  ┌─────────────────────┐                                                    │
│  │      Service        │                                                    │
│  │  selector:          │                                                    │
│  │    app: nginx ──────┘                                                    │
│  └─────────────────────┘                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Практика с labels

```yaml
# Pod с labels
apiVersion: v1
kind: Pod
metadata:
  name: nginx-prod
  labels:
    app: nginx
    env: production
    team: backend
    version: v1.21
```

```bash
# Фильтрация по labels
kubectl get pods -l app=nginx                    # app=nginx
kubectl get pods -l app=nginx,env=prod           # AND
kubectl get pods -l 'app in (nginx, redis)'      # OR
kubectl get pods -l app!=nginx                   # NOT
kubectl get pods -l 'env in (prod, staging)'     # IN
kubectl get pods -l '!env'                       # Без label env

# Показать labels
kubectl get pods --show-labels

# Добавить label
kubectl label pods nginx-prod tier=frontend

# Удалить label
kubectl label pods nginx-prod tier-
```

### Annotations vs Labels

| Labels | Annotations |
|--------|-------------|
| Для **выбора** объектов | Для **метаданных** |
| Короткие значения | Любой размер |
| Используются selectors | Не используются для выбора |
| `app: nginx` | `description: "Main web server"` |

```yaml
metadata:
  labels:
    app: nginx                    # Для селекторов
  annotations:
    description: "Production nginx"
    prometheus.io/scrape: "true"  # Для Prometheus
    helm.sh/chart: "nginx-1.0"    # Для Helm
```

---

## 15. Resource Limits — управление ресурсами

### Requests vs Limits

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESOURCE MANAGEMENT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  requests: Сколько ГАРАНТИРОВАННО получит контейнер                         │
│  limits:   Сколько МАКСИМУМ может использовать                              │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                           NODE (8 CPU, 16GB RAM)                    │    │
│  │                                                                      │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │    │
│  │  │     Pod A       │  │     Pod B       │  │     Pod C       │     │    │
│  │  │ requests:       │  │ requests:       │  │ requests:       │     │    │
│  │  │   cpu: 1        │  │   cpu: 2        │  │   cpu: 1        │     │    │
│  │  │   memory: 2Gi   │  │   memory: 4Gi   │  │   memory: 2Gi   │     │    │
│  │  │ limits:         │  │ limits:         │  │ limits:         │     │    │
│  │  │   cpu: 2        │  │   cpu: 4        │  │   cpu: 2        │     │    │
│  │  │   memory: 4Gi   │  │   memory: 8Gi   │  │   memory: 4Gi   │     │    │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘     │    │
│  │                                                                      │    │
│  │  Используемые requests: 4 CPU, 8GB (из 8 CPU, 16GB)                 │    │
│  │  Scheduler разместит Pod если requests помещаются!                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Что происходит при превышении:                                             │
│  • CPU limit:    Throttling (замедление)                                    │
│  • Memory limit: OOMKilled (контейнер убивается)                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Пример с resources

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.21
        resources:
          requests:
            memory: "128Mi"   # 128 мегабайт гарантированно
            cpu: "250m"       # 250 millicpu = 0.25 CPU
          limits:
            memory: "256Mi"   # Максимум 256 мегабайт
            cpu: "500m"       # Максимум 0.5 CPU
```

### Единицы измерения

| Ресурс | Единицы | Примеры |
|--------|---------|---------|
| **CPU** | millicpu (m) | `100m` = 0.1 CPU, `1000m` = 1 CPU, `1` = 1 CPU |
| **Memory** | bytes | `128Mi` = 128 MiB, `1Gi` = 1 GiB, `500M` = 500 MB |

### LimitRange — дефолтные лимиты

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: production
spec:
  limits:
  - default:          # Дефолтные limits
      cpu: "500m"
      memory: "512Mi"
    defaultRequest:   # Дефолтные requests
      cpu: "100m"
      memory: "128Mi"
    max:              # Максимально допустимые limits
      cpu: "2"
      memory: "2Gi"
    min:              # Минимально допустимые requests
      cpu: "50m"
      memory: "64Mi"
    type: Container
```

### ResourceQuota — лимиты на namespace

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "10"        # Всего 10 CPU requests
    requests.memory: "20Gi"   # Всего 20GB memory requests
    limits.cpu: "20"          # Всего 20 CPU limits
    limits.memory: "40Gi"     # Всего 40GB memory limits
    pods: "50"                # Максимум 50 Pod'ов
    services: "10"            # Максимум 10 Service'ов
```

---

## 16. Probes — проверки здоровья

### Три типа проверок

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROBES                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. STARTUP PROBE (только при старте)                                       │
│     "Приложение запустилось?"                                               │
│     ┌───────────────────────────────────────────────────────┐              │
│     │  Container Starting ──► Startup Probe ──► Ready       │              │
│     │                              │                         │              │
│     │                         FAIL │ (перезапуск)            │              │
│     └───────────────────────────────────────────────────────┘              │
│                                                                              │
│  2. READINESS PROBE (постоянно)                                             │
│     "Готов принимать трафик?"                                               │
│     ┌───────────────────────────────────────────────────────┐              │
│     │  Pod Ready ──► Readiness OK ──► Service включает      │              │
│     │                     │                                   │              │
│     │               FAIL  │ (убирает из Service,             │              │
│     │                     │  Pod продолжает работать)        │              │
│     └───────────────────────────────────────────────────────┘              │
│                                                                              │
│  3. LIVENESS PROBE (постоянно)                                              │
│     "Приложение живо?"                                                      │
│     ┌───────────────────────────────────────────────────────┐              │
│     │  Pod Running ──► Liveness OK ──► Всё хорошо           │              │
│     │                      │                                  │              │
│     │                FAIL  │ (ПЕРЕЗАПУСК контейнера!)        │              │
│     └───────────────────────────────────────────────────────┘              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Полный пример с probes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: myapp:1.0
        ports:
        - containerPort: 8080

        # Startup: ждём пока приложение запустится
        startupProbe:
          httpGet:
            path: /healthz
            port: 8080
          failureThreshold: 30      # 30 попыток
          periodSeconds: 10         # каждые 10 сек = 5 минут на запуск

        # Readiness: готов к трафику?
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5    # Ждать 5 сек после старта
          periodSeconds: 5          # Проверять каждые 5 сек
          failureThreshold: 3       # 3 ошибки = не готов

        # Liveness: жив?
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 10
          failureThreshold: 3       # 3 ошибки = перезапуск
```

### Типы проверок

```yaml
# HTTP GET
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
    httpHeaders:
    - name: Custom-Header
      value: "check"

# TCP Socket
livenessProbe:
  tcpSocket:
    port: 3306          # Для MySQL, Postgres

# Exec Command
livenessProbe:
  exec:
    command:
    - cat
    - /tmp/healthy
```

---

## 17. RBAC — управление доступом

### Модель безопасности

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RBAC MODEL                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  WHO (Кто)              WHAT (Что может делать)      WHERE (Где)            │
│  ┌──────────────┐       ┌──────────────────────┐     ┌───────────────┐      │
│  │    User      │       │        Role          │     │   Namespace   │      │
│  │ ServiceAcct  │ ───── │  • get pods          │ ─── │   (default)   │      │
│  │    Group     │       │  • list deployments  │     │               │      │
│  └──────────────┘       │  • create secrets    │     └───────────────┘      │
│        │                └──────────────────────┘            │               │
│        │                         │                          │               │
│        └─────────────────────────┼──────────────────────────┘               │
│                                  │                                          │
│                         ┌────────▼────────┐                                 │
│                         │   RoleBinding   │                                 │
│                         │ (связывает)     │                                 │
│                         └─────────────────┘                                 │
│                                                                              │
│  ClusterRole + ClusterRoleBinding = права на весь кластер                   │
│  Role + RoleBinding = права только в namespace                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Role и RoleBinding

```yaml
# Role — определяет права
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: default
rules:
- apiGroups: [""]           # "" = core API group
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list"]
---
# RoleBinding — привязывает права к пользователю/сервису
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: default
subjects:
- kind: User
  name: developer
  apiGroup: rbac.authorization.k8s.io
- kind: ServiceAccount
  name: my-app
  namespace: default
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

### ServiceAccount для Pod'ов

```yaml
# ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus
  namespace: monitoring
---
# Deployment использует ServiceAccount
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
spec:
  template:
    spec:
      serviceAccountName: prometheus    # Привязываем!
      containers:
      - name: prometheus
        image: prom/prometheus
```

### Verbs (действия)

| Verb | Описание |
|------|----------|
| `get` | Получить один ресурс |
| `list` | Получить список |
| `watch` | Следить за изменениями |
| `create` | Создать |
| `update` | Обновить |
| `patch` | Частичное обновление |
| `delete` | Удалить |
| `deletecollection` | Удалить коллекцию |

---

## 18. Network Policies — сетевой firewall

### Изоляция трафика

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          NETWORK POLICIES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Без NetworkPolicy:              С NetworkPolicy:                           │
│  ┌─────────────────────┐         ┌─────────────────────┐                   │
│  │  All traffic allowed │         │  Only allowed traffic│                   │
│  │                      │         │                      │                   │
│  │  frontend ←→ backend │         │  frontend ──► backend│                   │
│  │  frontend ←→ db      │         │  backend ──► db      │                   │
│  │  backend ←→ db       │         │  frontend ✗─► db     │                   │
│  └─────────────────────┘         └─────────────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Пример: разрешить только frontend → backend

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-allow-frontend
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: backend           # Применяется к backend Pod'ам
  policyTypes:
  - Ingress                  # Входящий трафик
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend      # Разрешить только от frontend
    ports:
    - protocol: TCP
      port: 8080
```

### Пример: запретить весь входящий трафик

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
  namespace: production
spec:
  podSelector: {}            # Все Pod'ы в namespace
  policyTypes:
  - Ingress
  ingress: []                # Пустой список = всё запрещено
```

---

## 19. Helm — пакетный менеджер

### Что такое Helm

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              HELM                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Без Helm:                          С Helm:                                 │
│  ┌─────────────────────────┐        ┌─────────────────────────┐            │
│  │  kubectl apply -f       │        │  helm install prometheus│            │
│  │    deployment.yaml      │        │    prometheus/prometheus│            │
│  │    service.yaml         │        │                         │            │
│  │    configmap.yaml       │        │  (автоматически создаёт │            │
│  │    secret.yaml          │        │   все нужные ресурсы)   │            │
│  │    ingress.yaml         │        └─────────────────────────┘            │
│  │    ...                  │                                                │
│  └─────────────────────────┘                                                │
│                                                                              │
│  Chart = пакет с шаблонами                                                  │
│  Release = установленный Chart                                              │
│  Repository = место хранения Charts                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Основные команды Helm

```bash
# Установка Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Добавить репозиторий
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Поиск Charts
helm search repo prometheus
helm search hub grafana          # Искать во всех репозиториях

# Установка
helm install my-prometheus prometheus-community/prometheus
helm install my-grafana grafana/grafana -n monitoring --create-namespace

# С кастомными значениями
helm install my-prometheus prometheus-community/prometheus \
  --set server.persistentVolume.size=50Gi \
  --set alertmanager.enabled=true

# Или из файла
helm install my-prometheus prometheus-community/prometheus -f values.yaml

# Список установленных
helm list
helm list -A                     # Все namespace

# Обновление
helm upgrade my-prometheus prometheus-community/prometheus

# Откат
helm rollback my-prometheus 1    # К версии 1

# Удаление
helm uninstall my-prometheus

# Посмотреть values (настройки)
helm show values prometheus-community/prometheus

# Посмотреть что будет создано (dry-run)
helm install my-prometheus prometheus-community/prometheus --dry-run
```

### Структура Helm Chart

```
mychart/
├── Chart.yaml          # Метаданные chart
├── values.yaml         # Дефолтные значения
├── templates/          # Шаблоны K8s манифестов
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   └── _helpers.tpl    # Вспомогательные функции
├── charts/             # Зависимости
└── README.md
```

---

## 20. Troubleshooting — поиск проблем

### Алгоритм диагностики

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TROUBLESHOOTING FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Pod не запускается                                                      │
│     │                                                                        │
│     ├──► kubectl get pods              # Статус?                            │
│     ├──► kubectl describe pod <name>   # Events?                            │
│     └──► kubectl logs <name>           # Логи?                              │
│                                                                              │
│  2. Возможные статусы Pod                                                   │
│     │                                                                        │
│     ├── Pending      → Нет ресурсов или PVC не привязан                    │
│     ├── ImagePullBackOff → Проблема с image (имя, registry, credentials)   │
│     ├── CrashLoopBackOff → Приложение падает (смотри логи!)                │
│     ├── CreateContainerError → Проблема с конфигом                         │
│     ├── OOMKilled    → Не хватило памяти (увеличь limits)                  │
│     └── Evicted      → Нода под нагрузкой (ресурсы кончились)              │
│                                                                              │
│  3. Service не работает                                                     │
│     │                                                                        │
│     ├──► kubectl get endpoints <svc>   # Есть ли endpoints?                │
│     ├──► kubectl get pods -l <selector># Labels совпадают?                 │
│     └──► kubectl port-forward          # Проверь Pod напрямую              │
│                                                                              │
│  4. Ingress не работает                                                     │
│     │                                                                        │
│     ├──► kubectl get ingress           # Создан?                           │
│     ├──► kubectl describe ingress      # Backend?                          │
│     └──► kubectl logs -n ingress-nginx # Логи контроллера                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Полезные команды для диагностики

```bash
# ===== POD ДИАГНОСТИКА =====
kubectl get pods                          # Статус всех Pod'ов
kubectl get pods -o wide                  # + IP и Node
kubectl describe pod <name>               # Детали + Events
kubectl logs <pod> [-c container]         # Логи
kubectl logs <pod> --previous             # Логи упавшего контейнера
kubectl logs -f <pod>                     # Follow
kubectl exec -it <pod> -- sh              # Зайти внутрь

# ===== EVENTS =====
kubectl get events                        # Все события
kubectl get events --sort-by='.lastTimestamp'
kubectl get events --field-selector type=Warning

# ===== SERVICE ДИАГНОСТИКА =====
kubectl get svc                           # Список сервисов
kubectl get endpoints                     # IP Pod'ов за сервисами
kubectl describe svc <name>               # Детали

# ===== DNS ТЕСТ =====
kubectl run -it --rm debug --image=busybox -- nslookup <service>

# ===== СЕТЬ ТЕСТ =====
kubectl run -it --rm debug --image=nicolaka/netshoot -- bash
# Внутри: curl, ping, dig, tcpdump, etc.

# ===== РЕСУРСЫ =====
kubectl top nodes                         # CPU/Memory по нодам
kubectl top pods                          # CPU/Memory по Pod'ам
kubectl describe node <name>              # Allocatable vs Requests

# ===== RBAC ТЕСТ =====
kubectl auth can-i create pods            # Могу ли я?
kubectl auth can-i create pods --as=system:serviceaccount:default:myapp
```

### Частые ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `ImagePullBackOff` | Image не найден | Проверь имя image, registry credentials |
| `CrashLoopBackOff` | Приложение падает | `kubectl logs --previous`, проверь команду запуска |
| `Pending` (долго) | Нет ресурсов | `kubectl describe pod` → Events, увеличь кластер |
| `OOMKilled` | Memory limit | Увеличь `limits.memory` |
| `Evicted` | Node под давлением | Добавь ноды или оптимизируй приложения |
| `CreateContainerConfigError` | Ошибка в ConfigMap/Secret | Проверь что ConfigMap/Secret существует |
| Service без Endpoints | Label mismatch | Сравни selector в Service и labels в Pod |

---

## 21. Реальные сценарии развёртывания

### Сценарий 1: Web-приложение + БД

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: myapp
---
# postgres-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: myapp
type: Opaque
stringData:
  POSTGRES_USER: myapp
  POSTGRES_PASSWORD: secretpassword
  POSTGRES_DB: myapp_db
---
# postgres-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: myapp
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
---
# postgres-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: myapp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:14
        envFrom:
        - secretRef:
            name: postgres-secret
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: postgres-pvc
---
# postgres-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: myapp
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
---
# web-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: web-config
  namespace: myapp
data:
  DATABASE_HOST: postgres.myapp.svc.cluster.local
  DATABASE_PORT: "5432"
---
# web-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: myregistry/myapp:1.0
        envFrom:
        - configMapRef:
            name: web-config
        - secretRef:
            name: postgres-secret
        ports:
        - containerPort: 8080
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
---
# web-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: myapp
spec:
  selector:
    app: web
  ports:
  - port: 80
    targetPort: 8080
---
# web-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web
  namespace: myapp
spec:
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: web
            port:
              number: 80
```

```bash
# Развернуть всё
kubectl apply -f namespace.yaml
kubectl apply -f .

# Проверить
kubectl get all -n myapp
kubectl get pvc -n myapp
kubectl logs -l app=web -n myapp
```

---

## 22. Подготовка к курсу Observability

### Минимальный стек для практики

```bash
# 1. Установить Prometheus + Grafana через Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Prometheus (метрики)
helm install prometheus prometheus-community/prometheus \
  --namespace monitoring --create-namespace

# Grafana (визуализация)
helm install grafana grafana/grafana \
  --namespace monitoring \
  --set adminPassword=admin123

# 2. Доступ к Grafana
kubectl port-forward svc/grafana 3000:80 -n monitoring
# Открой http://localhost:3000 (admin / admin123)

# 3. Проверить что всё работает
kubectl get pods -n monitoring
```

### Что учить дальше

| Тема | Для курса |
|------|-----------|
| Prometheus Queries (PromQL) | Модуль 2: Метрики |
| Grafana Dashboards | Модуль 2: Метрики |
| Alertmanager | Модуль 2: Метрики |
| Elasticsearch + Kibana | Модуль 3: Логи |
| Fluentd / Filebeat | Модуль 3: Логи |
| Jaeger + OpenTelemetry | Модуль 4: Трассировки |

---

## Итоговый чек-лист (расширенный)

### Базовый уровень
- [ ] Архитектура: Control Plane, Workers, etcd
- [ ] Объекты: Pod, Deployment, Service, ConfigMap, Secret
- [ ] kubectl: get, describe, logs, exec, apply
- [ ] Namespaces и изоляция

### Средний уровень
- [ ] StatefulSet, DaemonSet, Job, CronJob
- [ ] Labels, Selectors, Annotations
- [ ] Resources: requests, limits
- [ ] Probes: startup, readiness, liveness
- [ ] PV, PVC, StorageClass
- [ ] Ingress и DNS

### Продвинутый уровень
- [ ] RBAC: Role, ClusterRole, Bindings
- [ ] NetworkPolicy
- [ ] Helm: install, upgrade, values
- [ ] Troubleshooting

### Для курса Observability
- [ ] Prometheus установлен и работает
- [ ] Grafana подключена к Prometheus
- [ ] Понимаю annotations для scraping метрик
- [ ] Знаю как смотреть логи Pod'ов

**Удачи на курсе!**

---

## 23. Сети Kubernetes — глубокое погружение

### Базовые принципы сети K8s

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KUBERNETES NETWORKING MODEL                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ПРАВИЛА:                                                                    │
│  1. Все Pod'ы могут общаться друг с другом БЕЗ NAT                          │
│  2. Все ноды могут общаться со всеми Pod'ами БЕЗ NAT                        │
│  3. IP, который Pod видит у себя = IP, который видят другие                │
│                                                                              │
│  Это называется "flat network" — плоская сеть                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Сетевые уровни в Kubernetes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NETWORK LAYERS                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  УРОВЕНЬ 4: INGRESS (L7 - HTTP/HTTPS)                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Internet → Ingress Controller → myapp.com/api → Service → Pod     │    │
│  │                                  myapp.com/web → Service → Pod     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  УРОВЕНЬ 3: SERVICE (L4 - TCP/UDP)                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ClusterIP: 10.96.0.1:80 ──► Pod 10.244.1.5:8080                   │    │
│  │                          ──► Pod 10.244.2.3:8080                   │    │
│  │                          ──► Pod 10.244.3.7:8080                   │    │
│  │  (kube-proxy делает балансировку через iptables/IPVS)             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  УРОВЕНЬ 2: POD NETWORK (L3 - IP)                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Pod 10.244.1.5 ←──────────────────────────→ Pod 10.244.2.3        │    │
│  │       (Node 1)            CNI Plugin              (Node 2)          │    │
│  │                     (Calico/Flannel/Cilium)                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  УРОВЕНЬ 1: NODE NETWORK (физическая сеть)                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Node 1 (192.168.1.10) ←───── Switch ────→ Node 2 (192.168.1.11)  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### IP-адресация в кластере

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          IP ADDRESSING                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ТРИ РАЗНЫХ IP-ДИАПАЗОНА:                                                   │
│                                                                              │
│  1. NODE IPs (физические/облачные)                                          │
│     └─ 192.168.1.0/24                                                       │
│        ├─ node-1: 192.168.1.10                                              │
│        ├─ node-2: 192.168.1.11                                              │
│        └─ node-3: 192.168.1.12                                              │
│                                                                              │
│  2. POD IPs (виртуальные, CNI выделяет)                                     │
│     └─ 10.244.0.0/16 (Pod CIDR)                                             │
│        ├─ node-1 pods: 10.244.1.0/24                                        │
│        ├─ node-2 pods: 10.244.2.0/24                                        │
│        └─ node-3 pods: 10.244.3.0/24                                        │
│                                                                              │
│  3. SERVICE IPs (виртуальные, kube-proxy)                                   │
│     └─ 10.96.0.0/12 (Service CIDR)                                          │
│        ├─ kubernetes: 10.96.0.1                                             │
│        ├─ kube-dns: 10.96.0.10                                              │
│        └─ my-service: 10.96.45.123                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pod-to-Pod коммуникация

#### На одной ноде

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POD-TO-POD (Same Node)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────── NODE 1 ───────────────────────────────────────────────┐       │
│  │                                                                    │       │
│  │  ┌─────────┐     veth pair      ┌──────────────┐     veth pair   │       │
│  │  │  Pod A  │ ◄──────────────────┤              ├─────────────────►│       │
│  │  │10.244.1.2│     eth0          │    cbr0     │         eth0    │       │
│  │  └─────────┘                    │  (bridge)   │                  │       │
│  │                                 │ 10.244.1.1  │                  │       │
│  │  ┌─────────┐     veth pair      │              │     veth pair   │       │
│  │  │  Pod B  │ ◄──────────────────┤              ├─────────────────►│       │
│  │  │10.244.1.3│     eth0          └──────────────┘         eth0    │       │
│  │  └─────────┘                                                      │       │
│  │                                                                    │       │
│  │  Пакет: 10.244.1.2 → 10.244.1.3 (через bridge напрямую)          │       │
│  │                                                                    │       │
│  └────────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### На разных нодах

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POD-TO-POD (Different Nodes)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────── NODE 1 ───────┐                    ┌─────── NODE 2 ───────┐       │
│  │                       │                    │                       │       │
│  │  ┌─────────┐         │                    │         ┌─────────┐  │       │
│  │  │  Pod A  │         │                    │         │  Pod B  │  │       │
│  │  │10.244.1.2│        │                    │        │10.244.2.3│  │       │
│  │  └────┬────┘         │                    │         └────┬────┘  │       │
│  │       │ eth0         │                    │              │ eth0  │       │
│  │       ▼              │                    │              ▼       │       │
│  │  ┌─────────┐         │                    │         ┌─────────┐  │       │
│  │  │  cbr0   │         │                    │         │  cbr0   │  │       │
│  │  │10.244.1.1│        │                    │        │10.244.2.1│  │       │
│  │  └────┬────┘         │                    │         └────┬────┘  │       │
│  │       │              │                    │              │       │       │
│  │       ▼              │                    │              ▼       │       │
│  │  ┌─────────┐         │                    │         ┌─────────┐  │       │
│  │  │  eth0   │         │                    │         │  eth0   │  │       │
│  │  │192.168.1.10│◄─────┼─── Overlay/VXLAN ──┼────────►│192.168.1.11│ │       │
│  │  └─────────┘         │    или routing     │         └─────────┘  │       │
│  │                       │                    │                       │       │
│  └───────────────────────┘                    └───────────────────────┘       │
│                                                                              │
│  Маршрут: 10.244.1.2 → cbr0 → eth0 → [overlay] → eth0 → cbr0 → 10.244.2.3  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### CNI — Container Network Interface

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CNI PLUGINS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CNI = стандарт для настройки сети контейнеров                              │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  kubelet                                                            │     │
│  │     │                                                               │     │
│  │     │ "Создай Pod"                                                  │     │
│  │     ▼                                                               │     │
│  │  CNI Plugin (Calico/Flannel/Cilium/Weave)                          │     │
│  │     │                                                               │     │
│  │     ├── Создаёт veth pair                                          │     │
│  │     ├── Назначает IP из CIDR                                       │     │
│  │     ├── Настраивает маршруты                                       │     │
│  │     └── Настраивает iptables/eBPF                                  │     │
│  │                                                                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  Популярные CNI:                                                            │
│  ┌─────────────┬─────────────┬──────────────┬─────────────────────────┐     │
│  │   Calico    │   Flannel   │    Cilium    │        Weave           │     │
│  ├─────────────┼─────────────┼──────────────┼─────────────────────────┤     │
│  │ BGP routing │ VXLAN/UDP   │ eBPF         │ Mesh overlay           │     │
│  │ Network     │ Простой     │ Network      │ Encryption             │     │
│  │ Policies    │ Без policies│ Policies L7  │ Network Policies       │     │
│  │ Production  │ Небольшие   │ High perf    │ Простой setup          │     │
│  │ grade       │ кластеры    │ Observability│                        │     │
│  └─────────────┴─────────────┴──────────────┴─────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Service — как работает внутри

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SERVICE INTERNALS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Service (ClusterIP: 10.96.45.123)                                          │
│                                                                              │
│  1. kube-proxy (на каждой ноде) создаёт правила:                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          IPTABLES MODE                              │    │
│  │                                                                      │    │
│  │  -A KUBE-SERVICES -d 10.96.45.123/32 -p tcp --dport 80              │    │
│  │      -j KUBE-SVC-XXXX                                               │    │
│  │                                                                      │    │
│  │  -A KUBE-SVC-XXXX -m statistic --mode random --probability 0.333    │    │
│  │      -j KUBE-SEP-AAAA (Pod 1)                                       │    │
│  │  -A KUBE-SVC-XXXX -m statistic --mode random --probability 0.500    │    │
│  │      -j KUBE-SEP-BBBB (Pod 2)                                       │    │
│  │  -A KUBE-SVC-XXXX                                                   │    │
│  │      -j KUBE-SEP-CCCC (Pod 3)                                       │    │
│  │                                                                      │    │
│  │  -A KUBE-SEP-AAAA -p tcp -j DNAT --to-destination 10.244.1.5:8080  │    │
│  │  -A KUBE-SEP-BBBB -p tcp -j DNAT --to-destination 10.244.2.3:8080  │    │
│  │  -A KUBE-SEP-CCCC -p tcp -j DNAT --to-destination 10.244.3.7:8080  │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  2. Пакет к Service:                                                        │
│     Client → 10.96.45.123:80 → [DNAT] → 10.244.1.5:8080 → Pod              │
│                                                                              │
│  3. IPVS MODE (более производительный для больших кластеров):              │
│     ipvsadm -L -n                                                           │
│     TCP 10.96.45.123:80 rr                                                  │
│       -> 10.244.1.5:8080    Masq   1      0          0                      │
│       -> 10.244.2.3:8080    Masq   1      0          0                      │
│       -> 10.244.3.7:8080    Masq   1      0          0                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### DNS в Kubernetes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KUBERNETES DNS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CoreDNS (kube-dns) — DNS-сервер кластера                                   │
│  ClusterIP: 10.96.0.10                                                      │
│                                                                              │
│  DNS-записи автоматически создаются для:                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SERVICES:                                                          │    │
│  │                                                                      │    │
│  │  <service>.<namespace>.svc.cluster.local                            │    │
│  │                                                                      │    │
│  │  Примеры:                                                           │    │
│  │  • nginx.default.svc.cluster.local      → 10.96.45.123             │    │
│  │  • postgres.database.svc.cluster.local  → 10.96.78.45              │    │
│  │  • prometheus.monitoring.svc.cluster.local → 10.96.12.34           │    │
│  │                                                                      │    │
│  │  Короткие имена (внутри namespace):                                 │    │
│  │  • nginx              → nginx.default.svc.cluster.local            │    │
│  │  • nginx.default      → nginx.default.svc.cluster.local            │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  PODS (только для StatefulSet с headless service):                  │    │
│  │                                                                      │    │
│  │  <pod-name>.<service>.<namespace>.svc.cluster.local                 │    │
│  │                                                                      │    │
│  │  Примеры (StatefulSet "postgres" с headless service):               │    │
│  │  • postgres-0.postgres.default.svc.cluster.local → 10.244.1.5      │    │
│  │  • postgres-1.postgres.default.svc.cluster.local → 10.244.2.3      │    │
│  │  • postgres-2.postgres.default.svc.cluster.local → 10.244.3.7      │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  /etc/resolv.conf в каждом Pod:                                             │
│  nameserver 10.96.0.10                                                      │
│  search default.svc.cluster.local svc.cluster.local cluster.local          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Headless Service — для StatefulSet

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HEADLESS SERVICE                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Обычный Service:                    Headless Service:                      │
│  clusterIP: 10.96.45.123            clusterIP: None                        │
│                                                                              │
│  DNS → один IP (VIP)                 DNS → список IP всех Pod'ов           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  nslookup nginx.default           nslookup postgres.default         │    │
│  │  → 10.96.45.123                   → 10.244.1.5                      │    │
│  │                                   → 10.244.2.3                      │    │
│  │                                   → 10.244.3.7                      │    │
│  │                                                                      │    │
│  │  Клиент обращается к VIP,         Клиент сам выбирает Pod           │    │
│  │  kube-proxy балансирует           или обращается по имени:          │    │
│  │                                   postgres-0.postgres.default       │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  apiVersion: v1                                                             │
│  kind: Service                                                              │
│  metadata:                                                                   │
│    name: postgres                                                           │
│  spec:                                                                       │
│    clusterIP: None          # ← Headless!                                   │
│    selector:                                                                 │
│      app: postgres                                                          │
│    ports:                                                                    │
│    - port: 5432                                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### NodePort и LoadBalancer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL ACCESS                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  NODEPORT (type: NodePort)                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Внешний клиент → любая_нода:30080 → Service → Pod                  │    │
│  │                                                                      │    │
│  │  Node 1 (192.168.1.10)  ─┐                                          │    │
│  │  Node 2 (192.168.1.11)  ─┼─ Все слушают порт 30080                  │    │
│  │  Node 3 (192.168.1.12)  ─┘                                          │    │
│  │                                                                      │    │
│  │  spec:                                                               │    │
│  │    type: NodePort                                                    │    │
│  │    ports:                                                            │    │
│  │    - port: 80                                                        │    │
│  │      targetPort: 8080                                                │    │
│  │      nodePort: 30080      # 30000-32767                             │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  LOADBALANCER (type: LoadBalancer) — только в облаке                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Внешний клиент → Cloud LB (external IP) → NodePort → Service → Pod │    │
│  │                                                                      │    │
│  │                   ┌──────────────────┐                               │    │
│  │  Internet ───────►│ Cloud Load      │                               │    │
│  │                   │ Balancer        │                               │    │
│  │                   │ (AWS ELB/       │                               │    │
│  │                   │  GCP LB/Azure)  │                               │    │
│  │                   └────────┬─────────┘                               │    │
│  │                            │                                         │    │
│  │               ┌────────────┼────────────┐                            │    │
│  │               ▼            ▼            ▼                            │    │
│  │            Node 1       Node 2       Node 3                          │    │
│  │           :30080       :30080       :30080                           │    │
│  │                                                                      │    │
│  │  kubectl get svc                                                     │    │
│  │  NAME    TYPE           EXTERNAL-IP      PORT(S)                     │    │
│  │  nginx   LoadBalancer   52.123.45.67     80:30080/TCP               │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Ingress Controller — HTTP роутинг

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INGRESS ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                              Internet                                        │
│                                  │                                           │
│                                  ▼                                           │
│                   ┌──────────────────────────────┐                          │
│                   │     Load Balancer            │                          │
│                   │   (Cloud или MetalLB)        │                          │
│                   └──────────────┬───────────────┘                          │
│                                  │                                           │
│                                  ▼                                           │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    INGRESS CONTROLLER                                  │  │
│  │              (nginx-ingress / traefik / contour)                      │  │
│  │                                                                        │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │  Ingress Resource:                                                │ │  │
│  │  │                                                                   │ │  │
│  │  │  rules:                                                           │ │  │
│  │  │  - host: api.example.com                                         │ │  │
│  │  │    http:                                                          │ │  │
│  │  │      paths:                                                       │ │  │
│  │  │      - path: /v1    →  api-v1-service:8080                       │ │  │
│  │  │      - path: /v2    →  api-v2-service:8080                       │ │  │
│  │  │                                                                   │ │  │
│  │  │  - host: web.example.com                                         │ │  │
│  │  │    http:                                                          │ │  │
│  │  │      paths:                                                       │ │  │
│  │  │      - path: /      →  frontend-service:80                       │ │  │
│  │  │                                                                   │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                        │  │
│  │  Ingress Controller читает Ingress ресурсы и настраивает              │  │
│  │  свой reverse proxy (nginx.conf / traefik config)                     │  │
│  │                                                                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                         │              │              │                      │
│                         ▼              ▼              ▼                      │
│                   ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│                   │Service A│    │Service B│    │Service C│                 │
│                   └─────────┘    └─────────┘    └─────────┘                 │
│                         │              │              │                      │
│                         ▼              ▼              ▼                      │
│                   ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│                   │  Pods   │    │  Pods   │    │  Pods   │                 │
│                   └─────────┘    └─────────┘    └─────────┘                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Практика: диагностика сети

```bash
# ===== ПРОВЕРКА POD СЕТИ =====

# IP Pod'а
kubectl get pod <name> -o wide

# Зайти в Pod и проверить сеть
kubectl exec -it <pod> -- sh
# Внутри:
ip addr                    # IP адреса
ip route                   # Маршруты
cat /etc/resolv.conf       # DNS
nslookup <service>         # Резолв имени
curl http://<service>      # HTTP запрос

# Дебаг-контейнер с сетевыми утилитами
kubectl run debug --rm -it --image=nicolaka/netshoot -- bash
# Внутри:
ping 10.244.1.5           # Ping Pod
traceroute 10.244.2.3     # Трассировка
dig <service>.default.svc.cluster.local  # DNS lookup
tcpdump -i eth0           # Захват пакетов

# ===== ПРОВЕРКА SERVICE =====

# Endpoints (реальные IP Pod'ов)
kubectl get endpoints <service>

# Детали Service
kubectl describe svc <service>

# Проверить iptables правила (на ноде)
sudo iptables -t nat -L KUBE-SERVICES -n
sudo iptables -t nat -L KUBE-SVC-XXXX -n

# Проверить IPVS (если используется)
sudo ipvsadm -L -n

# ===== ПРОВЕРКА DNS =====

# Тест DNS из Pod'а
kubectl run dnstest --rm -it --image=busybox -- nslookup kubernetes

# Логи CoreDNS
kubectl logs -n kube-system -l k8s-app=kube-dns

# ===== ПРОВЕРКА CNI =====

# Конфигурация CNI
cat /etc/cni/net.d/*.conf

# Логи CNI (зависит от плагина)
kubectl logs -n kube-system -l k8s-app=calico-node
```

### Сетевая политика — пример

```yaml
# Разрешить только frontend → backend на порту 8080
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: database
    ports:
    - protocol: TCP
      port: 5432
  - to:                    # Разрешить DNS
    - namespaceSelector: {}
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
```

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  frontend ──────► backend ──────► database                                  │
│     ✓               │                ✓                                      │
│                     │                                                        │
│  other-pod ──✗──────┘                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Часть 3: Практика с Rancher

## 24. Установка Rancher

### Почему Rancher, а не Minikube?

| Критерий | Minikube | Rancher + K3s |
|----------|----------|---------------|
| Production-ready | Нет | Да |
| Multi-cluster | Нет | Да |
| UI для управления | Базовый | Полноценный |
| RBAC управление | Командная строка | Веб-интерфейс |
| Мониторинг | Нужно ставить | Встроен |
| Ресурсы | Много | K3s очень лёгкий |

### Варианты установки Rancher

**Вариант A: Docker (для обучения) — рекомендуется для старта**
```bash
# Запуск Rancher в Docker
docker run -d --restart=unless-stopped \
  -p 80:80 -p 443:443 \
  --privileged \
  --name rancher \
  rancher/rancher:latest

# Получить начальный пароль
docker logs rancher 2>&1 | grep "Bootstrap Password:"
```

**Вариант B: На существующем K8s кластере (production)**
```bash
# Добавить Helm repo
helm repo add rancher-stable https://releases.rancher.com/server-charts/stable
helm repo update

# Установить cert-manager (требуется)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Установить Rancher
helm install rancher rancher-stable/rancher \
  --namespace cattle-system \
  --create-namespace \
  --set hostname=rancher.example.com \
  --set bootstrapPassword=admin
```

### Первый вход в Rancher

1. Откройте `https://localhost` (или IP сервера)
2. Примите самоподписанный сертификат
3. Введите bootstrap password из логов
4. Установите новый пароль администратора
5. Укажите Server URL (как кластеры будут подключаться)

## 25. Создание кластера K3s через Rancher

### Что такое K3s?

K3s — лёгкий Kubernetes от Rancher:
- Бинарник < 100MB
- Потребляет ~512MB RAM
- Сертифицирован CNCF
- Идеален для Edge, IoT, обучения

### Создание кластера в Rancher UI

```
1. Cluster Management → Create
2. Выбрать "Custom" (свои серверы)
3. Задать имя кластера: "lab-cluster"
4. Kubernetes Version: выбрать последнюю стабильную
5. Нажать Create
```

### Добавление нод

После создания кластера Rancher даст команду регистрации:

```bash
# На сервере который станет Control Plane + Worker
curl -fL https://rancher.example.com/system-agent-install.sh | \
  sudo sh -s - \
  --server https://rancher.example.com \
  --label 'cattle.io/os=linux' \
  --token <TOKEN> \
  --etcd --controlplane --worker
```

**Роли нод:**
- `--etcd` — хранилище состояния
- `--controlplane` — API server, scheduler, controller
- `--worker` — запуск подов

### Минимальные конфигурации

**Для обучения (1 нода):**
```bash
# Все роли на одной машине
--etcd --controlplane --worker
```

**Для production (минимум 3 ноды):**
```
Node 1: --etcd --controlplane
Node 2: --etcd --controlplane
Node 3: --etcd --controlplane
Node 4+: --worker
```

## 26. Практическое упражнение 1: Развёртывание приложения

### Задача
Развернуть веб-приложение с базой данных через Rancher UI.

### Шаг 1: Создание Namespace

```
Rancher UI → Cluster → Projects/Namespaces → Create Namespace
Name: practice-app
```

Или через kubectl:
```bash
kubectl create namespace practice-app
```

### Шаг 2: Развёртывание PostgreSQL

**Через Rancher UI:**
```
Workload → Deployments → Create

Name: postgres
Namespace: practice-app
Container Image: postgres:15-alpine

Environment Variables:
  POSTGRES_DB: appdb
  POSTGRES_USER: appuser
  POSTGRES_PASSWORD: secretpass

Ports:
  Container Port: 5432
  Protocol: TCP
```

**Или YAML (сохранить как postgres.yaml):**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: practice-app
type: Opaque
stringData:
  POSTGRES_DB: appdb
  POSTGRES_USER: appuser
  POSTGRES_PASSWORD: secretpass
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: practice-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
        envFrom:
        - secretRef:
            name: postgres-secret
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: practice-app
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
  type: ClusterIP
```

```bash
kubectl apply -f postgres.yaml
```

### Шаг 3: Развёртывание веб-приложения

```yaml
# app.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webapp
  namespace: practice-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: webapp
  template:
    metadata:
      labels:
        app: webapp
    spec:
      containers:
      - name: webapp
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "200m"
        livenessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: webapp
  namespace: practice-app
spec:
  selector:
    app: webapp
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: webapp-ingress
  namespace: practice-app
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: webapp.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: webapp
            port:
              number: 80
```

```bash
kubectl apply -f app.yaml
```

### Шаг 4: Проверка в Rancher UI

```
Cluster → Workload → Deployments
  ✓ postgres    1/1 Running
  ✓ webapp      3/3 Running

Cluster → Service Discovery → Services
  ✓ postgres    ClusterIP
  ✓ webapp      ClusterIP

Cluster → Service Discovery → Ingresses
  ✓ webapp-ingress   webapp.local
```

### Шаг 5: Тестирование

```bash
# Проверить поды
kubectl get pods -n practice-app

# Проверить логи
kubectl logs -n practice-app -l app=webapp

# Exec в под
kubectl exec -it -n practice-app deploy/webapp -- sh

# Проверить связность с postgres
kubectl exec -it -n practice-app deploy/webapp -- \
  sh -c "nc -zv postgres 5432"
```

## 27. Практическое упражнение 2: Масштабирование и обновление

### Задача
Научиться масштабировать и обновлять приложения без простоя.

### Масштабирование через UI

```
Workload → Deployments → webapp → ⋮ → Edit Config
  Replicas: 5
  Save
```

### Масштабирование через kubectl

```bash
# Увеличить до 5 реплик
kubectl scale deployment webapp -n practice-app --replicas=5

# Проверить
kubectl get pods -n practice-app -l app=webapp

# Автоскейлинг (HPA)
kubectl autoscale deployment webapp -n practice-app \
  --min=3 --max=10 --cpu-percent=70
```

### Rolling Update

```bash
# Обновить образ
kubectl set image deployment/webapp webapp=nginx:1.25-alpine \
  -n practice-app

# Следить за обновлением
kubectl rollout status deployment/webapp -n practice-app

# История обновлений
kubectl rollout history deployment/webapp -n practice-app

# Откатиться на предыдущую версию
kubectl rollout undo deployment/webapp -n practice-app
```

### Стратегии обновления

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Макс. дополнительных подов
      maxUnavailable: 0  # Не допускать недоступность
```

## 28. Практическое упражнение 3: Мониторинг в Rancher

### Включение мониторинга

```
Cluster → Apps → Charts → Monitoring → Install

Prometheus: ✓
Grafana: ✓
Alertmanager: ✓
```

### Просмотр метрик

```
Cluster → Monitoring → Grafana

Dashboards:
  - Kubernetes / Compute Resources / Cluster
  - Kubernetes / Compute Resources / Namespace (Pods)
  - Kubernetes / Networking / Cluster
```

### Создание алерта

```yaml
# alert-rule.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: webapp-alerts
  namespace: cattle-monitoring-system
  labels:
    app: rancher-monitoring
spec:
  groups:
  - name: webapp
    rules:
    - alert: WebappDown
      expr: kube_deployment_status_replicas_available{deployment="webapp",namespace="practice-app"} < 1
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "Webapp is down"
        description: "No available replicas for webapp"
    - alert: WebappHighMemory
      expr: |
        sum(container_memory_usage_bytes{pod=~"webapp-.*",namespace="practice-app"})
        / sum(kube_pod_container_resource_limits{pod=~"webapp-.*",namespace="practice-app",resource="memory"})
        > 0.8
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Webapp memory usage > 80%"
```

## 29. Практическое упражнение 4: Хранилище данных

### Задача
Настроить persistent storage для PostgreSQL.

### Шаг 1: Проверить StorageClass

```bash
kubectl get storageclass

# K3s по умолчанию использует local-path
NAME                   PROVISIONER             RECLAIMPOLICY
local-path (default)   rancher.io/local-path   Delete
```

### Шаг 2: Создать PVC

```yaml
# postgres-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: practice-app
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 5Gi
```

### Шаг 3: Обновить Deployment PostgreSQL

```yaml
# postgres-with-storage.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: practice-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
        envFrom:
        - secretRef:
            name: postgres-secret
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-data
```

### Шаг 4: Проверка

```bash
# Проверить PVC
kubectl get pvc -n practice-app

# Проверить что данные сохраняются
kubectl exec -it -n practice-app deploy/postgres -- psql -U appuser -d appdb -c "CREATE TABLE test(id int);"

# Удалить под (он пересоздастся)
kubectl delete pod -n practice-app -l app=postgres

# Проверить что таблица осталась
kubectl exec -it -n practice-app deploy/postgres -- psql -U appuser -d appdb -c "\dt"
```

## 30. Практическое упражнение 5: RBAC и пользователи

### Задача
Создать пользователя с ограниченным доступом.

### Шаг 1: Создать ServiceAccount

```yaml
# developer-sa.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: developer
  namespace: practice-app
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer-role
  namespace: practice-app
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log", "services", "configmaps"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/exec"]
  verbs: ["create"]  # Разрешить exec в поды
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developer-binding
  namespace: practice-app
subjects:
- kind: ServiceAccount
  name: developer
  namespace: practice-app
roleRef:
  kind: Role
  name: developer-role
  apiGroup: rbac.authorization.k8s.io
```

```bash
kubectl apply -f developer-sa.yaml
```

### Шаг 2: Получить токен

```bash
# Создать токен для ServiceAccount
kubectl create token developer -n practice-app --duration=24h
```

### Шаг 3: Создать kubeconfig

```bash
# Получить CA сертификат
kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d > ca.crt

# Создать kubeconfig
cat > developer-kubeconfig.yaml << EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: $(cat ca.crt | base64 -w0)
    server: https://<CLUSTER-IP>:6443
  name: lab-cluster
contexts:
- context:
    cluster: lab-cluster
    namespace: practice-app
    user: developer
  name: developer-context
current-context: developer-context
users:
- name: developer
  user:
    token: <TOKEN-FROM-STEP-2>
EOF
```

### Шаг 4: Тестирование ограничений

```bash
# Использовать kubeconfig разработчика
export KUBECONFIG=developer-kubeconfig.yaml

# Это работает
kubectl get pods
kubectl logs deploy/webapp
kubectl exec -it deploy/webapp -- sh

# Это НЕ работает (нет прав)
kubectl delete pod webapp-xxx
# Error: pods "webapp-xxx" is forbidden

kubectl get pods -n kube-system
# Error: pods is forbidden in namespace "kube-system"
```

### Управление пользователями в Rancher UI

```
Rancher → Users & Authentication → Users → Create

Username: developer
Password: ***
Global Permissions: User (базовые права)

Затем:
Cluster → Members → Add
  Member: developer
  Role: Read-Only или Custom
```

## 31. Практическое упражнение 6: CI/CD интеграция

### Задача
Настроить автоматический деплой из Git.

### Rancher Fleet (GitOps)

```
Cluster → Continuous Delivery → Git Repos → Add Repository

Name: practice-app-repo
Repository URL: https://github.com/user/k8s-manifests.git
Branch: main
Paths: /practice-app
```

**Структура репозитория:**
```
k8s-manifests/
└── practice-app/
    ├── fleet.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

**fleet.yaml:**
```yaml
defaultNamespace: practice-app
helm:
  releaseName: webapp
```

### Webhook для автоматического деплоя

```bash
# При push в репозиторий Fleet автоматически применит изменения
git add .
git commit -m "Update webapp to v2"
git push

# Rancher Fleet обнаружит изменения и применит их
```

## 32. Чек-лист практических навыков

После выполнения упражнений вы должны уметь:

### Базовые операции
- [ ] Установить Rancher в Docker
- [ ] Создать K3s кластер через Rancher
- [ ] Добавить ноды в кластер
- [ ] Работать с kubectl и Rancher UI параллельно

### Workloads
- [ ] Создавать Deployments (UI и YAML)
- [ ] Настраивать Services (ClusterIP, NodePort)
- [ ] Создавать Ingress для внешнего доступа
- [ ] Масштабировать приложения
- [ ] Выполнять rolling updates
- [ ] Откатывать неудачные обновления

### Конфигурация
- [ ] Создавать ConfigMaps и Secrets
- [ ] Использовать переменные окружения из Secrets
- [ ] Настраивать resource requests/limits
- [ ] Настраивать liveness/readiness probes

### Storage
- [ ] Создавать PVC
- [ ] Подключать volumes к подам
- [ ] Проверять persistence данных

### Безопасность
- [ ] Создавать ServiceAccount
- [ ] Настраивать Role и RoleBinding
- [ ] Ограничивать доступ по namespace
- [ ] Создавать пользователей в Rancher

### Мониторинг
- [ ] Включать Monitoring stack в Rancher
- [ ] Просматривать метрики в Grafana
- [ ] Создавать alert rules
- [ ] Просматривать логи подов

### Troubleshooting
- [ ] Диагностировать failing pods
- [ ] Читать события (`kubectl get events`)
- [ ] Проверять сетевую связность между подами
- [ ] Использовать `kubectl describe` для отладки

## 33. Полезные команды для ежедневной работы

```bash
# === Статус кластера ===
kubectl get nodes -o wide
kubectl top nodes
kubectl get all -A | head -50

# === Быстрая диагностика ===
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
kubectl describe pod <pod> -n <namespace> | tail -30
kubectl logs <pod> -n <namespace> --tail=100 -f

# === Работа с ресурсами ===
kubectl get pods -n <namespace> -o wide
kubectl get svc,ing -n <namespace>
kubectl get pvc -n <namespace>

# === Отладка сети ===
kubectl run debug --rm -it --image=nicolaka/netshoot -- bash
# Внутри: curl, nslookup, ping, traceroute, tcpdump

# === Управление контекстами ===
kubectl config get-contexts
kubectl config use-context <context>
kubectl config set-context --current --namespace=<namespace>

# === Rancher CLI (опционально) ===
# Установка: https://github.com/rancher/cli/releases
rancher login https://rancher.example.com --token <token>
rancher kubectl get pods
```

## 34. Архитектура тестового стенда

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Rancher Server                                  │
│                           (Docker container)                                 │
│                              Port 443                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Manages
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            K3s Cluster "lab"                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        Node 1 (All-in-one)                             │ │
│  │  Roles: etcd + controlplane + worker                                   │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │ │
│  │  │  API Server │ │  Scheduler  │ │ Controller  │ │    etcd     │      │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                      │ │
│  │  │   kubelet   │ │ kube-proxy  │ │  Traefik    │                      │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  Namespaces:                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │   kube-system    │  │  cattle-system   │  │   practice-app   │          │
│  │ CoreDNS, Metrics │  │ Rancher Agent    │  │ webapp, postgres │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 35. Следующие шаги после практики

1. **Добавить второй worker node** — понять распределение подов
2. **Настроить Longhorn** — distributed storage от Rancher
3. **Попробовать Helm charts** — установить готовые приложения
4. **Настроить внешний LoadBalancer** — MetalLB для bare-metal
5. **Изучить Service Mesh** — Istio или Linkerd через Rancher
6. **Настроить backup** — Velero для бэкапа кластера
