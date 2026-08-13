# Установка и эксплуатация

## Вариант 1 — локальная разработка

Требования: Python 3.12+ и `uv`.

```powershell
Copy-Item .env.example .env
uv sync --extra dev --extra ui
uv run incident-investigator
```

API доступен на `http://localhost:8000`, OpenAPI — на `/docs`, health check — на `/health`.
Все `/api/*` endpoints требуют `Authorization: Bearer <INVESTIGATOR_ADMIN_API_TOKEN>`.

Режим `demo` проверяет ingestion, очередь, persistence и orchestration. Он намеренно не делает
LLM-диагностику до настройки реальных evidence providers.

### Включение safe remediation

Remediation запускается только как явная opt-in возможность. Sandbox image должен уже
содержать зависимости проверяемого проекта: network внутри проверки отключён.

```dotenv
INVESTIGATOR_MODE=connected
INVESTIGATOR_REMEDIATION_ENABLED=true
INVESTIGATOR_REMEDIATION_SANDBOX_IMAGE=your-org/project-ci:locked-digest
INVESTIGATOR_REMEDIATION_CHECK_PROFILES={"python":[["python","-m","pytest","-q"],["python","-m","ruff","check","."]]}
```

Backend, запущенный непосредственно на машине, использует локальный Docker CLI. Не
монтируйте `/var/run/docker.sock` в публичный API-контейнер: Docker socket эквивалентен
административному доступу к host. Для server deployment безопаснее вынести sandbox runner
на отдельный worker/VM и оставить webhook/API process без доступа к Docker daemon.

GitHub fine-grained token должен иметь Contents read/write и Pull requests read/write только
для подключённого repository. GitLab project token — `read_repository` и `api` в пределах
одного проекта. Webhook tokens остаются отдельными.

Для локальной проверки sandbox boundary без SCM credentials выполните:

```powershell
uv run python scripts/run_remediation_demo.py
```

Обычный `uv run pytest` исключает real-Docker тест для скорости и воспроизводимости unit
suite. Явный запуск возможен через `uv run pytest -o "addopts=-q" -m docker`.

## Вариант 2 — Docker на ноутбуке

```powershell
Copy-Item .env.example .env
docker compose up --build
```

SQLite incidents/checkpoints находятся в named volume `investigator-data` и переживают
пересоздание контейнера.

### Полный runtime-стенд

Для воспроизводимого Alertmanager-сценария используйте дополнительный compose override:

```powershell
docker compose -f compose.yaml -f compose.runtime.yaml up -d --build
```

Он добавляет synthetic runtime app, Prometheus с alert rule и Alertmanager. Override
переводит investigator в connected mode, подключает Prometheus по внутренней Docker-сети и
задаёт четыре server-owned PromQL-шаблона: доступность target, request rate, error rate и
error ratio. Значение `runtime-demo-token` в fixture публичное и предназначено только для
локального стенда; в реальном контуре используйте отдельный случайный secret.

Проверить состояние можно в dashboard (`:8501`), Prometheus (`:9090`) и Alertmanager
(`:9093`). Для удаления только тестового состояния и volume выполните:

```powershell
docker compose -f compose.yaml -f compose.runtime.yaml down -v
```

## Вариант 3 — один Linux-сервер

1. Установить Docker Engine и Compose plugin.
2. Клонировать репозиторий.
3. Создать `.env` из `.env.example` и сгенерировать уникальные secrets.
4. Ограничить входящий порт firewall или поставить TLS reverse proxy.
5. Запустить:

```bash
docker compose -f compose.yaml -f compose.production.yaml up -d --build
```

Production override включает restart policy, read-only root filesystem и
`no-new-privileges`. Каталог `/app/data` остаётся writable через named volume.

## Подключение GitHub

В настройках repository webhook:

- URL: `https://<host>/webhooks/github`
- Content type: `application/json`
- Secret: значение `INVESTIGATOR_GITHUB_WEBHOOK_SECRET`
- Event: Workflow runs

Для evidence/remediation API используется отдельный fine-grained token или GitHub App.
Webhook secret не даёт доступа к репозиторию.

## Подключение GitLab

В Settings → Webhooks проекта:

- URL: `https://<host>/webhooks/gitlab`
- Secret token: значение `INVESTIGATOR_GITLAB_WEBHOOK_TOKEN`
- Trigger: Pipeline events

GitLab.com, Dedicated и Self-Managed используют один adapter; `base_url` API будет
настраиваться отдельно для self-hosted instances.

## Подключение Alertmanager

```yaml
receivers:
  - name: incident-investigator
    webhook_configs:
      - url: http://investigator:8000/webhooks/alertmanager
        http_config:
          authorization:
            credentials: <shared-token>
```

Adapter принимает стандартный `Authorization: Bearer <token>` от Alertmanager, а также
`X-Incident-Token` для локальных тестов.

PromQL не принимается из alert payload или ответа LLM. Оператор задаёт allowlisted templates
в `INVESTIGATOR_PROMETHEUS_QUERY_TEMPLATES`; adapter подставляет только нормализованное имя
service. Это сохраняет read-only boundary и предсказуемый бюджет запросов.

## Масштабирование

SQLite подходит для capstone, локального использования и одного server process. Перед
горизонтальным масштабированием несколько replicas очередь и checkpoints переносятся в
PostgreSQL; API и adapter contracts при этом не меняются.
