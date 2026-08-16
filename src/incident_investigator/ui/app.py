from __future__ import annotations

import json
from contextlib import suppress
from datetime import datetime
from html import escape
from typing import Any

import streamlit as st

from incident_investigator.ui.client import DashboardAPIError, IncidentAPIClient

TEXT = {
    "ru": {
        "app": "Incident Investigator",
        "eyebrow": "ОПЕРАЦИОННЫЙ КОНТУР",
        "subtitle": "Расследования, основанные на доказательствах",
        "queue": "Очередь инцидентов",
        "filter": "Фильтр инцидентов",
        "all": "Все",
        "active": "Активные",
        "approval": "Ждут вас",
        "resolved": "Завершённые",
        "refresh": "Обновить",
        "open": "Открыть",
        "connected": "Ядро на связи",
        "offline": "Ядро недоступно",
        "no_incidents": "Пока тихо",
        "no_incidents_hint": "Новый CI-сбой или Alertmanager alert появится здесь автоматически.",
        "select": "Выберите инцидент в очереди",
        "select_hint": "Здесь раскроется вся траектория расследования: сигнал, доказательства, гипотезы и действие.",
        "signal": "Сигнал",
        "evidence": "Доказательства",
        "hypotheses": "Гипотезы",
        "reflection": "Проверка вывода",
        "action": "Безопасное действие",
        "result": "Результат",
        "received": "получен",
        "evidence_count": "источников",
        "evidence_shown": "показано",
        "confidence": "уверенность",
        "verified": "проверена",
        "unverified": "нужна проверка",
        "supports": "подтверждают",
        "contradicts": "противоречат",
        "checks": "Следующие проверки",
        "why": "Почему агент так решил",
        "risk": "Риск",
        "expected": "Ожидаемый результат",
        "rollback": "Откат",
        "approve": "Разрешить действие",
        "reject": "Отклонить",
        "approval_note": "Действие не будет выполнено без вашего решения.",
        "decision_title": "Агент готов исправить инцидент",
        "decision_copy": "Причина подтверждена доказательствами. Проверьте предлагаемое действие и разрешите его — после этого агент сам выполнит изменение и проверит восстановление.",
        "verification_running": "Выполняю действие и проверяю восстановление сервиса…",
        "recovery_check": "Проверка восстановления",
        "sandbox_checks": "Sandbox-проверки",
        "changed_files": "Изменённые файлы",
        "critic": "Вердикт критика",
        "approved": "Решение отправлено: действие разрешено.",
        "rejected": "Решение отправлено: действие отклонено.",
        "details": "Технические детали",
        "source": "Источник",
        "service": "Сервис",
        "severity": "Важность",
        "correlation": "Correlation ID",
        "updated": "Обновлён",
        "status": "Статус",
        "api_missing": "Не задан INVESTIGATOR_ADMIN_API_TOKEN для dashboard.",
        "retry": "Проверьте API URL, токен и состояние backend-контейнера.",
        "errors": "Ошибки расследования",
        "notes": "Системные заметки",
        "budget_truncated": "Лимит инструментов достигнут: ядро сохранило собранные данные и безопасно передало расследование человеку.",
        "language": "Язык",
        "operator_summary": "Что делать сейчас",
        "what_happened": "Что произошло",
        "agent_found": "Главная гипотеза агента",
        "your_next_step": "Что проверить вам",
        "impact": "Что уже изменено",
        "how_to_read": "Как читать это расследование",
        "guide_copy": "Сначала прочитайте резюме выше. Затем сверяйте вывод агента с блоками 02–04. Блок 05 требует вашего внимания только тогда, когда агент подготовил безопасное действие.",
        "raw_evidence": "Показать исходные данные",
        "source_link": "Открыть источник",
        "finding_pending": "Подтверждённого вывода пока нет — агент продолжает собирать данные.",
        "queued_headline": "Инцидент принят",
        "running_headline": "Агент ведёт расследование",
        "awaiting_approval_headline": "Требуется ваше решение",
        "awaiting_input_headline": "Агенту нужны дополнительные данные",
        "completed_headline": "Расследование завершено",
        "escalated_headline": "Нужна ручная проверка",
        "rejected_headline": "Действие отклонено",
        "failed_headline": "Расследование завершилось с ошибкой",
        "wait_step": "Пока ничего делать не нужно. Дождитесь итогового уведомления.",
        "approval_step": "Проверьте предлагаемое действие, ожидаемый результат и план отката. Затем разрешите или отклоните действие одной кнопкой.",
        "input_step": "Ответьте на точный вопрос агента ниже или приложите файл. После отправки расследование продолжится автоматически с того же места.",
        "escalation_step": "Автоматического исправления нет. Проверьте доказательства и добавьте недостающий источник данных, например логи приложения.",
        "runtime_escalation_step": "Подключите логи приложения (например, Loki) или вручную проверьте ошибки и маршруты сервиса за время инцидента. Метрики уже собраны, но без логов причина не подтверждается.",
        "ci_escalation_step": "Причина CI-сбоя найдена, но публикация исправления отключена. Включите remediation для тестового репозитория и повторите событие, чтобы получить sandbox-проверки и запрос approval.",
        "completed_step": "Проверьте результат в блоке 06 и убедитесь, что сервис или CI действительно восстановились.",
        "failed_step": "Откройте системные ошибки справа, исправьте подключение или credentials и повторите событие.",
        "no_changes": "Изменений не внесено.",
        "approval_impact": "Действие подготовлено, но ещё не выполнено. До вашего решения система ничего не изменит.",
        "input_impact": "Расследование приостановлено. Изменений не внесено, лимит ожидания не расходуется.",
        "draft_impact": "Создан только черновик PR/MR; автоматического merge нет.",
        "completed_impact": "Результат сохранён в истории расследования.",
        "recovered_step": "Ничего делать не нужно: агент выполнил действие и автоматически проверил, что сервис здоров, а алерт больше не активен.",
        "recovered_impact": "Изменение применено; восстановление подтверждено независимой проверкой health и Prometheus.",
        "input_title": "Продолжить расследование",
        "input_copy": "Агент исчерпал доступные источники и сформулировал, какого доказательства не хватает. Передайте его здесь — заново запускать инцидент не нужно.",
        "input_question": "Что именно нужно",
        "input_reason": "Почему без этого нельзя продолжить",
        "input_formats": "Подходящие форматы",
        "input_warning": "Перед отправкой удалите пароли, токены и персональные данные. Система дополнительно маскирует типовые секреты.",
        "input_text_label": "Вставьте логи, конфигурацию или ответ",
        "input_text_help": "Только относящийся к инциденту фрагмент; не отправляйте секреты.",
        "input_file_label": "Или приложите текстовый файл",
        "input_file_help": "TXT, LOG, JSON, YAML; не более 1 МБ.",
        "input_submit": "Передать агенту и продолжить",
        "input_decline": "Не могу предоставить данные",
        "input_required": "Добавьте текст или файл.",
        "input_one_source": "Выберите один вариант: текст или файл.",
        "input_running": "Сохраняю доказательство и продолжаю расследование…",
        "input_sent": "Данные приняты. Агент продолжил расследование.",
        "input_declined": "Запрос закрыт. Инцидент передан на ручное расследование.",
    },
    "en": {
        "app": "Incident Investigator",
        "eyebrow": "OPERATIONS CONTROL",
        "subtitle": "Evidence-led incident investigations",
        "queue": "Incident queue",
        "filter": "Incident filter",
        "all": "All",
        "active": "Active",
        "approval": "Needs you",
        "resolved": "Resolved",
        "refresh": "Refresh",
        "open": "Open",
        "connected": "Core connected",
        "offline": "Core unavailable",
        "no_incidents": "All quiet",
        "no_incidents_hint": "A new CI failure or Alertmanager alert will appear here automatically.",
        "select": "Select an incident from the queue",
        "select_hint": "Its full investigation path will unfold here: signal, evidence, hypotheses and action.",
        "signal": "Signal",
        "evidence": "Evidence",
        "hypotheses": "Hypotheses",
        "reflection": "Conclusion check",
        "action": "Safe action",
        "result": "Outcome",
        "received": "received",
        "evidence_count": "sources",
        "evidence_shown": "shown",
        "confidence": "confidence",
        "verified": "verified",
        "unverified": "needs verification",
        "supports": "support",
        "contradicts": "contradict",
        "checks": "Next checks",
        "why": "Why the agent decided this",
        "risk": "Risk",
        "expected": "Expected outcome",
        "rollback": "Rollback",
        "approve": "Allow action",
        "reject": "Reject",
        "approval_note": "The action cannot run without your decision.",
        "decision_title": "The agent is ready to remediate",
        "decision_copy": "The cause is supported by evidence. Review the proposed action and allow it; the agent will then execute it and verify recovery automatically.",
        "verification_running": "Executing the action and verifying service recovery…",
        "recovery_check": "Recovery verification",
        "sandbox_checks": "Sandbox checks",
        "changed_files": "Changed files",
        "critic": "Critic verdict",
        "approved": "Decision sent: action approved.",
        "rejected": "Decision sent: action rejected.",
        "details": "Technical details",
        "source": "Source",
        "service": "Service",
        "severity": "Severity",
        "correlation": "Correlation ID",
        "updated": "Updated",
        "status": "Status",
        "api_missing": "INVESTIGATOR_ADMIN_API_TOKEN is not configured for the dashboard.",
        "retry": "Check the API URL, token and backend container.",
        "errors": "Investigation errors",
        "notes": "System notes",
        "budget_truncated": "The tool limit was reached: the core preserved collected evidence and safely escalated the investigation.",
        "language": "Language",
        "operator_summary": "What to do now",
        "what_happened": "What happened",
        "agent_found": "Leading agent hypothesis",
        "your_next_step": "What you need to check",
        "impact": "What has changed",
        "how_to_read": "How to read this investigation",
        "guide_copy": "Start with the summary above. Then verify the agent's conclusion against sections 02–04. Section 05 needs your attention only when the agent has prepared a safe action.",
        "raw_evidence": "Show raw evidence",
        "source_link": "Open source",
        "finding_pending": "There is no confirmed conclusion yet — the agent is still collecting evidence.",
        "queued_headline": "Incident received",
        "running_headline": "The agent is investigating",
        "awaiting_approval_headline": "Your decision is required",
        "awaiting_input_headline": "The agent needs additional evidence",
        "completed_headline": "Investigation completed",
        "escalated_headline": "Manual review needed",
        "rejected_headline": "Action rejected",
        "failed_headline": "Investigation failed",
        "wait_step": "Nothing to do yet. Wait for the final notification.",
        "approval_step": "Review the proposed action, expected outcome and rollback plan. Then allow or reject it with one button.",
        "input_step": "Answer the agent's exact question below or attach a file. The investigation will resume automatically from the same point.",
        "escalation_step": "No automatic fix is available. Review the evidence and connect the missing data source, such as application logs.",
        "runtime_escalation_step": "Connect application logs (for example, Loki) or inspect service errors and routes for the incident window. Metrics are available, but logs are still required to verify the cause.",
        "ci_escalation_step": "The CI cause is known, but fix publication is disabled. Enable remediation for the test repository and replay the event to run sandbox checks and request approval.",
        "completed_step": "Review the outcome in section 06 and confirm that the service or CI actually recovered.",
        "failed_step": "Open the system errors on the right, fix the connection or credentials, and replay the event.",
        "no_changes": "No changes were made.",
        "approval_impact": "The action is prepared but has not run. Nothing changes before your decision.",
        "input_impact": "The investigation is paused. No changes were made and the waiting time does not consume its budget.",
        "draft_impact": "Only a draft PR/MR was created; it was not merged automatically.",
        "completed_impact": "The outcome was saved to the investigation history.",
        "recovered_step": "Nothing else is required: the agent executed the action and verified that the service is healthy and the alert is no longer firing.",
        "recovered_impact": "The change was applied; recovery was independently verified through health and Prometheus.",
        "input_title": "Continue the investigation",
        "input_copy": "The agent exhausted its available sources and identified the missing evidence. Supply it here; you do not need to restart the incident.",
        "input_question": "What is needed",
        "input_reason": "Why the agent cannot proceed without it",
        "input_formats": "Accepted formats",
        "input_warning": "Remove passwords, tokens and personal data before sending. The system also masks common secret patterns.",
        "input_text_label": "Paste logs, configuration or your answer",
        "input_text_help": "Include only the incident-related excerpt; do not send secrets.",
        "input_file_label": "Or attach a text file",
        "input_file_help": "TXT, LOG, JSON or YAML; up to 1 MB.",
        "input_submit": "Send to agent and continue",
        "input_decline": "I cannot provide this",
        "input_required": "Add text or a file.",
        "input_one_source": "Choose one option: text or file.",
        "input_running": "Saving the evidence and resuming the investigation…",
        "input_sent": "Evidence accepted. The agent resumed the investigation.",
        "input_declined": "The request was closed. The incident was handed off for manual investigation.",
    },
}

