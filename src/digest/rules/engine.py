from __future__ import annotations

import re
from email.utils import parseaddr
from fnmatch import fnmatchcase

from src.digest.config.settings import RulesConfig, Settings
from src.digest.models import Action, EmailMessage, Priority, RuleDecision

ACTION_PATTERNS = {
    Action.pay: r"\b(please pay|payment due|invoice.*due|bitte zahlen|bitte bezahlen)\b",
    Action.confirm: r"\b(please confirm|confirm your|bitte bestätigen)\b",
    Action.reply: r"\b(please reply|please respond|reply by|bitte antworten)\b",
    Action.attend: r"\b(please attend|join the meeting|invited to|teilnehmen)\b",
    Action.submit: r"\b(please submit|submit by|send the proposal|einreichen)\b",
    Action.change: r"\b(change your|update your|bitte ändern)\b",
    Action.contact: r"\b(please contact|call us|kontaktieren)\b",
}


def extract_action(text: str) -> tuple[Action, str | None]:
    action = next(
        (a for a, pattern in ACTION_PATTERNS.items() if re.search(pattern, text, re.I)), Action.none
    )
    date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    deadline = date.group() if action != Action.none and date else None
    return action, deadline


def evaluate_rule_engine(email: EmailMessage, config: RulesConfig | None = None) -> RuleDecision:
    config = config or Settings().rules
    text = f"{email.subject} {email.body}"
    action, deadline = extract_action(text)
    labels = {label.upper() for label in email.labels}
    for rule in config.rules:
        when = rule.when
        matches = (
            (
                not when.sender
                or fnmatchcase(parseaddr(email.sender)[1].lower(), when.sender.lower())
            )
            and (
                not when.sender_domain
                or fnmatchcase(email.sender_domain, when.sender_domain.lower())
            )
            and (not when.subject_pattern or re.search(when.subject_pattern, email.subject, re.I))
            and (
                not when.body_contains
                or any(k.lower() in email.body.lower() for k in when.body_contains)
            )
            and (not when.labels or set(s.upper() for s in when.labels).issubset(labels))
            and (
                when.list_unsubscribe is None
                or bool(email.metadata.get("list_unsubscribe")) == when.list_unsubscribe
            )
        )
        if matches:
            return RuleDecision(
                category=rule.category,
                priority=rule.priority,
                confidence=rule.confidence,
                action_type=rule.action_type if rule.action_type != Action.none else action,
                deadline=deadline,
                locked=True,
                llm_required=rule.analyze,
            )
    for category in config.categories:
        if any(keyword.lower() in text.lower() for keyword in category.keywords):
            return RuleDecision(
                category=category.name,
                priority=category.priority,
                confidence=0.9,
                action_type=action,
                deadline=deadline,
            )
    if email.metadata.get("list_unsubscribe") and "newsletters" in {
        c.name for c in config.categories
    }:
        return RuleDecision(category="newsletters", priority=Priority.LOW, confidence=0.9)
    general = next(category for category in config.categories if category.name == "general")
    priority = (
        Priority.HIGH if re.search(r"\b(urgent|asap|dringend)\b", text, re.I) else general.priority
    )
    return RuleDecision(
        category="general",
        priority=priority,
        confidence=0.4,
        action_type=action,
        deadline=deadline,
        resolved_by_rules=False,
        llm_required=True,
    )
