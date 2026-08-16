# Архитектура решения

## 1. Архитектурная цель

Доказать, что один orchestration core обрабатывает два разных класса событий:

1. CI failure из GitHub Actions или GitLab CI.
2. Runtime alert из Prometheus Alertmanager.

Расширяемость доказывается реализацией общего контракта, а не утверждением «работает везде».

## 2. Компоненты

```text
Webhook/API
    |
    v
Event Adapter -----> IncidentEvent
                         |
                         v
             Investigation Orchestrator
             triage -> evidence -> hypotheses
                 -> verification -> reflection -> action proposal
                    |                         |
                    | runtime action          | code remediation
                    v                         v
                 approval             workspace -> patch policy
                    |                 -> sandbox -> critic -> approval
                    v                         |
             execute -> recovery              v
                                        draft PR / MR
                         |
           +-------------+-------------+
           |                           |
    Evidence providers           Action executors
    (read-only tools)          (policy protected tools)
```

Ядро зависит только от доменных моделей и портов. Интеграции зависят от ядра, но не наоборот.

Webhook request не запускает LLM синхронно. Он сохраняет дедуплицированное событие в SQLite
queue и сразу отвечает `202`; worker продолжает durable LangGraph thread в фоне.

## 3. Production-ready означает

- Pydantic validation на каждой внешней границе.
- Подпись/токен webhook и защита от повторной доставки.
- Durable checkpoint и стабильный incident/thread ID.
- Таймаут, retry и классификация ошибок каждого tool call.
- Tool-call, time и iteration budgets.
- Policy enforcement вне LLM.
- Least privilege: read-only инструменты отделены от action tools.
- HitL перед side effect; side effect идемпотентен.
- Audit trail для входов, решений, approvals и результатов действий.
- Evidence provenance: вывод без ссылки на доказательство не считается подтверждённым.
- Проверка результата после действия и rollback/escalation при неуспехе.

## 4. Стабильные контракты

### EventAdapter

Преобразует внешний payload в один или несколько `IncidentEvent`. Проверка подписи относится
к адаптеру транспорта и выполняется до нормализации.

### EvidenceProvider

Объявляет capabilities и возвращает `EvidenceItem` с source URI, временем получения и
неизменённым raw reference. Провайдер не делает выводов.

### InvestigationEngine

Генерирует гипотезы и оценивает их только через структурированный вывод. Провайдер LLM
сменный; для тестов используется детерминированная реализация.

### ActionExecutor

Принимает только уже одобренный `ActionProposal`, поддерживает idempotency key и возвращает
проверяемый `ActionResult`.

### RemediationPipeline

Отдельный двухфазный action contract. `prepare` не создаёт внешних веток: материализует
зафиксированный revision, применяет patch, запускает серверный check profile и critic.
Durable report хранит только пути, тип операций и hashes — не полное содержимое source files.
`publish` повторно сверяет hashes и только после HitL отправляет один commit через SCM API.

### Operator evidence continuation

Если Reflexion определяет конкретный пробел в доказательствах, ядро не завершает инцидент
общей эскалацией. Оно создаёт структурированный `InformationRequest` с вопросом, причиной,
допустимыми форматами и предупреждением о секретах, затем переводит durable thread в
`awaiting_input`.

Dashboard принимает один текстовый фрагмент или файл TXT/LOG/JSON/YAML. Вход ограничен по
размеру, тип файла и UTF-8, типовые секреты маскируются, а raw SHA-256 и provenance
сохраняются в audit trail. После отправки тот же LangGraph checkpoint возобновляется с новым
`operator_evidence`; история гипотез, budgets и correlation ID не теряются. Оператор также
может отказаться от передачи данных — тогда thread штатно завершается ручной эскалацией.

## 5. Security boundary

LLM никогда не получает shell без ограничений. Она выбирает только зарегистрированный tool
и валидированные аргументы. `PolicyEngine` может запретить действие независимо от ответа LLM.

Начальная политика:

- read-only: автоматически;
- low risk: автоматически только в demo;
- high/critical: human approval;
- destructive/unknown: запрещено.

## 6. Pull Request flow

PR — отдельная ветка после подтверждённой причины, а не обязательный результат любого алерта:

1. Материализовать изолированную workspace из archive зафиксированного SHA.
2. Применить минимальный patch.
3. Выполнить allowlisted test/lint commands в sandbox.
4. Запустить regression checks.
5. Critic сопоставляет patch, evidence и результаты тестов.
6. Human approval.
7. Повторно сверить hashes, атомарно создать commit/branch и draft PR/MR через SCM API.

LLM не задаёт test command. Она выбирает `check_profile` из списка, добавленного event
adapter; реальные argv принадлежат конфигурации сервера. Sandbox запускается с отключённой
сетью, read-only root, dropped capabilities, PID/memory/CPU limits и отдельным `/tmp`.

При отсутствии доказательств или неуспешных тестах создаётся investigation report/issue,
но PR не создаётся.

## 7. Telegram

Telegram является notification adapter, а не частью orchestration logic. События домена:

- incident.received;
- investigation.completed;
- approval.required;
- input.required;
- draft_pr.created;
- recovery.verified;
- investigation.escalated.

Кнопки Telegram могут передавать approval decision в тот же application service, что и UI.

## 8. Проверка архитектуры

Минимальный benchmark содержит CI и runtime сценарии с известным root cause. Сравниваются:

- single prompt baseline;
- граф без reflection;
- полный граф.

Основные метрики: root-cause accuracy, evidence completeness, unsafe action rate, recovery
success, лишние tool calls, latency и token cost.