STATUS_LABELS = {
    "ru": {
        "queued": "В очереди", "running": "Расследуется", "awaiting_input": "Нужны данные", "awaiting_approval": "Нужно решение",
        "completed": "Завершён", "escalated": "Эскалация", "rejected": "Отклонён", "failed": "Ошибка",
    },
    "en": {
        "queued": "Queued", "running": "Investigating", "awaiting_input": "Needs evidence", "awaiting_approval": "Needs decision",
        "completed": "Completed", "escalated": "Escalated", "rejected": "Rejected", "failed": "Failed",
    },
}

STATUS_SYMBOLS = {
    "queued": "○", "running": "◌", "awaiting_input": "?", "awaiting_approval": "!", "completed": "✓",
    "escalated": "↑", "rejected": "×", "failed": "×",
}


def _css() -> str:
    return """
    <style>
    :root { --paper:#f5f3ec; --ink:#20231f; --muted:#687069; --line:#d9d7cd;
      --verm:#c94735; --gold:#b68a35; --ok:#307257; --white:#fffefa; }
    .stApp { background:
      linear-gradient(90deg, rgba(32,35,31,.035) 1px, transparent 1px) 0 0/32px 32px,
      linear-gradient(rgba(32,35,31,.025) 1px, transparent 1px) 0 0/32px 32px,
      var(--paper); color:var(--ink); }
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stAppDeployButton"] { display:none!important; }
    #MainMenu, footer { visibility:hidden; }
    .block-container { max-width:1680px; padding:1.35rem 2rem 3rem; }
    html, body, [class*="css"] { font-family:"Segoe UI Variable","Aptos",system-ui,sans-serif; }
    h1,h2,h3,p { color:var(--ink); }
    .topbar { display:flex;justify-content:space-between;align-items:center;gap:1rem; }
    .brand { display:flex; align-items:center; gap:.85rem; min-height:48px; }
    .brand-mark { width:34px;height:34px;background:var(--verm);clip-path:polygon(0 0,100% 0,100% 64%,64% 100%,0 100%);position:relative; }
    .brand-mark:after { content:""; position:absolute; width:16px;height:1px;background:#fff;transform:rotate(-45deg);right:1px;bottom:8px; }
    .eyebrow { font-size:.66rem;font-weight:750;letter-spacing:.18em;color:var(--verm);margin-bottom:.15rem; }
    .brand-title { font-size:1.12rem;font-weight:680;letter-spacing:-.025em;line-height:1.05; }
    .brand-sub { font-size:.76rem;color:var(--muted);margin-top:.18rem; }
    .lang-switch { display:flex;border:1px solid var(--ink); }
    .lang-switch a { min-width:48px;padding:.55rem .75rem;text-align:center;color:var(--ink);text-decoration:none;font-size:.76rem;font-weight:650; }
    .lang-switch a + a { border-left:1px solid var(--ink); }
    .lang-switch a.current { background:var(--verm);color:#fff;border-color:var(--verm); }
    .lang-switch a:focus-visible { outline:2px solid var(--verm);outline-offset:3px; }
    .connection { display:flex;gap:.45rem;align-items:center;font-size:.74rem;color:var(--muted);padding-top:.75rem; }
    .connection i { width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 4px rgba(48,114,87,.12); }
    .connection.offline i { background:var(--verm);box-shadow:0 0 0 4px rgba(201,71,53,.12); }
    .section-label { margin:1.45rem 0 .7rem;font-size:.68rem;font-weight:750;letter-spacing:.13em;text-transform:uppercase;color:var(--muted); }
    .incident { display:block;padding:.9rem 1rem;border:1px solid transparent;background:rgba(255,254,250,.45);margin-bottom:.45rem; }
    .incident.selected { background:var(--white);border-color:var(--line);box-shadow:0 8px 26px rgba(43,46,40,.06); }
    .incident.selected .incident-source { color:var(--verm); }
    .incident-top { display:flex;justify-content:space-between;align-items:center;gap:.5rem; }
    .incident-source { font-size:.65rem;letter-spacing:.11em;text-transform:uppercase;color:var(--muted); }
    .incident-time { font:600 .68rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted); }
    .incident-title { font-weight:660;font-size:.9rem;line-height:1.28;margin:.45rem 0 .55rem; }
    .incident-meta { display:flex;justify-content:space-between;align-items:center;font-size:.71rem;color:var(--muted); }
    .state { display:inline-flex;align-items:center;gap:.35rem;color:var(--ink); }
    .state b { display:grid;place-items:center;width:17px;height:17px;border:1px solid currentColor;border-radius:50%;font-size:.65rem; }
    .state.awaiting_input,.state.awaiting_approval { color:var(--verm);font-weight:700; }
    .state.completed { color:var(--ok); }
    .state.failed,.state.rejected { color:var(--verm); }
    .case-head { padding:1.1rem 0 1.4rem;border-bottom:1px solid var(--line);margin-bottom:.25rem; }
    .case-kicker { display:flex;gap:.6rem;align-items:center;font:650 .68rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted);text-transform:uppercase; }
    .severity { color:var(--verm); }
    .case-head h1 { font-size:clamp(1.7rem,3vw,2.75rem);line-height:1.03;letter-spacing:-.045em;margin:.65rem 0 .55rem;max-width:850px; }
    .case-deck { color:var(--muted);font-size:.9rem; }
    .operator-summary { margin:1rem 0 1.1rem;background:var(--ink);color:var(--white);padding:1.1rem 1.2rem 1.2rem;clip-path:polygon(0 0,calc(100% - 18px) 0,100% 18px,100% 100%,0 100%); }
    .operator-summary .section-label { color:#d7d8d1;margin:0 0 .3rem; }
    .operator-summary h2 { color:var(--white);font-size:1.2rem;letter-spacing:-.02em;margin:.15rem 0 1rem; }
    .operator-grid { display:grid;grid-template-columns:1fr 1.35fr;gap:1rem 1.4rem; }
    .decision-panel { margin:.4rem 0 1rem;padding:1rem 1.2rem;background:var(--white);border:1px solid var(--verm); }
    .decision-panel h2 { margin:0 0 .35rem;font-size:1.12rem;letter-spacing:-.02em; }
    .decision-panel p { margin:0;max-width:72ch;color:var(--ink);font-size:.9rem;line-height:1.5; }
    .input-panel { margin:.4rem 0 .8rem;padding:1rem 1.2rem;background:var(--white);border:1px solid var(--verm); }
    .input-panel h2 { margin:0 0 .35rem;font-size:1.12rem;letter-spacing:-.02em; }
    .input-panel > p { margin:0 0 .9rem;max-width:72ch;color:var(--ink);font-size:.9rem;line-height:1.5; }
    .input-request { display:grid;grid-template-columns:1.25fr 1fr;gap:1rem 1.4rem;border-top:1px solid var(--line);padding-top:.8rem; }
    .input-request div { min-width:0; }
    .input-request b { display:block;color:var(--muted);font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:.25rem; }
    .input-request span { display:block;font-size:.84rem;line-height:1.48;overflow-wrap:anywhere; }
    .input-warning { margin:.75rem 0 0!important;color:var(--verm)!important;font-size:.76rem!important;font-weight:620; }
    .operator-item { min-width:0;border-top:1px solid rgba(255,255,255,.2);padding-top:.55rem; }
    .operator-item b { display:block;color:var(--line);font-size:.65rem;letter-spacing:.09em;text-transform:uppercase;margin-bottom:.28rem; }
    .operator-item span { color:var(--white);font-size:.86rem;line-height:1.48;overflow-wrap:anywhere; }
    .operator-item.next { grid-column:1 / -1;border-color:var(--verm); }
    .operator-item.next b { color:var(--white); }
    .case-guide { border:1px solid var(--line);background:rgba(255,254,250,.55);padding:.75rem 1rem;margin-bottom:1rem; }
    .case-guide summary { cursor:pointer;font-weight:680;font-size:.82rem; }
    .case-guide p { color:var(--muted);font-size:.79rem;line-height:1.5;margin:.65rem 0 0;max-width:75ch; }
    .spine { position:relative;padding:.6rem 0 .5rem 3.4rem; }
    .spine:before { content:"";position:absolute;left:1.05rem;top:1.35rem;bottom:1.5rem;width:1px;background:var(--line); }
    .fold { position:relative;padding:1.1rem 1.2rem 1.15rem;margin:.65rem 0 1rem;background:rgba(255,254,250,.72);border:1px solid var(--line);clip-path:polygon(0 0,calc(100% - 18px) 0,100% 18px,100% 100%,0 100%); }
    .fold:after { content:"";position:absolute;right:0;top:0;border-style:solid;border-width:0 18px 18px 0;border-color:transparent var(--paper) var(--gold) transparent; }
    .fold-node { position:absolute;left:-3rem;top:1rem;width:28px;height:28px;display:grid;place-items:center;background:var(--paper);border:1px solid var(--ink);border-radius:50%;font:700 .68rem ui-monospace,SFMono-Regular,Consolas,monospace;z-index:2; }
    .fold.active .fold-node { color:#fff;background:var(--verm);border-color:var(--verm);animation:breathe 1.8s ease-in-out infinite; }
    .fold-title { display:flex;justify-content:space-between;gap:1rem;align-items:baseline;margin-bottom:.8rem; }
    .fold-title h2 { font-size:.94rem;letter-spacing:.02em;margin:0; }
    .fold-title span { font:600 .65rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted); }
    .evidence { display:grid;grid-template-columns:minmax(72px,90px) minmax(0,1fr);gap:.8rem;padding:.75rem 0;border-top:1px solid var(--line); }
    .evidence:first-of-type { border-top:0; }
    .evidence-kind { font:650 .66rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--verm);text-transform:uppercase;overflow-wrap:anywhere; }
    .evidence-copy { min-width:0;max-width:100%; }
    .evidence-preview { font-size:.84rem;line-height:1.48;overflow-wrap:anywhere;word-break:break-word; }
    .evidence-details { margin-top:.55rem;max-width:100%; }
    .evidence-details summary { cursor:pointer;color:var(--muted);font-size:.72rem;font-weight:650; }
    .evidence-raw { box-sizing:border-box;max-width:100%;max-height:22rem;overflow:auto;margin:.55rem 0 0;padding:.8rem;background:var(--ink);color:var(--white);font:500 .72rem/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:normal;overflow-wrap:anywhere;word-break:break-word; }
    .evidence-source { display:inline-block;margin-top:.45rem;color:var(--verm);font-size:.72rem;font-weight:650;text-underline-offset:2px; }
    .hypothesis { border-top:1px solid var(--line);padding:.85rem 0 0;margin-top:.7rem; }
    .hypothesis:first-of-type { border-top:0;margin-top:0;padding-top:0; }
    .hyp-row { display:flex;gap:1rem;justify-content:space-between;align-items:flex-start; }
    .hyp-row p { margin:0;font-size:.89rem;line-height:1.45;font-weight:560; }
    .confidence { flex:0 0 58px;text-align:right;font:700 .78rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--verm); }
    .meter { height:3px;background:var(--line);margin:.6rem 0 .45rem; }
    .meter i { display:block;height:100%;background:var(--verm); }
    .micro { color:var(--muted);font-size:.71rem;line-height:1.45; }
    .reflection { border-left:2px solid var(--gold);padding-left:1rem;line-height:1.5;font-size:.86rem; }
    .action-name { font-size:1.05rem;font-weight:680;margin-bottom:.45rem; }
    .action-grid { display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-top:1rem; }
    .datum { border-top:1px solid var(--line);padding-top:.55rem; }
    .datum b { display:block;font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:.25rem; }
    .datum span { font-size:.79rem;line-height:1.4;overflow-wrap:anywhere; }
    .empty { min-height:58vh;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:3rem; }
    .empty-shape { width:72px;height:72px;border:1px solid var(--line);transform:rotate(45deg);position:relative;margin-bottom:2rem; }
    .empty-shape:before,.empty-shape:after { content:"";position:absolute;background:var(--line); }
    .empty-shape:before { width:1px;height:100%;left:50%; }
    .empty-shape:after { height:1px;width:100%;top:50%; }
    .empty h2 { font-size:1.25rem;margin:.3rem; }
    .empty p { color:var(--muted);max-width:440px;font-size:.85rem;line-height:1.5; }
    .tech { margin-top:1.25rem;border-top:1px solid var(--line);padding-top:1rem; }
    div[data-testid="stButton"] button { border-radius:0;min-height:2.45rem;border:1px solid var(--ink);font-weight:650;background:transparent; }
    div[data-testid="stButton"] button:hover { border-color:var(--verm);color:var(--verm); }
    div[data-testid="stButton"] button:focus-visible,
    div[data-testid="stTextArea"] textarea:focus-visible,
    div[data-testid="stFileUploader"] button:focus-visible { outline:2px solid var(--verm);outline-offset:2px; }
    div[data-testid="stSegmentedControl"] { margin-bottom:.65rem; }
    div[data-testid="stSegmentedControl"] button { border-radius:0!important; }
    @keyframes breathe { 50% { box-shadow:0 0 0 7px rgba(201,71,53,.12); } }
    @media (prefers-reduced-motion:reduce) { * { animation:none!important;transition:none!important; } }
    @media (max-width:1100px) { div[data-testid="stHorizontalBlock"]{flex-direction:column} div[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important}.operator-grid{grid-template-columns:1fr}.operator-item.next{grid-column:auto} }
    @media (max-width:900px) { .block-container{padding:1rem}.brand-sub{display:none}.lang-switch a{min-width:42px;padding:.5rem}.spine{padding-left:2.8rem}.fold-node{left:-2.55rem}.action-grid,.input-request{grid-template-columns:1fr}.evidence{grid-template-columns:1fr;gap:.35rem}.evidence-kind{margin-top:.1rem} }
    </style>
    """


