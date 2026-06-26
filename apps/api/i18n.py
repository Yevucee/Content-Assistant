"""Lightweight i18n helpers for server-rendered pages.

Minimal, dependency-free dictionary translations. Currently scoped to the
landing/index page; extend ``TRANSLATIONS`` as more pages are localised.

Language is negotiated in this order: explicit ``?lang=`` query param →
``lang`` cookie → ``Accept-Language`` header → ``DEFAULT_LANGUAGE``.
"""

from __future__ import annotations

from starlette.requests import Request

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "de", "pt")

LANGUAGE_NAMES = {
    "en": "English",
    "de": "Deutsch",
    "pt": "Português",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "index_lead": (
            "Plan and draft multi-channel content for your brands, with human "
            "review before anything ships."
        ),
        "index_go_dashboard": "Go to dashboard",
        "index_create_run": "Create a new run",
        "index_also_available": "Also available",
        "index_review_queue": "Review queue",
        "index_review_queue_desc": "approve runs, export WordPress drafts",
        "index_api_docs": "API documentation",
        "index_api_docs_desc": "integrations and automation",
        "index_public_url": "Public URL:",
        "language_label": "Language",
    },
    "de": {
        "index_lead": (
            "Planen und entwerfen Sie Multichannel-Inhalte für Ihre Marken – "
            "mit menschlicher Prüfung, bevor etwas veröffentlicht wird."
        ),
        "index_go_dashboard": "Zum Dashboard",
        "index_create_run": "Neuen Lauf erstellen",
        "index_also_available": "Ebenfalls verfügbar",
        "index_review_queue": "Prüfungswarteschlange",
        "index_review_queue_desc": "Läufe freigeben, WordPress-Entwürfe exportieren",
        "index_api_docs": "API-Dokumentation",
        "index_api_docs_desc": "Integrationen und Automatisierung",
        "index_public_url": "Öffentliche URL:",
        "language_label": "Sprache",
    },
    "pt": {
        "index_lead": (
            "Planeje e redija conteúdo multicanal para as suas marcas, com "
            "revisão humana antes de qualquer publicação."
        ),
        "index_go_dashboard": "Ir para o painel",
        "index_create_run": "Criar uma nova execução",
        "index_also_available": "Também disponível",
        "index_review_queue": "Fila de revisão",
        "index_review_queue_desc": "aprovar execuções, exportar rascunhos do WordPress",
        "index_api_docs": "Documentação da API",
        "index_api_docs_desc": "integrações e automação",
        "index_public_url": "URL pública:",
        "language_label": "Idioma",
    },
}


def _normalise(code: str | None) -> str | None:
    """Reduce a raw language tag (e.g. ``pt-BR``) to a supported base code."""
    if not code:
        return None
    base = code.strip().lower().split("-")[0]
    return base if base in SUPPORTED_LANGUAGES else None


def negotiate_language(request: Request) -> str:
    """Pick the best supported language for this request."""
    query = _normalise(request.query_params.get("lang"))
    if query:
        return query

    cookie = _normalise(request.cookies.get("lang"))
    if cookie:
        return cookie

    header = request.headers.get("accept-language", "")
    for part in header.split(","):
        candidate = _normalise(part.split(";")[0])
        if candidate:
            return candidate

    return DEFAULT_LANGUAGE


def get_translations(lang: str) -> dict[str, str]:
    """Return the translation table for ``lang`` (falls back to default)."""
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANGUAGE])


def language_options() -> list[tuple[str, str]]:
    """Return ``(code, display_name)`` pairs for the language switcher."""
    return [(code, LANGUAGE_NAMES[code]) for code in SUPPORTED_LANGUAGES]
