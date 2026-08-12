# Roadmap

## Milestone 1 — Foundation — готово

- Доменные модели и adapter ports.
- GitHub/Alertmanager event normalization.
- Policy engine, budgets и tool runtime.
- Unit и failure-path tests.

## Milestone 2 — Investigation graph — основа готова

- LangGraph state и durable checkpoint.
- Structured LLM outputs.
- Evidence collection, hypothesis verification и reflection loop.
- LangSmith tracing.

Готовы durable SQLite checkpoints, structured OpenAI engine и persistent budgets. Осталось
зафиксировать trace metadata/tags и собрать eval dashboard.

## Milestone 3 — Demo environments — следующий

- GitHub repository с контролируемыми CI failures.
- Docker Compose: demo app, Prometheus, Alertmanager и логи.
- Ground-truth fixtures и eval runner.

## Milestone 4 — Safe remediation — core готов

- Изолированная archive workspace и patch policy.
- Allowlisted Docker checks, structured critic и hash revalidation.
- Human approval и draft GitHub PR/GitLab MR через общий SCM contract.

Осталось подготовить отдельный demo repository/sandbox image с известными поломками и
проверить реальный PR/MR end-to-end на тестовых GitHub/GitLab проектах.

## Milestone 5 — Interfaces — основной UI готов

- FastAPI webhook/API service.
- Streamlit investigation dashboard.
- Telegram notifications и approval callback.

FastAPI incident/approval API, Telegram message sink и двуязычный Streamlit dashboard готовы.
Telegram callback остаётся отдельным transport enhancement.
