# Incident Investigator

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Incident Investigator принимает CI-сбой или runtime-alert, сам собирает доступные
доказательства, проверяет несколько гипотез и предлагает только проверяемое безопасное
действие. Изменение выполняется после подтверждения человека, а затем агент отдельно
проверяет восстановление системы.

Это не ещё один чат с логами. Ядро хранит durable state расследования, ограничивает инструменты
политиками и бюджетами, переживает перезапуск, умеет запросить недостающие данные у оператора
и оставляет воспроизводимый audit trail.

## Попробовать за пять минут

Нужен только запущенный Docker Desktop. Дополнительные репозитории, токены и OpenAI API key
для первого знакомства не требуются.

Windows:

```powershell
.\demo.ps1
```

Linux/macOS:

```bash
sh demo.sh
```

Затем откройте [http://127.0.0.1:8501](http://127.0.0.1:8501).

Стенд внутри этого репозитория сам:

1. запускает неисправное приложение;
2. генерирует трафик и метрики;
3. поднимает Prometheus и Alertmanager;
4. отправляет настоящий webhook;
5. собирает метрики и структурированные логи;
6. останавливается перед rollback и ждёт вашего решения;
7. после approval применяет узкое исправление и проверяет health и исчезновение alert.

Локальный smoke test использует честно обозначенный детерминированный fixture-engine, поэтому
проверяет всю инфраструктуру без оплаты LLM. Для проверки реального модельного рассуждения
добавьте OpenAI key и включите `INVESTIGATOR_MODE=connected` по инструкции ниже.

Остановить стенд:

```powershell
.\demo.ps1 down
```

## Что уже работает

- GitHub Actions `workflow_run`, GitLab Pipeline Hook и Prometheus Alertmanager.
- Единая модель события для CI- и runtime-инцидентов.
- Цикл evidence → hypotheses → verification → Reflexion → action → recovery.
- SQLite queue и LangGraph checkpoints, переживающие перезапуск процесса.
- Таймауты, retry, iteration/tool budgets и безопасная эскалация.
- Bounded replanning: ошибка action tool или recovery check становится новым evidence;
  повтор уже провалившегося действия блокируется.
- Human-in-the-Loop для runtime-действий и публикации draft PR/MR.
- Запрос недостающего контекста через dashboard: текст или TXT/LOG/JSON/YAML.
- Маскирование типовых секретов, provenance и SHA-256 операторских данных.
- Изолированный remediation pipeline: patch → Docker tests/lint → critic → approval.
- Draft GitHub PR или GitLab MR без автоматического merge.
- Telegram-уведомления и LangSmith tracing.
- Русский и английский интерфейс.

## Встроенный CI-сценарий

В `demo/ci-python-app` находится намеренно сломанное приложение. Оно позволяет проверить
поиск причины, patch, pytest, Ruff и critic полностью локально:

```powershell
uv sync --extra dev --extra ui
uv run python scripts/run_remediation_demo.py
```

Во внешний GitHub или GitLab этот сценарий ничего не отправляет.

## Подключение к своему проекту

Создавать отдельный «репозиторий инцидентов» не нужно. Один раз разверните Investigator на
сервере, затем подключайте к нему существующие проекты:

- GitHub/GitLab отправляют webhook о провалившемся pipeline;
- токен с минимальными правами позволяет читать job log и diff;
- Prometheus Alertmanager отправляет firing alerts;
- evidence adapters читают метрики, логи и deployment context;
- action adapter описывает только разрешённые для вашей среды операции.

Начинайте в read-only shadow mode. После накопления успешных расследований включайте draft
PR/MR, а runtime-actions оставляйте за allowlist и approval. Практический план подключения,
права и ограничения текущей версии описаны в
[Production integration guide](docs/production-integration.md).

## Режимы

| Режим | Назначение | LLM |
|---|---|---|
| `demo` | Проверка webhook, queue, checkpoints и UI | Нет |
| `fixture` | Полный встроенный runtime smoke test | Нет |
| `connected` | Настоящее расследование по собранным evidence | OpenAI |

## Архитектура в одном абзаце

Event adapters проверяют подпись и нормализуют внешние payload в `IncidentEvent`. Durable
LangGraph управляет расследованием. Read-only evidence providers возвращают факты с provenance.
LLM формирует структурированные гипотезы, но policy engine, sandbox, approval и recovery
verification находятся вне модели. GitHub, GitLab, Prometheus, Telegram и конкретная LLM
остаются заменяемыми адаптерами.

```mermaid
%%{init: {"theme":"base","flowchart":{"curve":"basis","nodeSpacing":42,"rankSpacing":58},"themeVariables":{"background":"#0B1220","fontFamily":"Segoe UI, Arial, sans-serif","fontSize":"16px","textColor":"#F8FAFC","lineColor":"#CBD5E1","edgeLabelBackground":"#111827","clusterBkg":"#111827","clusterBorder":"#475569","titleColor":"#F8FAFC"}}}%%
flowchart TB
    SOURCES["INCIDENT SOURCES<br/>GitHub Actions · GitLab CI · Prometheus Alertmanager"]
    GATEWAY["EVENT GATEWAY<br/>Проверка webhook · нормализация в IncidentEvent"]
    STATE["DURABLE STATE<br/>Очередь · deduplication · LangGraph checkpoint"]

    SOURCES --> GATEWAY --> STATE

    subgraph INVESTIGATION["АГЕНТНОЕ ЯДРО"]
        direction TB
        EVIDENCE["EVIDENCE ORCHESTRATOR<br/>CI logs · diff · metrics · runtime logs"]
        HYPOTHESIS["HYPOTHESIS AGENT<br/>Гипотезы · confidence · evidence links"]
        REFLEXION{"REFLEXION<br/>Причина доказана?"}
        INPUT["HUMAN INPUT<br/>Запросить недостающий текст или файл"]
        PLANNER["ACTION PLANNER<br/>Предложить минимальное обратимое действие"]
        POLICY{"POLICY GATE<br/>Allowlist · risk · approval"}

        EVIDENCE --> HYPOTHESIS --> REFLEXION
        REFLEXION -- "Больше фактов" --> EVIDENCE
        REFLEXION -- "Нужен контекст" --> INPUT
        INPUT -- "Новое evidence" --> HYPOTHESIS
        REFLEXION -- "Причина подтверждена" --> PLANNER --> POLICY
    end

    STATE --> EVIDENCE

    subgraph REMEDIATION["REMEDIATION PIPELINES"]
        direction LR

        subgraph RUNTIME["RUNTIME"]
            direction TB
            RUNTIME_APPROVAL["HUMAN APPROVAL<br/>Риск · evidence · rollback plan"]
            EXECUTOR["SAFE EXECUTOR<br/>Timeout · retry · idempotency"]
            RECOVERY{"RECOVERY CHECK<br/>Сервис healthy<br/>и alert исчез?"}
            RUNTIME_APPROVAL --> EXECUTOR --> RECOVERY
        end

        subgraph CODE["CI / CODE"]
            direction TB
            PATCH["REMEDIATION AGENT<br/>Изолированный patch"]
            SANDBOX["DOCKER SANDBOX<br/>Tests · linter · network off"]
            CRITIC{"CRITIC AGENT<br/>Fix безопасен<br/>и доказан?"}
            CODE_APPROVAL["HUMAN APPROVAL<br/>Evidence · diff · tests"]
            PR["DRAFT PR / MR<br/>Без автоматического merge"]
            PATCH --> SANDBOX --> CRITIC
            CRITIC -- "Repair" --> PATCH
            CRITIC -- "Проверка пройдена" --> CODE_APPROVAL --> PR
        end
    end

    POLICY -- "Runtime action" --> RUNTIME_APPROVAL
    POLICY -- "Исправление кода" --> PATCH

    REPLAN["↺ BOUNDED REPLAN<br/>Ошибка становится новым evidence<br/>и возвращает граф к Hypothesis Agent"]
    REPORT["INCIDENT REPORT<br/>Причина · доказательства · confidence · результат"]
    OUTPUT["DELIVERY<br/>Dashboard · Telegram · LangSmith trace"]

    EXECUTOR -- "Tool failure" --> REPLAN
    RECOVERY -- "Не восстановилось" --> REPLAN
    PATCH -- "Patch заблокирован" --> REPLAN
    POLICY -- "Действие запрещено" --> REPORT
    REFLEXION -- "Безопасного действия нет" --> REPORT
    RECOVERY -- "Восстановлено" --> REPORT
    PR --> REPORT
    REPORT --> OUTPUT

    classDef source fill:#1E293B,stroke:#94A3B8,color:#F8FAFC,stroke-width:2px,font-weight:600,font-family:Arial;
    classDef infrastructure fill:#164E63,stroke:#67E8F9,color:#F0FDFA,stroke-width:3px,font-weight:600,font-family:Arial;
    classDef agent fill:#7F1D1D,stroke:#FDA4AF,color:#FFF7F7,stroke-width:3px,font-weight:700,font-family:Arial;
    classDef human fill:#78350F,stroke:#FBBF24,color:#FFFBEB,stroke-width:3px,font-weight:700,font-family:Arial;
    classDef failure fill:#581C87,stroke:#D8B4FE,color:#FAF5FF,stroke-width:3px,font-weight:700,font-family:Arial;
    classDef result fill:#14532D,stroke:#86EFAC,color:#F0FDF4,stroke-width:3px,font-weight:700,font-family:Arial;

    class SOURCES source;
    class GATEWAY,STATE,EVIDENCE,POLICY,EXECUTOR,RECOVERY,SANDBOX infrastructure;
    class HYPOTHESIS,REFLEXION,PLANNER,PATCH,CRITIC agent;
    class INPUT,RUNTIME_APPROVAL,CODE_APPROVAL human;
    class REPLAN failure;
    class PR,REPORT,OUTPUT result;

    style INVESTIGATION fill:#111827,stroke:#F87171,color:#F8FAFC,stroke-width:3px
    style REMEDIATION fill:#0B1220,stroke:#64748B,color:#F8FAFC,stroke-width:3px
    style RUNTIME fill:#0F172A,stroke:#22D3EE,color:#F8FAFC,stroke-width:2px
    style CODE fill:#0F172A,stroke:#F59E0B,color:#F8FAFC,stroke-width:2px
    linkStyle default stroke:#CBD5E1,stroke-width:2px,color:#F8FAFC
```

Красным обозначены LLM-роли, голубым — детерминированные компоненты безопасности и
интеграций, золотым — точки Human-in-the-Loop, зелёным — проверенные результаты. Фиолетовый
узел показывает единый безопасный fallback: ошибка становится новым evidence и запускает
ограниченное перепланирование.

Подробнее: [архитектура](docs/architecture.md), [модель угроз](docs/threat-model.md),
[observability и evals](docs/observability.md), [установка](docs/deployment.md),
[сценарий защиты](docs/demo-runbook.md),
[соответствие исходному ТЗ](docs/requirements-compliance.md),
[редактируемая агентная диаграмма](docs/agent-architecture.excalidraw),
[аудит по книге об AI-агентах](docs/book-review.md).

## Что проект не обещает

Investigator не может без настройки понимать любую инфраструктуру и не должен получать
неограниченный shell или административные credentials. Универсален lifecycle расследования;
форматы логов, runbooks и разрешённые действия задаются адаптерами конкретной среды.

Текущая SQLite-реализация рассчитана на ноутбук или один server process. Для нескольких
replicas очередь и checkpoints нужно перенести в PostgreSQL.

## Разработка

```powershell
uv sync --extra dev --extra ui
uv run ruff check src tests scripts demo
uv run pytest
```

Проект использует Python 3.12+, FastAPI, LangGraph, Streamlit, OpenAI Structured Outputs,
Docker sandbox и LangSmith.

## Лицензия

Проект распространяется по [Apache License 2.0](LICENSE).
