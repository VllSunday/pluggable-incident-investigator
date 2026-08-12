from __future__ import annotations

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
        "all": "Все",
        "active": "Активные",
        "approval": "Ждут решения",
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
        "language": "Язык",
    },
    "en": {
        "app": "Incident Investigator",
        "eyebrow": "OPERATIONS CONTROL",
        "subtitle": "Evidence-led incident investigations",
        "queue": "Incident queue",
        "all": "All",
        "active": "Active",
        "approval": "Needs decision",
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
        "language": "Language",
    },
}

STATUS_LABELS = {
    "ru": {
        "queued": "В очереди", "running": "Расследуется", "awaiting_approval": "Нужно решение",
        "completed": "Завершён", "escalated": "Эскалация", "rejected": "Отклонён", "failed": "Ошибка",
    },
    "en": {
        "queued": "Queued", "running": "Investigating", "awaiting_approval": "Needs decision",
        "completed": "Completed", "escalated": "Escalated", "rejected": "Rejected", "failed": "Failed",
    },
}

STATUS_SYMBOLS = {
    "queued": "○", "running": "◌", "awaiting_approval": "!", "completed": "✓",
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
    header[data-testid="stHeader"] { background:transparent; }
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
    .state.awaiting_approval { color:var(--verm);font-weight:700; }
    .state.completed { color:var(--ok); }
    .state.failed,.state.rejected { color:var(--verm); }
    .case-head { padding:1.1rem 0 1.4rem;border-bottom:1px solid var(--line);margin-bottom:.25rem; }
    .case-kicker { display:flex;gap:.6rem;align-items:center;font:650 .68rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted);text-transform:uppercase; }
    .severity { color:var(--verm); }
    .case-head h1 { font-size:clamp(1.7rem,3vw,2.75rem);line-height:1.03;letter-spacing:-.045em;margin:.65rem 0 .55rem;max-width:850px; }
    .case-deck { color:var(--muted);font-size:.9rem; }
    .spine { position:relative;padding:.6rem 0 .5rem 3.4rem; }
    .spine:before { content:"";position:absolute;left:1.05rem;top:1.35rem;bottom:1.5rem;width:1px;background:var(--line); }
    .fold { position:relative;padding:1.1rem 1.2rem 1.15rem;margin:.65rem 0 1rem;background:rgba(255,254,250,.72);border:1px solid var(--line);clip-path:polygon(0 0,calc(100% - 18px) 0,100% 18px,100% 100%,0 100%); }
    .fold:after { content:"";position:absolute;right:0;top:0;border-style:solid;border-width:0 18px 18px 0;border-color:transparent var(--paper) var(--gold) transparent; }
    .fold-node { position:absolute;left:-3rem;top:1rem;width:28px;height:28px;display:grid;place-items:center;background:var(--paper);border:1px solid var(--ink);border-radius:50%;font:700 .68rem ui-monospace,SFMono-Regular,Consolas,monospace;z-index:2; }
    .fold.active .fold-node { color:#fff;background:var(--verm);border-color:var(--verm);animation:breathe 1.8s ease-in-out infinite; }
    .fold-title { display:flex;justify-content:space-between;gap:1rem;align-items:baseline;margin-bottom:.8rem; }
    .fold-title h2 { font-size:.94rem;letter-spacing:.02em;margin:0; }
    .fold-title span { font:600 .65rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted); }
    .evidence { display:grid;grid-template-columns:90px 1fr;gap:.8rem;padding:.75rem 0;border-top:1px solid var(--line); }
    .evidence:first-of-type { border-top:0; }
    .evidence-kind { font:650 .66rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--verm);text-transform:uppercase;overflow-wrap:anywhere; }
    .evidence p { margin:0;font-size:.84rem;line-height:1.48; }
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
    .datum span { font-size:.79rem;line-height:1.4; }
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
    div[data-testid="stSegmentedControl"] { margin-bottom:.65rem; }
    div[data-testid="stSegmentedControl"] button { border-radius:0!important; }
    @keyframes breathe { 50% { box-shadow:0 0 0 7px rgba(201,71,53,.12); } }
    @media (prefers-reduced-motion:reduce) { * { animation:none!important;transition:none!important; } }
    @media (max-width:900px) { .block-container{padding:1rem}.brand-sub{display:none}.lang-switch a{min-width:42px;padding:.5rem}.spine{padding-left:2.8rem}.fold-node{left:-2.55rem}.action-grid{grid-template-columns:1fr} }
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

    signal_body = f"""<div class="action-name">{escape(str(event.get('title','')))}</div>
    <div class="micro">{escape(str(event.get('kind','')).replace('_',' '))} · {escape(str(event.get('external_id','—')))}</div>"""
    folds = [_fold("01", t["signal"], signal_body, meta=_source_label(str(event.get("source", ""))))]

    evidence_body = "".join(
        f"""<div class="evidence"><div class="evidence-kind">{escape(str(item.get('kind','source')))}</div>
        <p>{escape(str(item.get('summary','')))}</p></div>""" for item in evidence
    ) or f'<p class="micro">{escape(t["no_incidents_hint"])}</p>'
    folds.append(_fold("02", t["evidence"], evidence_body, meta=f"{len(evidence)} {t['evidence_count']}", active=status == "running"))

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
        result_body = f'<div class="action-name">{escape(str(result.get("summary", "")))}</div>'
        folds.append(_fold("06", t["result"], result_body, meta="success" if result.get("success") else "failed"))

    st.markdown(f'<main class="spine">{"".join(folds)}</main>', unsafe_allow_html=True)

    if status == "awaiting_approval":
        st.caption(t["approval_note"])
        approve_col, reject_col, _ = st.columns([1.3, 1, 2.5])
        with approve_col:
            if st.button(t["approve"], type="primary", use_container_width=True):
                _submit_decision(record, True, t)
        with reject_col:
            if st.button(t["reject"], use_container_width=True):
                _submit_decision(record, False, t)


def _submit_decision(record: dict[str, Any], approved: bool, t: dict[str, str]) -> None:
    client: IncidentAPIClient = st.session_state.api_client
    try:
        client.decide_approval(str(record["incident_id"]), approved=approved)
        st.toast(t["approved"] if approved else t["rejected"], icon="✓" if approved else "×")
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
        <nav class="lang-switch" aria-label="Language / Язык"><a class="{ru_class}" href="?lang=ru">RU</a><a class="{en_class}" href="?lang=en">EN</a></nav></div>""",
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
            "Filter",
            [t["all"], t["active"], t["approval"], t["resolved"]],
            label_visibility="collapsed",
        )
        groups = {
            t["active"]: {"queued", "running", "escalated"},
            t["approval"]: {"awaiting_approval"},
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
            errors = (selected.get("state") or {}).get("errors") or []
            if selected.get("error"):
                errors.append(selected["error"])
            if errors:
                st.markdown(f'<div class="section-label">{t["errors"]}</div>', unsafe_allow_html=True)
                for error in errors:
                    st.error(str(error))


if __name__ == "__main__":
    main()
