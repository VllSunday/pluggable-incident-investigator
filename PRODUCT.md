# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Основной пользователь — solo-разработчик или небольшая инженерная команда. Пользователь
поддерживает собственные приложения без выделенного SRE-отдела и должен быстро понять,
почему упала сборка или сработал runtime-алерт, не отдавая агенту неограниченный доступ.

## Product Purpose

Pluggable Multi-Agent Incident Investigator принимает CI- и runtime-события, собирает
доказательства из подключённых систем, проверяет конкурирующие гипотезы и предлагает
безопасное следующее действие. Успех означает, что пользователь видит доказуемую причину,
может проверить предлагаемый patch и контролирует каждое критическое действие.

## Positioning

Один durable orchestration core работает с разными классами инцидентов через подключаемые
адаптеры. В отличие от универсального coding chat, система автоматически принимает события,
сохраняет траекторию, применяет внешнюю policy, требует approval и проверяет восстановление.

## Operating Context

- GitHub Actions и GitLab CI pipeline failures.
- Prometheus Alertmanager runtime alerts.
- GitHub Pull Requests и GitLab Merge Requests.
- Логи CI, commit diff, метрики Prometheus, runbooks и результаты тестов.
- Локальная установка или один сервер через Docker Compose.
- Telegram используется для оперативных уведомлений; dashboard — для расследования и review.

## Capabilities and Constraints

- Ядро не предполагает автоматическую совместимость с неизвестной инфраструктурой: для новой
  системы требуется adapter и конфигурация permissions.
- LLM не получает неограниченный shell и не может обойти policy engine.
- Draft PR/MR создаётся только после подтверждения причины, sandbox-проверки и Human-in-the-Loop.
- SQLite рассчитан на локальную установку и один server process; horizontal scaling потребует
  PostgreSQL.
- Интерфейс поддерживает русский и английский языки с явным переключателем.
- Незавершённое решение: конкретный визуальный язык dashboard.

## Evidence on Hand

- Реализованное LangGraph-ядро и адаптерные контракты.
- Реальные GitHub, GitLab и Prometheus HTTP adapters.
- Persistent queue/checkpoints, policy, HitL и authenticated API.
- Тестовый набор проекта; коммерческие клиенты, публичные benchmark-результаты и testimonials
  отсутствуют и не должны выдумываться.

## Product Principles

1. Evidence before confidence — каждый вывод ссылается на источник.
2. Approval before impact — критические действия всегда контролирует человек.
3. One core, explicit adapters — расширяемость достигается контрактами, а не скрытой магией.
4. Fail visibly and safely — недостаток данных ведёт к fallback или escalation, а не к догадке.
5. Useful for one developer — установка и ежедневное использование не требуют SRE-платформы.

## Accessibility & Inclusion

Dashboard должен быть доступен с клавиатуры, поддерживать reduced motion, сохранять читаемый
контраст и не использовать один цвет как единственный носитель статуса.
