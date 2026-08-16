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

## 1. Runtime incident: автономное расследование и remediation

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
3. Агент сам забирает метрики Prometheus и структурированные application logs.
4. Кворум `application_log + metric_snapshot` подтверждает причину; Reflexion допускает только allowlisted action.
5. Граф останавливается в `awaiting_approval`: до решения человека конфигурация не меняется.
6. После кнопки «Разрешить действие» executor откатывает только `runtime-demo` к `target_error_fraction=0.0`.
7. Агент сам ждёт healthy `/health` и исчезновения firing-alert в Prometheus, затем закрывает инцидент как recovered.

### Как читать dashboard

1. Начните с тёмного блока **«Что делать сейчас»** — там указано, требуется ли ваше действие
   и вносил ли агент какие-либо изменения.
2. В **«Сигнале»** проверьте, какой сервис и внешнее событие запустили расследование.
3. В **«Доказательствах»** сверяйте факты: метрики, CI-логи и snapshots. Длинные исходные
   данные открываются отдельно и не являются выводом агента.
4. **«Гипотезы»** — это версии причины с уровнем уверенности, а не подтверждённые факты.
5. **«Проверка вывода»** показывает самокритику агента и объясняет, почему он продолжил,
   предложил действие или передал расследование человеку.
6. **«Безопасное действие»** требует внимания только при статусе «Нужно решение». Для runtime-инцидента
   действие не выполняется, а для CI-инцидента ветка и PR/MR не публикуются до approval.
7. **«Результат»** содержит не только ответ executor, но и отдельное доказательство восстановления.

Статус **«Эскалация»** не означает сбой приложения Investigator. Он означает, что агент
сохранил evidence, не нашёл достаточно безопасного автоматического действия и перечислил,
что должен проверить человек или какой adapter нужно подключить.

Статус **«Нужны данные»** означает временную паузу, а не завершение расследования. Dashboard
показывает точный вопрос и причину. Вставьте релевантный фрагмент либо приложите один файл
TXT/LOG/JSON/YAML и нажмите **«Передать агенту и продолжить»**. Агент сохранит provenance и
продолжит тот же checkpoint. Если получить данные невозможно, нажмите
**«Не могу предоставить данные»** — инцидент перейдёт в безопасную ручную эскалацию.

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

В read-only deployment с выключенным remediation тот же webhook-path штатно завершается
`no_safe_action`: evidence и причина сохраняются, но branch не создаётся.

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