def _fmt_time(value: str | None, *, short: bool = False) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%H:%M" if short else "%d.%m.%Y · %H:%M UTC")
    except ValueError:
        return value


def _source_label(source: str) -> str:
    return {"github_actions": "GitHub Actions", "gitlab_ci": "GitLab CI", "alertmanager": "Prometheus"}.get(source, source)


def _visible_evidence(items: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in reversed(items):
        attributes = item.get("attributes") or {}
        kind = str(item.get("kind", "source"))
        identity = str(attributes.get("query_name") or item.get("summary", ""))
        key = (kind, identity)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return list(reversed(unique[:limit]))


def _evidence_label(item: dict[str, Any]) -> str:
    attributes = item.get("attributes") or {}
    return str(attributes.get("query_name") or item.get("kind", "source"))


def _evidence_summary(item: dict[str, Any]) -> str:
    summary = str(item.get("summary", ""))
    attributes = item.get("attributes") or {}
    query_name = attributes.get("query_name")
    if not query_name:
        return summary
    try:
        result = json.loads(summary).get("result", [])
        if not result:
            return f"{query_name}: no data"
        sample = result[0]
        value = float(sample["value"][1])
        labels = sample.get("metric") or {}
        context = " · ".join(
            f"{key}={value}" for key, value in labels.items() if key != "__name__"
        )
        rendered_value = f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{query_name.replace('_', ' ')} = {rendered_value}{' · ' + context if context else ''}"
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return summary


def _safe_evidence_text(value: str) -> str:
    return escape(value).replace("`", "&#96;")


def _evidence_html(item: dict[str, Any], t: dict[str, str]) -> str:
    summary = _evidence_summary(item)
    compact = " ".join(summary.split())
    preview = compact if len(compact) <= 260 else f"{compact[:257].rstrip()}…"
    needs_details = "\n" in summary or len(summary) > 260
    details = ""
    if needs_details:
        raw = _safe_evidence_text(summary).replace("\n", "<br>")
        details = (
            f'<details class="evidence-details"><summary>{escape(t["raw_evidence"])}</summary>'
            f'<div class="evidence-raw">{raw}</div></details>'
        )
    source_uri = str(item.get("source_uri", ""))
    source = ""
    if source_uri.startswith(("https://", "http://")):
        safe_uri = escape(source_uri, quote=True)
        source = (
            f'<a class="evidence-source" href="{safe_uri}" target="_blank" '
            f'rel="noopener noreferrer">{escape(t["source_link"])}</a>'
        )
    return (
        f'<div class="evidence"><div class="evidence-kind">'
        f'{escape(_evidence_label(item))}</div><div class="evidence-copy">'
        f'<div class="evidence-preview">{_safe_evidence_text(preview)}</div>'
        f'{details}{source}</div></div>'
    )


def _operator_guidance(
    record: dict[str, Any], t: dict[str, str]
) -> dict[str, str]:
    status = str(record.get("status", "queued"))
    state = record.get("state") or {}
    hypotheses = list(state.get("hypotheses") or [])
    leading = max(
        hypotheses,
        key=lambda item: float(item.get("confidence", 0)),
        default=None,
    )
    finding = (
        str(leading.get("statement", t["finding_pending"]))
        if leading
        else t["finding_pending"]
    )
    required_checks = list((leading or {}).get("required_checks") or [])
    result = state.get("action_result") or {}
    recovery_verified = state.get("recovery_verified") is True
    event = record.get("event") or {}
    kind = str(event.get("kind", ""))

    headline = t.get(f"{status}_headline", STATUS_LABELS["en"].get(status, status))
    if status in {"queued", "running"}:
        next_step = t["wait_step"]
        impact = t["no_changes"]
    elif status == "awaiting_input":
        next_step = t["input_step"]
        impact = t["input_impact"]
    elif status == "awaiting_approval":
        next_step = t["approval_step"]
        impact = t["approval_impact"]
    elif status == "escalated":
        if kind == "runtime_alert":
            next_step = t["runtime_escalation_step"]
        elif kind == "ci_failure":
            next_step = t["ci_escalation_step"]
        else:
            next_step = (
                str(required_checks[0]) if required_checks else t["escalation_step"]
            )
        impact = t["no_changes"]
    elif status == "failed":
        next_step = t["failed_step"]
        impact = t["no_changes"]
    elif status == "rejected":
        next_step = t["completed_step"]
        impact = t["no_changes"]
    elif recovery_verified:
        next_step = t["recovered_step"]
        impact = t["recovered_impact"]
    else:
        next_step = t["completed_step"]
        impact = t["draft_impact"] if result.get("external_reference") else t["completed_impact"]

    return {
        "headline": headline,
        "finding": finding,
        "next_step": next_step,
        "impact": impact,
    }


def _operator_summary_html(
    record: dict[str, Any], t: dict[str, str]
) -> str:
    event = record.get("event") or {}
    guidance = _operator_guidance(record, t)
    happened = (
        f'{event.get("title", "—")} · {event.get("service", "—")} · '
        f'{event.get("severity", "unknown")}'
    )
    return f"""<section class="operator-summary">
    <div class="section-label">{escape(t['operator_summary'])}</div>
    <h2>{escape(guidance['headline'])}</h2>
    <div class="operator-grid">
      <div class="operator-item"><b>{escape(t['what_happened'])}</b><span>{escape(happened)}</span></div>
      <div class="operator-item"><b>{escape(t['agent_found'])}</b><span>{escape(guidance['finding'])}</span></div>
      <div class="operator-item next"><b>{escape(t['your_next_step'])}</b><span>{escape(guidance['next_step'])}</span></div>
      <div class="operator-item"><b>{escape(t['impact'])}</b><span>{escape(guidance['impact'])}</span></div>
    </div></section>"""


def _humanize_error(error: str, t: dict[str, str]) -> tuple[str, bool]:
    if error == "budget:tool_call_budget_truncated":
        return t["budget_truncated"], True
    return error, error.startswith("budget:")


def _status_html(status: str, language: str) -> str:
    label = STATUS_LABELS[language].get(status, status)
    return f'<span class="state {escape(status)}"><b>{STATUS_SYMBOLS.get(status, "·")}</b>{escape(label)}</span>'


def _incident_card(record: dict[str, Any], selected: bool, language: str) -> str:
    event = record.get("event", {})
    selected_class = " selected" if selected else ""
    return f"""<div class="incident{selected_class}">
      <div class="incident-top"><span class="incident-source">{escape(_source_label(str(event.get('source',''))))}</span>
      <span class="incident-time">{escape(_fmt_time(record.get('updated_at'), short=True))}</span></div>
      <div class="incident-title">{escape(str(event.get('title','Untitled incident')))}</div>
      <div class="incident-meta">{_status_html(str(record.get('status','queued')), language)}<span>{escape(str(event.get('service','—')))}</span></div>
    </div>"""


def _fold(number: str, title: str, body: str, *, meta: str = "", active: bool = False) -> str:
    active_class = " active" if active else ""
    return f"""<section class="fold{active_class}"><div class="fold-node">{number}</div>
    <div class="fold-title"><h2>{escape(title)}</h2><span>{escape(meta)}</span></div>{body}</section>"""


def _render_input_request(
    record: dict[str, Any], t: dict[str, str]
) -> None:
    state = record.get("state") or {}
    request = state.get("information_request") or {}
    request_id = str(request.get("request_id", ""))
    question = str(request.get("question") or t["input_step"])
    reason = str(
        request.get("reason")
        or request.get("evidence_gap")
        or t["finding_pending"]
    )
    formats = ", ".join(
        str(item).upper()
        for item in request.get("accepted_input_types", [])
    ) or "TXT, LOG, JSON, YAML"
    warning = str(request.get("sensitive_data_warning") or t["input_warning"])
    st.markdown(
        f"""<section class="input-panel">
        <h2>{escape(t['input_title'])}</h2><p>{escape(t['input_copy'])}</p>
        <div class="input-request">
          <div><b>{escape(t['input_question'])}</b><span>{escape(question)}</span></div>
          <div><b>{escape(t['input_reason'])}</b><span>{escape(reason)}</span></div>
          <div><b>{escape(t['input_formats'])}</b><span>{escape(formats)}</span></div>
        </div><p class="input-warning">{escape(warning)}</p></section>""",
        unsafe_allow_html=True,
    )
    with st.form(f"evidence-{record['incident_id']}", clear_on_submit=False):
        evidence_text = st.text_area(
            t["input_text_label"],
            height=160,
            help=t["input_text_help"],
            placeholder=question,
        )
        evidence_file = st.file_uploader(
            t["input_file_label"],
            type=["txt", "log", "json", "yaml", "yml"],
            help=t["input_file_help"],
        )
        submit_col, decline_col = st.columns([1.7, 1])
        with submit_col:
            submitted = st.form_submit_button(
                t["input_submit"], type="primary", use_container_width=True
            )
        with decline_col:
            declined = st.form_submit_button(
                t["input_decline"], use_container_width=True
            )
    if submitted:
        if evidence_text.strip() and evidence_file is not None:
            st.error(t["input_one_source"])
        elif not evidence_text.strip() and evidence_file is None:
            st.error(t["input_required"])
        else:
            _submit_operator_evidence(
                record,
                request_id=request_id,
                text=evidence_text.strip(),
                uploaded_file=evidence_file,
                t=t,
            )
    elif declined:
        _decline_operator_request(record, t)


def _render_investigation(record: dict[str, Any], t: dict[str, str], language: str) -> None:
    event = record.get("event", {})
    state = record.get("state") or {}
    status = str(record.get("status", "queued"))
    st.markdown(
        f"""<header class="case-head">
        <div class="case-kicker"><span>{escape(_source_label(str(event.get('source',''))))}</span><span>·</span>
        <span class="severity">{escape(str(event.get('severity','unknown')).upper())}</span><span>·</span>{_status_html(status, language)}</div>
        <h1>{escape(str(event.get('title','Untitled incident')))}</h1>
        <div class="case-deck">{escape(str(event.get('service','—')))} · {t['received']} {_fmt_time(event.get('received_at'))}</div>
        </header>""",
        unsafe_allow_html=True,
    )

    evidence = state.get("evidence") or []
    hypotheses = state.get("hypotheses") or []
    reflection = state.get("reflection") or {}
    action = state.get("proposed_action") or {}
    result = state.get("action_result") or {}
    remediation = state.get("remediation_report") or {}

    st.markdown(_operator_summary_html(record, t), unsafe_allow_html=True)
    if status == "awaiting_input":
        _render_input_request(record, t)
    if status == "awaiting_approval":
        st.markdown(
            f'<section class="decision-panel"><h2>{escape(t["decision_title"])}</h2>'
            f'<p>{escape(t["decision_copy"])}</p></section>',
            unsafe_allow_html=True,
        )
        approve_col, reject_col, _ = st.columns([1.5, 1, 2.2])
        with approve_col:
            if st.button(t["approve"], type="primary", use_container_width=True):
                _submit_decision(record, True, t)
        with reject_col:
            if st.button(t["reject"], use_container_width=True):
                _submit_decision(record, False, t)
        st.caption(t["approval_note"])
    st.markdown(
        f"""<details class="case-guide"><summary>{escape(t['how_to_read'])}</summary>
        <p>{escape(t['guide_copy'])}</p></details>""",
        unsafe_allow_html=True,
    )

    signal_body = f"""<div class="action-name">{escape(str(event.get('title','')))}</div>
    <div class="micro">{escape(str(event.get('kind','')).replace('_',' '))} · {escape(str(event.get('external_id','—')))}</div>"""
    folds = [_fold("01", t["signal"], signal_body, meta=_source_label(str(event.get("source", ""))))]

    visible_evidence = _visible_evidence(evidence)
    evidence_body = "".join(
        _evidence_html(item, t) for item in visible_evidence
    ) or f'<p class="micro">{escape(t["no_incidents_hint"])}</p>'
    evidence_meta = f"{len(evidence)} {t['evidence_count']}"
    if len(visible_evidence) < len(evidence):
        evidence_meta = f"{t['evidence_shown']} {len(visible_evidence)} / {len(evidence)}"
    folds.append(_fold("02", t["evidence"], evidence_body, meta=evidence_meta, active=status == "running"))

    hypothesis_body = ""
    for item in hypotheses:
        confidence = round(float(item.get("confidence", 0)) * 100)
        checks = item.get("required_checks") or []
        check_text = f"{t['checks']}: " + " · ".join(map(str, checks)) if checks else ""
        verdict = t["verified"] if item.get("verified") else t["unverified"]
        hypothesis_body += f"""<div class="hypothesis"><div class="hyp-row"><p>{escape(str(item.get('statement','')))}</p>
        <span class="confidence">{confidence}%</span></div><div class="meter"><i style="width:{confidence}%"></i></div>
        <div class="micro">{escape(verdict)}{(' · ' + escape(check_text)) if check_text else ''}</div></div>"""
    if not hypothesis_body:
        hypothesis_body = '<p class="micro">—</p>'
    folds.append(_fold("03", t["hypotheses"], hypothesis_body, meta=f"{len(hypotheses)}"))

    reflection_body = f'<div class="reflection">{escape(str(reflection.get("critique", "—")))}</div>'
    folds.append(_fold("04", t["reflection"], reflection_body, meta=str(reflection.get("outcome", "pending")).replace("_", " ")))

    if action:
        remediation_body = ""
        if remediation:
            changed_files = ", ".join(
                escape(str(item.get("path", "")))
                for item in remediation.get("changes", [])
            )
            checks = " · ".join(
                f"{escape(' '.join(item.get('command', [])))}: {item.get('exit_code')}"
                for item in remediation.get("checks", [])
            )
            review = remediation.get("review") or {}
            remediation_body = f"""<div class="action-grid">
            <div class="datum"><b>{escape(t['changed_files'])}</b><span>{changed_files or '—'}</span></div>
            <div class="datum"><b>{escape(t['sandbox_checks'])}</b><span>{checks or '—'}</span></div>
            <div class="datum"><b>{escape(t['critic'])}</b><span>{escape(str(review.get('summary','—')))}</span></div></div>"""
        action_body = f"""<div class="action-name">{escape(str(action.get('description','')))}</div>
        <div class="micro">{escape(str(action.get('tool_name','')))}</div><div class="action-grid">
        <div class="datum"><b>{escape(t['risk'])}</b><span>{escape(str(action.get('risk','—')))}</span></div>
        <div class="datum"><b>{escape(t['expected'])}</b><span>{escape(str(action.get('expected_outcome','—')))}</span></div>
        <div class="datum"><b>{escape(t['rollback'])}</b><span>{escape(str(action.get('rollback_plan') or '—'))}</span></div></div>{remediation_body}"""
    else:
        action_body = '<p class="micro">—</p>'
    folds.append(_fold("05", t["action"], action_body, meta=str(action.get("risk", "pending")), active=status == "awaiting_approval"))

    if result:
        recovery = state.get("recovery_summary") or "—"
        result_body = (
            f'<div class="action-name">{escape(str(result.get("summary", "")))}</div>'
            f'<div class="datum"><b>{escape(t["recovery_check"])}</b>'
            f'<span>{escape(str(recovery))}</span></div>'
        )
        folds.append(_fold("06", t["result"], result_body, meta="success" if result.get("success") else "failed"))

    st.markdown(f'<main class="spine">{"".join(folds)}</main>', unsafe_allow_html=True)

def _submit_decision(record: dict[str, Any], approved: bool, t: dict[str, str]) -> None:
    client: IncidentAPIClient = st.session_state.api_client
    try:
        if approved:
            with st.spinner(t["verification_running"]):
                client.decide_approval(str(record["incident_id"]), approved=True)
        else:
            client.decide_approval(str(record["incident_id"]), approved=False)
        st.toast(
            t["approved"] if approved else t["rejected"],
            icon="✅" if approved else "❌",
        )
        st.rerun()
    except DashboardAPIError as error:
        st.error(str(error))


def _submit_operator_evidence(
    record: dict[str, Any],
    *,
    request_id: str,
    text: str,
    uploaded_file: Any,
    t: dict[str, str],
) -> None:
    client: IncidentAPIClient = st.session_state.api_client
    try:
        with st.spinner(t["input_running"]):
            if uploaded_file is not None:
                client.submit_file_evidence(
                    str(record["incident_id"]),
                    request_id=request_id,
                    filename=str(uploaded_file.name),
                    content=uploaded_file.getvalue(),
                    media_type=uploaded_file.type,
                )
            else:
                client.submit_text_evidence(
                    str(record["incident_id"]),
                    request_id=request_id,
                    text=text,
                )
        st.toast(t["input_sent"], icon="✅")
        st.rerun()
    except DashboardAPIError as error:
        st.error(str(error))


def _decline_operator_request(
    record: dict[str, Any], t: dict[str, str]
) -> None:
    client: IncidentAPIClient = st.session_state.api_client
    try:
        client.decline_information_request(str(record["incident_id"]))
        st.toast(t["input_declined"], icon="↗️")
        st.rerun()
    except DashboardAPIError as error:
        st.error(str(error))


def main() -> None:
    st.set_page_config(page_title="Incident Investigator", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(_css(), unsafe_allow_html=True)
    if "api_client" not in st.session_state:
        st.session_state.api_client = IncidentAPIClient.from_environment()

    language = str(st.query_params.get("lang", "ru")).lower()
    if language not in TEXT:
        language = "ru"
    t = TEXT[language]
    ru_class = "current" if language == "ru" else ""
    en_class = "current" if language == "en" else ""
    st.markdown(
        f"""<div class="topbar"><div class="brand"><div class="brand-mark"></div><div><div class="eyebrow">{t['eyebrow']}</div>
        <div class="brand-title">{t['app']}</div><div class="brand-sub">{t['subtitle']}</div></div></div>
        <nav class="lang-switch" aria-label="Language / Язык"><a class="{ru_class}" href="/?lang=ru" target="_self">RU</a><a class="{en_class}" href="/?lang=en" target="_self">EN</a></nav></div>""",
        unsafe_allow_html=True,
    )

    client: IncidentAPIClient = st.session_state.api_client
    if not client.configured:
        st.error(t["api_missing"])
        st.caption(t["retry"])
        return

    try:
        incidents = client.list_incidents()
        online = True
    except DashboardAPIError as error:
        incidents = []
        online = False
        st.error(str(error))

    queue_col, main_col, detail_col = st.columns([1.05, 2.65, .95], gap="large")
    with queue_col:
        state_class = "" if online else " offline"
        st.markdown(f'<div class="connection{state_class}"><i></i>{t["connected"] if online else t["offline"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="section-label">{t["queue"]} · {len(incidents):02d}</div>', unsafe_allow_html=True)
        filter_value = st.selectbox(
            t["filter"],
            [t["all"], t["active"], t["approval"], t["resolved"]],
            label_visibility="collapsed",
        )
        groups = {
            t["active"]: {"queued", "running", "escalated"},
            t["approval"]: {"awaiting_input", "awaiting_approval"},
            t["resolved"]: {"completed", "rejected", "failed"},
        }
        visible = [item for item in incidents if filter_value == t["all"] or item.get("status") in groups.get(filter_value, set())]
        selected_id = st.session_state.get("selected_incident")
        for record in visible:
            incident_id = str(record["incident_id"])
            st.markdown(_incident_card(record, incident_id == selected_id, language), unsafe_allow_html=True)
            if st.button(t["open"], key=f"open-{incident_id}", help=record.get("event", {}).get("title", ""), use_container_width=True):
                st.session_state.selected_incident = incident_id
                st.rerun()
        if not visible:
            st.markdown(f'<div class="empty" style="min-height:20rem"><div class="empty-shape"></div><h2>{t["no_incidents"]}</h2><p>{t["no_incidents_hint"]}</p></div>', unsafe_allow_html=True)
        if st.button(f"↻  {t['refresh']}", use_container_width=True):
            st.rerun()

    selected = next((item for item in incidents if str(item["incident_id"]) == st.session_state.get("selected_incident")), None)
    if selected is None and incidents:
        selected = incidents[0]
        st.session_state.selected_incident = str(selected["incident_id"])

    with main_col:
        if selected:
            with suppress(DashboardAPIError):
                selected = client.get_incident(str(selected["incident_id"]))
            _render_investigation(selected, t, language)
        else:
            st.markdown(f'<div class="empty"><div class="empty-shape"></div><h2>{t["select"]}</h2><p>{t["select_hint"]}</p></div>', unsafe_allow_html=True)

    with detail_col:
        if selected:
            event = selected.get("event", {})
            st.markdown(f'<div class="section-label">{t["details"]}</div>', unsafe_allow_html=True)
            details = [(t["source"], _source_label(str(event.get("source", "—")))), (t["service"], str(event.get("service", "—"))),
                       (t["severity"], str(event.get("severity", "—"))), (t["status"], STATUS_LABELS[language].get(str(selected.get("status")), str(selected.get("status")))),
                       (t["updated"], _fmt_time(selected.get("updated_at"))), (t["correlation"], str(selected.get("correlation_id", "—")))]
            for label, value in details:
                st.markdown(f'<div class="datum"><b>{escape(label)}</b><span>{escape(value)}</span></div>', unsafe_allow_html=True)
            errors = list((selected.get("state") or {}).get("errors") or [])
            if selected.get("error"):
                errors.append(selected["error"])
            if errors:
                rendered_errors = [_humanize_error(str(error), t) for error in errors]
                only_notes = all(is_note for _, is_note in rendered_errors)
                heading = t["notes"] if only_notes else t["errors"]
                st.markdown(f'<div class="section-label">{heading}</div>', unsafe_allow_html=True)
                for message, is_note in rendered_errors:
                    if is_note:
                        st.warning(message)
                    else:
                        st.error(message)


if __name__ == "__main__":
    main()
