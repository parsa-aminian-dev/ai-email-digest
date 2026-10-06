from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

from src.digest.config.settings import RulesConfig, Settings
from src.digest.models import PRIORITY_ORDER, Action, DigestEntry, DigestResult, ProcessedEmail
from src.digest.preprocessing.redact import safe_text

WORDS = {
    "en": {
        "title": "Your daily email digest",
        "health": "Processing health",
        "action": "Action",
        "due": "Due",
        "grouped": "Grouped messages",
        "degraded": "Degraded processing: review your inbox for missed or unresolved items.",
    },
    "de": {
        "title": "Deine tägliche E-Mail-Übersicht",
        "health": "Verarbeitungsstatus",
        "action": "Aktion",
        "due": "Frist",
        "grouped": "Zusammengefasste Nachrichten",
        "degraded": "Eingeschränkte Verarbeitung: Bitte prüfe dein Postfach auf fehlende oder ungeklärte Nachrichten.",
    },
}

HEALTH_LABELS = {
    "en": {
        "processed": "Messages included",
        "high_priority": "High priority",
        "actions": "Actions to review",
        "needs_review": "Unresolved messages",
        "failures": "Processing failures",
        "provider_failures": "Mailbox retrieval failures",
        "llm_fallbacks": "AI analyses using a fallback",
        "overview_fallback": "AI overview unavailable",
        "llm_used": "Messages analyzed with AI",
        "llm_calls": "AI requests",
        "llm_tokens": "AI tokens used",
    },
    "de": {
        "processed": "Enthaltene Nachrichten",
        "high_priority": "Hohe Priorität",
        "actions": "Aktionen zur Prüfung",
        "needs_review": "Ungeklärte Nachrichten",
        "failures": "Verarbeitungsfehler",
        "provider_failures": "Fehler beim Postfachabruf",
        "llm_fallbacks": "KI-Analysen mit Regelergebnis",
        "overview_fallback": "KI-Überblick nicht verfügbar",
        "llm_used": "Mit KI analysierte Nachrichten",
        "llm_calls": "KI-Anfragen",
        "llm_tokens": "Verwendete KI-Token",
    },
}


class DigestBuilder:
    def __init__(self, config: RulesConfig | None = None) -> None:
        self.config = config or Settings().rules

    def build(
        self, processed: list[ProcessedEmail], health: dict[str, Any] | None = None
    ) -> DigestResult:
        groups: dict[tuple[str, str], DigestEntry] = {}
        remaining = self.config.digest.max_items
        ordered = sorted(
            processed,
            key=lambda item: (
                PRIORITY_ORDER[item.priority],
                item.category,
                item.received_at,
                item.id,
            ),
        )
        for item in ordered:
            key = (item.priority, item.category)
            group = groups.setdefault(
                key, DigestEntry(category=item.category, priority=item.priority)
            )
            group.count += 1
            relevant = (
                PRIORITY_ORDER[item.priority]
                <= PRIORITY_ORDER[self.config.digest.summary_threshold]
                or item.action_type != Action.none
            )
            if relevant and remaining > 0:
                group.items.append(item)
                remaining -= 1
        stats = {key: value for key, value in (health or {}).items() if key in HEALTH_LABELS["en"]}
        stats.update(
            processed=len(processed),
            high_priority=sum(item.priority in {"URGENT", "HIGH"} for item in processed),
            actions=sum(item.action_type != Action.none for item in processed),
            llm_used=sum(item.llm_used for item in processed),
            needs_review=sum(item.status == "needs_review" for item in processed),
        )
        stats.setdefault("failures", 0)
        stats.setdefault("provider_failures", 0)
        stats["llm_fallbacks"] = max(
            stats.get("llm_fallbacks", 0), sum(item.llm_fallback for item in processed)
        )
        if self.config.digest.language == "de":
            summary = f"{len(processed)} Nachrichten, {stats['high_priority']} mit hoher Priorität und {stats['actions']} mit einer Aktion."
        else:
            summary = f"{len(processed)} messages, {stats['high_priority']} high priority and {stats['actions']} requiring action."
        result = DigestResult(
            generated_at=datetime.now(UTC),
            entries=list(groups.values()),
            overall_summary=summary,
            health=stats,
        )
        return self.render(result)

    def render(self, result: DigestResult) -> DigestResult:
        words = WORDS[self.config.digest.language]
        result.overall_summary = safe_text(result.overall_summary)
        lines = [words["title"], result.overall_summary, ""]
        html = [
            '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
            "<title>Email digest</title><style>body{font-family:system-ui,sans-serif;color:#17263c;background:#f3f5f8;margin:0;padding:24px}main{max-width:760px;margin:auto;background:white;border-radius:12px;padding:28px}h1{font-size:26px}h2{font-size:18px;border-bottom:1px solid #dce2eb;padding-bottom:8px}li{margin:16px 0}.muted{color:#52647c}.health{background:#edf2f7;padding:16px;border-radius:8px}</style></head><body><main>",
            f"<h1>{escape(words['title'])}</h1><p>{escape(result.overall_summary)}</p>",
        ]
        if result.interval_start and result.interval_end:
            from zoneinfo import ZoneInfo

            zone = ZoneInfo(self.config.digest.timezone)
            period = f"{result.interval_start.astimezone(zone):%Y-%m-%d %H:%M %Z} — {result.interval_end.astimezone(zone):%Y-%m-%d %H:%M %Z}"
            lines.append(period)
            html.append(f'<p class="muted">{escape(period)}</p>')
        for group in result.entries:
            heading = f"{group.priority} · {safe_text(group.category)} ({group.count})"
            lines.append(heading)
            html.append(f"<h2>{escape(heading)}</h2><ul>")
            for item in group.items:
                subject, domain, summary = (
                    safe_text(item.subject, 300),
                    safe_text(item.sender_domain, 200),
                    safe_text(item.summary),
                )
                lines.extend([f"- {subject} · {domain}", f"  {summary}"])
                html.append(
                    f'<li><strong>{escape(subject)}</strong> <span class="muted">{escape(domain)}</span><br>{escape(summary)}'
                )
                if item.action_type != Action.none:
                    action = f"{words['action']}: {item.action_type}"
                    if item.deadline:
                        action += f" · {words['due']}: {safe_text(item.deadline, 80)}"
                    lines.append(f"  {action}")
                    html.append(f"<br><strong>{escape(action)}</strong>")
                html.append("</li>")
            html.append("</ul>")
            grouped = group.count - len(group.items)
            if grouped:
                text = f"{words['grouped']}: {grouped}"
                lines.append(text)
                html.append(f'<p class="muted">{escape(text)}</p>')
            lines.append("")
        lines.append(words["health"])
        html.append(f'<section class="health"><h2>{escape(words["health"])}</h2>')
        for key, value in sorted(result.health.items()):
            label = HEALTH_LABELS[self.config.digest.language].get(key, key)
            line = f"{label}: {value}"
            lines.append(line)
            html.append(f"<p>{escape(line)}</p>")
        if any(
            result.health.get(key, 0)
            for key in (
                "failures",
                "provider_failures",
                "llm_fallbacks",
                "needs_review",
                "overview_fallback",
            )
        ):
            lines.append(words["degraded"])
            html.append(f"<strong>{escape(words['degraded'])}</strong>")
        html.append("</section></main></body></html>")
        result.text = "\n".join(lines)
        result.html = "".join(html)
        return result
