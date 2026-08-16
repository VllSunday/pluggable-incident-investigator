# Подключение к production-системе

## Короткий ответ

Investigator разворачивается один раз как внутренний сервис. Отдельный репозиторий для каждого
инцидента не создаётся: существующие GitHub/GitLab-проекты и Alertmanager отправляют события в
один API, а расследования и checkpoints хранятся централизованно.

Безопасный путь внедрения состоит из четырёх ступеней:

1. **Shadow:** только чтение evidence и отчёт, без действий.
2. **Draft:** отдельная ветка и draft PR/MR после sandbox-проверок.
3. **Controlled action:** узкие обратимые runtime-actions после approval.
4. **Automation:** автоматизируются только многократно проверенные low-risk операции.

Не начинайте сразу с четвёртой ступени.

## Топология

```text
GitHub / GitLab ──webhook──┐
                           │
Alertmanager ─────webhook──┼──> Investigator API + worker
                           │          │
                           │          ├── evidence: SCM / Prometheus / logs
                           │          ├── durable investigation state
                           │          └── policy + approval + recovery check
                           │
                           └──── Dashboard / Telegram
```

Для небольшой команды достаточно одного приватного Linux-сервера за HTTPS reverse proxy.
Публично должны быть доступны только webhook endpoints и dashboard через вашу аутентификацию.
SQLite означает один worker process; горизонтальное масштабирование пока не поддерживается.

## GitHub и GitLab

### События

- GitHub: `POST https://investigator.example.com/webhooks/github`, event `Workflow runs`.
- GitLab: `POST https://investigator.example.com/webhooks/gitlab`, trigger `Pipeline events`.

Webhook secret только подтверждает источник события. Для evidence нужен отдельный токен:

- GitHub fine-grained token или GitHub App: Actions read, Contents read; Contents и Pull
  requests write добавляются только при включении draft PR.
- GitLab project access token: `read_repository` для анализа; `api` добавляется только для
  публикации branch/MR.

Один GitHub App может быть установлен в несколько выбранных репозиториев. Для GitLab можно
использовать project tokens или отдельного bot-user с доступом только к нужной группе. Ветка с
исправлением создаётся в исходном проекте, а не в дополнительном служебном репозитории.

Рекомендуемый первый запуск:

```dotenv
INVESTIGATOR_MODE=connected
INVESTIGATOR_REMEDIATION_ENABLED=false
```

Так агент собирает job logs и diff, строит расследование и ничего не записывает обратно. После
проверки качества включите remediation только для одного тестового проекта и одного server-owned
check profile.

## Runtime-инциденты

Alertmanager уже поддерживается. Receiver отправляет webhook с отдельным bearer token:

```yaml
receivers:
  - name: incident-investigator
    webhook_configs:
      - url: https://investigator.example.com/webhooks/alertmanager
        http_config:
          authorization:
            credentials: ${INVESTIGATOR_ALERTMANAGER_WEBHOOK_TOKEN}
```

PromQL поступает не из alert и не от LLM. Запросы задаются оператором через allowlisted templates,
а модель получает только результаты.

Текущий `RuntimeLogEvidenceProvider` обслуживает встроенный fixture endpoint. Для настоящей
среды нужно добавить read-only provider для Loki, Elasticsearch, Sentry или вашего log API,
реализующий общий `EvidenceProvider` contract. Аналогично, встроенный rollback предназначен
только для demo. Production action должен быть отдельным узким executor, например:

- перезапустить один allowlisted Kubernetes Deployment;
- откатить конкретный feature flag;
- повторно запустить один CI job;
- создать issue или change request.

Executor обязан самостоятельно валидировать service, namespace, аргументы и idempotency key.
LLM не должна получать `kubectl`, Docker socket или unrestricted shell.

## Как добавить адаптер

Стабильные границы находятся в `src/incident_investigator/core/ports.py`:

- `EventAdapter` проверяет подпись и создаёт `IncidentEvent`;
- `EvidenceProvider` выполняет только чтение и возвращает `EvidenceItem` с provenance;
- `ActionExecutor` исполняет один тип разрешённого действия;
- `RecoveryVerifier` независимо проверяет фактический результат;
- `NotificationSink` сообщает о смене состояния.

Новый адаптер регистрируется в composition root `src/incident_investigator/api/app.py`. Ядро и
граф при этом не меняются. Для production provider нужны contract tests на timeout, неверную
аутентификацию, пустой ответ, повторную доставку и redaction.

## Минимальная production-конфигурация

1. Сгенерировать уникальные webhook/admin secrets.
2. Хранить LLM и SCM tokens в secret manager, а не в image или Git.
3. Поставить TLS reverse proxy и корпоративную аутентификацию перед dashboard.
4. Не монтировать Docker socket в API-контейнер.
5. Запускать sandbox worker на отдельной VM/runner без production credentials.
6. Оставить runtime actions выключенными до прохождения shadow-пилота.
7. Настроить LangSmith или OpenTelemetry-compatible tracing с redaction.
8. Сохранять audit log и резервные копии durable state.

Пример запуска одного сервера находится в [deployment.md](deployment.md).

## Критерии готовности пилота

- 20–50 реальных инцидентов обработаны в shadow mode.
- Нет утечки секретов в traces и dashboard.
- Проверена серия последовательных прогонов, а не один удачный пример.
- Измерены root-cause accuracy, evidence coverage, tool errors, latency и стоимость.
- Каждый action имеет allowlist, idempotency, rollback и независимый recovery check.
- Дежурный инженер понимает, как отклонить действие и как завершить ручную эскалацию.
