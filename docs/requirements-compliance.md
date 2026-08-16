# Соответствие исходному техническому заданию

Документ фиксирует проверяемое соответствие capstone-проекта требованиям курса. Он не
считает frontend обязательным доказательством agentic architecture: основные гарантии
реализованы в orchestration core, policy layer и adapters.

## Orchestration & Logic

| Требование | Реализация | Проверка |
|---|---|---|
| ReAct | Цикл evidence → hypotheses → Reflexion → tool request → новое evidence | `tests/test_graph.py` |
| Plan-and-Execute | Явные стадии collect, reason, reflect, propose, policy, execute, verify | `core/graph.py` |
| Reflexion | Отдельный узел критики с gather-more, ready и escalate outcomes | `tests/test_graph.py` |
| LangGraph state | Typed state, conditional edges, durable thread ID и SQLite checkpointer | `core/graph.py`, `api/app.py` |
| Self-correction | Дополнительный evidence loop, patch repair и independent remediation critic | `tests/test_graph.py`, `tests/test_remediation.py` |
| Action fallback | Tool/recovery failure превращается в evidence и запускает bounded replan | `test_graph_replans_*` |
| Защита от loops | Iteration, elapsed-time, tool-call и action-replan budgets; failed idempotency key нельзя повторить | `test_graph_*budget*`, `test_graph_blocks_repeating_*` |

## Tools & Integrations

| Группа | Реализация |
|---|---|
| Event tools | GitHub Actions webhook, GitLab Pipeline Hook, Prometheus Alertmanager |
| Read-only evidence | GitHub/GitLab CI logs и diffs, Prometheus metrics, runtime diagnostics, operator evidence |
| Action tools | Allowlisted runtime rollback, GitHub draft PR, GitLab draft MR |
| Code execution | Network-isolated Docker sandbox с server-owned test/lint profiles |
| Notifications | Telegram adapter |
| Persistence | SQLite queue, deduplication и LangGraph checkpoints |

Все внешние границы типизированы Pydantic-моделями. Evidence tools допускают частичный отказ:
ошибка одного provider не уничтожает результаты остальных. Action tools имеют timeout,
retry, idempotency key, policy decision и bounded fallback. Неизвестные инструменты запрещены.

## Human-in-the-Loop & Safety

- Graph interrupt запрашивает недостающий контекст и продолжает тот же checkpoint.
- Отдельный graph interrupt требуется перед high/critical runtime action.
- Patch, sandbox checks и critic report формируются до approval draft PR/MR.
- Отклонённый remediation workspace удаляется; merge никогда не выполняется автоматически.
- Policy engine, allowlists и sandbox находятся вне LLM prompt.

## Observability & Evaluation

- LangGraph run получает incident/source/kind tags и безопасную metadata.
- OpenAI SDK обёрнут `langsmith.wrappers.wrap_openai`; LLM spans содержат model, latency и
  token usage.
- `scripts/verify_observability.py` проверяет настоящий OpenAI call и появление LangSmith span.
- Ground-truth runner оценивает event matching, evidence coverage, root cause, terminal
  status, tool budget и безопасность action.
- Runtime end-to-end case достигает score `1.0` после approved rollback и recovery check.

## Проверенный результат

На 16 августа 2026 года:

- `uv run pytest`: 93 unit/integration tests passed, Docker marker excluded;
- `uv run pytest -m docker`: real Docker remediation test passed;
- `uv run ruff check src tests`: passed;
- Compose runtime smoke test: alert → evidence → hypothesis → approval → rollback →
  recovery verification → `recovered`;
- ground-truth runtime score: `1.0`;
- OpenAI + LangSmith observability probe: LLM span найден, token usage получен.

## Граница production-ready

Проект соответствует capstone-ТЗ и готов как production-oriented single-node deployment.
Для нескольких replicas потребуется заменить SQLite queue/checkpoints на PostgreSQL и
добавить корпоративные SSO/RBAC/TLS — это эксплуатационное масштабирование, а не недостающая
часть агентного ядра.
