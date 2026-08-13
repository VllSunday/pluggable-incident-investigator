# Demo runbook

Runbook рассчитан на защиту проекта за 10–12 минут и показывает два разных класса
инцидентов на одном orchestration core.

## 0. Предварительная проверка

```powershell
uv run ruff check src tests scripts demo
uv run pytest
uv run pytest -o "addopts=-q" -m docker
```

Ожидаемо: lint без замечаний, unit suite зелёный, отдельный Docker integration зелёный.
Не показывайте `.env` или terminal history с токенами.

## 1. Runtime incident: реальный webhook и metrics evidence

```powershell
docker compose -f compose.yaml -f compose.runtime.yaml up -d --build
```

Откройте:

- dashboard: `http://127.0.0.1:8501`;
- Prometheus alerts: `http://127.0.0.1:9090/alerts`;
- Alertmanager: `http://127.0.0.1:9093`.

Показать аудитории:

1. Prometheus target остаётся `up=1`, но error ratio равен `0.8`.
2. Alertmanager сам отправляет authenticated webhook; ручного payload нет.
3. API отвечает `202`, а расследование выполняется durable worker в фоне.
4. Dashboard показывает signal → evidence → hypotheses → Reflexion.
5. После трёх итераций и 12 tool calls система безопасно эскалирует, не выдумывая action.

Проверка ground truth:

```powershell
uv run python scripts/evaluate_incidents.py `
  --case runtime_high_error_ratio `
  --minimum-score 0.8
```

Ожидаемо: score `1.0` для event match, evidence coverage, root cause, terminal status,
budget и safe action.

## 2. CI incident: GitLab remediation и draft MR

Используйте заранее созданный fixture pipeline или новый контролируемый failing commit:

```powershell
uv run python scripts/run_connected_gitlab_demo.py `
  --repository AllSunday/incident-investigator-demo-ci `
  --pipeline-id <FAILED_PIPELINE_ID> `
  --sha <FAILED_COMMIT_SHA>
```

Без `--approve` покажите:

1. failed job log и commit diff собраны разными tool calls;
2. агент нашёл off-by-one в `retry_delay`;
3. первый patch при необходимости прошёл bounded repair;
4. pytest и Ruff выполнены в sandbox без сети;
5. независимый critic подтвердил patch;
6. LangGraph остановился на HitL, branch ещё не создана.

Только для специально выделенного demo project повторите с `--approve`. Ожидаемый
результат: один commit, отдельная branch и draft GitLab MR. Merge не выполняется агентом.
Уже проверенный пример: `AllSunday/incident-investigator-demo-ci!1`; его pipeline завершился
успешно.

## 3. Что подчеркнуть на защите

- Универсален investigation lifecycle, а не знания обо всех системах.
- GitHub и GitLab реализуют общий SCM contract; Prometheus — read-only evidence contract.
- Policy, budgets, sandbox и approval находятся вне LLM prompt.
- Runtime и CI проходят один state graph, но используют разные adapters/evidence/action path.
- Любой внешний side effect возникает только после server checks и Human-in-the-Loop.

## 4. Cleanup

```powershell
docker compose -f compose.yaml -f compose.runtime.yaml down
```

Добавьте `-v`, только если нужно удалить synthetic incident history и начать demo с чистого
состояния. Draft MR оставьте открытым для проверки или закройте вручную после защиты; не
merge автоматически.
