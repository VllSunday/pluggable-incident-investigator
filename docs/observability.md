# Observability и evaluation

## LangSmith tracing

LangGraph поддерживает LangSmith через стандартные environment variables. Добавьте в
локальный `.env` или secret store сервера:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<secret>
LANGSMITH_PROJECT=incident-investigator
```

Каждый graph run получает tags `incident-investigator`, `source:<adapter>` и
`kind:<incident-kind>`, а также metadata с incident ID, correlation ID, service, source и
kind. Секреты и полные исходные файлы в metadata не передаются. По этим полям можно
сравнивать CI и runtime traces, latency, tool-call trajectory и зацикливания.

Без `LANGSMITH_TRACING=true` система работает полностью локально; observability не является
зависимостью для исполнения расследования.

## Ground-truth evaluation

Cases находятся в `evals/ground_truth.yaml`. Runner читает durable incident records через
защищённый API и оценивает:

- правильность нормализации события;
- наличие обязательных типов evidence;
- совпадение гипотезы с известной причиной;
- корректный terminal status;
- соблюдение tool-call budget;
- отсутствие action там, где разрешено только расследование.

Для запущенного runtime fixture:

```powershell
uv run python scripts/evaluate_incidents.py `
  --case runtime_high_error_ratio `
  --minimum-score 0.8
```

Если обязательный case не найден или score ниже порога, процесс завершается с ненулевым
exit code. Для offline CI можно экспортировать ответ `/api/incidents` в JSON и передать его
через `--input`; токен в отчёт не записывается.
