# Threat model

## Scope и активы

Защищаемые активы: SCM credentials, webhook secrets, source code, incident evidence,
approval decisions, sandbox host и возможность создать branch/PR/MR. LLM считается
недоверенным decision component: её вывод валидируется схемой и не является разрешением.

## Trust boundaries

```text
Internet webhook
  -> authenticated FastAPI ingress
  -> durable SQLite queue / LangGraph checkpoint
  -> read-only evidence adapters
  -> LLM structured reasoning
  -> policy + remediation boundary
  -> isolated Docker checks
  -> Human approval
  -> least-privilege SCM write adapter
```

Prometheus queries, sandbox commands и разрешённые action tools принадлежат конфигурации
оператора. Event payload и LLM не могут добавить произвольный PromQL или shell command.

## Основные угрозы и контрмеры

| Угроза | Возможный ущерб | Контрмера | Остаточный риск |
|---|---|---|---|
| Поддельный webhook | Ложное расследование, расход токенов | HMAC/shared token до parsing, Pydantic validation | Компрометация webhook secret |
| Повторная доставка | Дублированные действия | Unique correlation ID, idempotency key, durable state | Неверная стратегия correlation у нового adapter |
| Prompt injection в логах/diff | Обход policy, утечка | Evidence трактуется как данные; structured outputs; policy вне LLM | Модель может дать плохую гипотезу, но не разрешение |
| Secret в CI log | Попадание в LLM/trace/UI | Redaction patterns, log truncation, минимум trace metadata | Неизвестный формат секрета требует нового detector |
| Произвольный shell | Выполнение вредного кода | Только server-owned argv profiles; Docker без сети, read-only root, dropped capabilities, limits | Уязвимость container runtime или слишком широкий image |
| Path traversal в patch | Изменение файлов вне workspace | Normalized relative paths, deny absolute/parent paths, allowlisted changes | Ошибка в patch parser |
| TOCTOU между review и publish | Публикация непроверенного patch | Patch/workspace hashes повторно сверяются после HitL | Компрометация процесса/host |
| Excessive agency | Перезапуск/merge без человека | Risk policy, LangGraph interrupt, draft-only PR/MR | Ошибочная настройка action risk |
| SSRF/произвольный PromQL | Доступ к внутренним данным | Base URL и PromQL templates задаёт сервер | Оператор может настроить слишком широкий query |
| Token leakage | Захват SCM/Telegram | `.env` ignored, SecretStr, least-privilege project token, токены не логируются | Host/admin compromise |
| Resource exhaustion / loop | Cost и denial of service | Tool-call, iteration, elapsed-time budgets; truncation + escalation | Большой вход до нормализации должен ограничиваться proxy |
| Потеря процесса | Потеря расследования | SQLite queue, WAL, durable checkpoints, requeue running work | Один host остаётся single point of failure |

## Security invariants

1. До approval не существует внешней remediation branch.
2. LLM не задаёт executable argv и не получает Docker socket.
3. Failure evidence provider не превращается в разрешение на action.
4. Publish использует ровно проверенный commit SHA и повторно проверенный patch hash.
5. Runtime-only incident без зарегистрированного executor заканчивается эскалацией.
6. Notification failure не ломает investigation transaction.

## Production hardening после capstone

- Перенести queue/checkpoints в PostgreSQL перед запуском нескольких replicas.
- Разделить webhook/API и sandbox worker по разным hosts/identities.
- Использовать GitHub App/GitLab project tokens с rotation вместо долгоживущего PAT.
- Поставить TLS reverse proxy, body/rate limits и egress policy.
- Хранить secrets в platform secret manager и включить audit log retention.
- Pin sandbox image по digest и регулярно сканировать image/SBOM.
