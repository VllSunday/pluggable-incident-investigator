# Pluggable Multi-Agent Incident Investigator

Capstone-проект: расширяемая система расследования CI- и runtime-инцидентов.
Один orchestration core принимает унифицированное событие, собирает доказательства,
проверяет гипотезы, останавливается перед опасным действием и проверяет восстановление.

## Текущий MVP

- Источники событий: GitHub Actions `workflow_run`, GitLab `Pipeline Hook` и Prometheus Alertmanager.
- Среды исполнения: тестовый GitHub-репозиторий и локальный Docker Compose стенд.
- Критические действия: создание issue/PR и перезапуск demo-контейнера — только после approval.
- Любая интеграция подключается через контракт адаптера; ядро не импортирует GitHub,
  Prometheus, Docker или Telegram SDK.
- SQLite durable queue и LangGraph checkpoints переживают перезапуск одного server process.
- Connected mode использует OpenAI Structured Outputs; demo mode не делает вид, что умеет
  диагностировать без evidence providers.
- Для CI-инцидентов доступен opt-in remediation pipeline: проверенный unified diff →
  изолированная workspace → allowlisted Docker checks → critic → HitL → один commit и
  draft GitHub PR/GitLab MR.

## Структура

```text
src/incident_investigator/
  domain/       # стабильная модель предметной области
  core/         # policy, budgets, tool runtime, orchestration graph
  adapters/     # GitHub и Alertmanager на границе системы
  api/          # webhook/API transport
docs/           # архитектурные решения и roadmap
tests/          # contract, policy и failure-path tests
```

## Локальная разработка

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
```

HTTP-слой создаётся через `incident_investigator.api.create_app`. Composition root с
durable SQLite queue/checkpoints запускается командой `uv run incident-investigator`.

В отдельном терминале запустите двуязычный operator dashboard:

```bash
uv sync --extra dev --extra ui
uv run streamlit run src/incident_investigator/ui/app.py
```

Откройте `http://127.0.0.1:8501`. Dashboard использует
`INVESTIGATOR_API_URL` (по умолчанию `http://127.0.0.1:8000`) и тот же
`INVESTIGATOR_ADMIN_API_TOKEN`, что и API.
Режим `demo` принимает события и проверяет полный transport/persistence flow, но намеренно
эскалирует расследование до подключения реальных evidence providers.

Инструкции локальной и серверной установки: [`docs/deployment.md`](docs/deployment.md).

## Safe remediation

Remediation намеренно выключен по умолчанию. Для включения нужны connected mode,
GitHub/GitLab API token, локальный Docker daemon и заранее подготовленный sandbox image.
Команды проверок задаются оператором в `INVESTIGATOR_REMEDIATION_CHECK_PROFILES`; модель
выбирает только имя существующего профиля и не получает произвольный shell.

После успешных проверок dashboard показывает изменённые пути, exit codes, hash patch и
вердикт critic. До approval ветка и PR/MR не существуют. Если человек отклоняет изменение,
изолированная workspace удаляется.

## Воспроизводимая demo-защита

Docker Desktop должен быть запущен. Одна команда собирает отдельный sandbox image и
выполняет контролируемый сценарий с настоящими Docker-проверками:

```powershell
uv sync --extra dev --extra ui
uv run python scripts/run_remediation_demo.py
```

Demo сначала доказывает, что исходный retry service действительно падает, затем применяет
patch, выполняет `pytest` и `ruff` без сети, останавливает LangGraph на approval и после
симулированного решения формирует draft-PR payload. Во внешний GitHub ничего не отправляется.

Fixture находится в [`demo/ci-python-app`](demo/ci-python-app), а real-Docker test — в
[`tests/integration/test_real_docker_remediation.py`](tests/integration/test_real_docker_remediation.py).

Для настоящего GitHub Actions run сначала передайте read/write token в process environment,
не печатая его в terminal history:

```powershell
$env:INVESTIGATOR_GITHUB_API_TOKEN = gh auth token
uv run python scripts/run_connected_github_demo.py `
  --repository VllSunday/incident-investigator-demo-ci `
  --run-id <RUN_ID> `
  --head-sha <HEAD_SHA> `
  --evidence-only
```

Для реального GitLab pipeline используется симметричная команда; токен читается из
игнорируемого `.env`:

```powershell
uv run python scripts/run_connected_gitlab_demo.py `
  --repository AllSunday/incident-investigator-demo-ci `
  --pipeline-id <PIPELINE_ID> `
  --sha <COMMIT_SHA> `
  --evidence-only
```

Без `--approve` connected-run не создаёт ветку или merge request. Настоящий draft MR
публикуется только после успешных sandbox checks и явного `--approve`.

После заполнения `INVESTIGATOR_OPENAI_API_KEY` уберите `--evidence-only`. Без `--approve`
система завершит investigation и sandbox validation, но не создаст ветку. Настоящий draft PR
создаётся только при явном `--approve`.

## Что проект намеренно не обещает

Система не является универсальным SRE, который без настройки понимает любую инфраструктуру.
Универсальны модель события и цикл расследования. Форматы данных, доступные инструменты,
credentials, runbooks и разрешённые действия задаются адаптерами и конфигурацией окружения.
