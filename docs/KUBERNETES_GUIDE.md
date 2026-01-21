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

### Шаг 1: Установка minikube (локальный кластер)

```bash
# Установка minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Запуск кластера
minikube start

# Проверка
kubectl cluster-info
kubectl get nodes
```

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

# Получаем URL для доступа
minikube service hello-service --url
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
