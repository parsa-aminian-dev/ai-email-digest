from __future__ import annotations

import re
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def normalize_email_text(text: str, max_chars: int = 4000) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parser = TextExtractor()
    parser.feed(text)
    lines = "".join(parser.parts).splitlines()
    cleaned = []
    for line in lines:
        if re.match(
            r"^(On .+wrote:|Am .+schrieb.+:|[- ]*Original Message[- ]*|--\s*$|"
            r"(?:Best regards|Kind regards|Regards|Mit freundlichen Grüßen|Viele Grüße)[,.]?\s*$|"
            r"Sent from my (?:iPhone|Android))",
            line,
            re.IGNORECASE,
        ):
            break
        if not line.lstrip().startswith(">"):
            cleaned.append(line)
    return re.sub(r"\s+", " ", " ".join(cleaned)).strip()[:max_chars]


def redact_sensitive_text(text: str) -> str:
    patterns = [
        (
            r"\b(?:token|access[_-]?token|refresh[_-]?token|secret|client[_-]?secret|password|api[_-]?key|authorization)\s*[:=]\s*(?:Bearer\s+)?[^\s]+",
            "[SECRET]",
        ),
        (r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*", "[SECRET]"),
        (r"\b(?:sk|ghp|github_pat)[_-][A-Za-z0-9_-]{10,}\b", "[SECRET]"),
        (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[SECRET]"),
        (r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", "[IBAN]"),
        (r"\b(?:\d[ -]?){13,19}\b", "[CARD_NUMBER]"),
        (r"(?<!\w)\+?\d[\d(). -]{6,}\d(?!\w)", "[PHONE_OR_NUMBER]"),
        (r"\b\d{6,}\b", "[NUMBER]"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]"),
        (r"(?:https?://|www\.)[^\s<>]+", "[LINK]"),
    ]
    for pattern, replacement in patterns:

        def replace(match: re.Match[str], replacement: str = replacement) -> str:
            if replacement == "[PHONE_OR_NUMBER]" and re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", match.group()
            ):
                return match.group()
            return replacement

        text = re.sub(pattern, replace, text, flags=re.IGNORECASE)
    return text


def safe_text(text: str, max_chars: int = 500) -> str:
    return redact_sensitive_text(normalize_email_text(text, max_chars * 4))[:max_chars]
