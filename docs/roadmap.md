# Roadmap

## Milestone 1 — Foundation — готово

- Доменные модели и adapter ports.
- GitHub/Alertmanager event normalization.
- Policy engine, budgets и tool runtime.
- Unit и failure-path tests.

## Milestone 2 — Investigation graph — готово

- LangGraph state и durable checkpoint.
- Structured LLM outputs.
- Evidence collection, hypothesis verification и reflection loop.
- Bounded evidence execution с graceful truncation и эскалацией.

Готовы durable SQLite checkpoints, structured OpenAI engine, persistent budgets и обработка
async provider failures. Следующий observability-шаг — trace metadata/tags и eval dashboard.

## Milestone 3 — Demo environments — стенды готовы

- GitHub repository с контролируемыми CI failures.
- Docker Compose: demo app, Prometheus, Alertmanager и логи.
- Ground-truth fixtures и eval runner.

GitHub и GitLab CI fixtures проверены на реальных pipeline. Runtime fixture проверен по
полному пути Prometheus rule → Alertmanager webhook → durable graph → Prometheus evidence.
GitLab fixture также проверен через authenticated webhook → durable graph → real GitLab
evidence в read-only deployment. Ground-truth eval runner покрывает оба класса.

## Milestone 4 — Safe remediation — core готов

- Изолированная archive workspace и patch policy.
- Allowlisted Docker checks, structured critic и hash revalidation.
- Human approval и draft GitHub PR/GitLab MR через общий SCM contract.

Отдельные demo repositories и sandbox image готовы. GitLab end-to-end создал настоящий
draft MR после patch repair, pytest, Ruff, critic и HitL; pipeline MR успешно завершился.

## Milestone 5 — Interfaces — основной UI готов

- FastAPI webhook/API service.
- Streamlit investigation dashboard.
- Telegram notifications и approval callback.

FastAPI incident/approval API, Telegram message sink и двуязычный Streamlit dashboard готовы.
Telegram callback остаётся отдельным transport enhancement.

## До завершённого capstone

Browser-based QA двуязычного dashboard завершён на desktop/mobile: language route,
операторские budget notes и компактное представление metric evidence проверены.

1. Credential-dependent smoke tests: Telegram test chat и LangSmith cloud trace.
2. Telegram approval callback остаётся optional enhancement и не блокирует capstone.

Threat model, demo runbook и проверенная презентация с измеримыми результатами готовы.
