from __future__ import annotations

from typing import Callable, Dict, Optional

LEGACY_ORDER_STATUS_MAP = {
    "neu": "new",
    "in_bearbeitung": "in_progress",
    "abgeschlossen": "completed",
}

ORDER_STATUS_DEFS = [
    {"key": "new", "label": "New", "style": "bg-primary"},
    {"key": "in_progress", "label": "In progress", "style": "bg-info"},
    {"key": "on_hold", "label": "On hold", "style": "bg-warning text-dark"},
    {"key": "completed", "label": "Completed", "style": "bg-success"},
    {"key": "cancelled", "label": "Cancelled", "style": "bg-secondary"},
]

PRINT_JOB_STATUS_DEFS = [
    {"key": "upload", "label": "print_job_status_upload", "style": "bg-secondary", "label_is_key": True},
    {
        "key": "preparation",
        "label": "print_job_status_preparation",
        "style": "bg-info text-dark",
        "label_is_key": True,
    },
    {"key": "started", "label": "print_job_status_started", "style": "bg-primary", "label_is_key": True},
    {"key": "error", "label": "print_job_status_error", "style": "bg-danger", "label_is_key": True},
    {"key": "finished", "label": "print_job_status_finished", "style": "bg-success", "label_is_key": True},
    {"key": "cancelled", "label": "print_job_status_cancelled", "style": "bg-secondary", "label_is_key": True},
]

STATUS_GROUP_DEFS = {
    "order": ORDER_STATUS_DEFS,
    "print_job": PRINT_JOB_STATUS_DEFS,
}

STATUS_STYLE_OPTIONS = [
    ("bg-primary", "status_style_primary"),
    ("bg-secondary", "status_style_secondary"),
    ("bg-success", "status_style_success"),
    ("bg-danger", "status_style_danger"),
    ("bg-warning text-dark", "status_style_warning"),
    ("bg-info text-dark", "status_style_info"),
    ("bg-light text-dark", "status_style_light"),
    ("bg-dark", "status_style_dark"),
]


def default_label(def_item: Dict[str, str], translator: Optional[Callable[[str], str]] = None) -> str:
    label = str(def_item.get("label", "") or "")
    if def_item.get("label_is_key") and translator:
        return translator(label)
    return label


def normalize_status_messages(raw) -> Dict[str, Dict[str, Dict[str, str]]]:
    if not isinstance(raw, dict):
        return {}

    normalized: Dict[str, Dict[str, Dict[str, str]]] = {}
    for group_key, statuses in raw.items():
        if not isinstance(statuses, dict):
            continue
        group: Dict[str, Dict[str, str]] = {}
        for status_key, entry in statuses.items():
            if not isinstance(entry, dict):
                continue
            label = (entry.get("label") or "").strip()
            style = (entry.get("style") or "").strip()
            if label or style:
                group[str(status_key)] = {"label": label, "style": style}
        if group:
            normalized[str(group_key)] = group
    return normalized


def filter_status_messages(raw) -> Dict[str, Dict[str, Dict[str, str]]]:
    normalized = normalize_status_messages(raw)
    filtered: Dict[str, Dict[str, Dict[str, str]]] = {}
    for group_key, defs in STATUS_GROUP_DEFS.items():
        allowed = {item["key"] for item in defs}
        group = normalized.get(group_key)
        if not group:
            continue
        cleaned: Dict[str, Dict[str, str]] = {}
        for status_key, entry in group.items():
            if status_key not in allowed:
                continue
            label = (entry.get("label") or "").strip()
            style = (entry.get("style") or "").strip()
            if label or style:
                cleaned[status_key] = {"label": label, "style": style}
        if cleaned:
            filtered[group_key] = cleaned
    return filtered


def resolve_status_messages(
    settings: Dict[str, object],
    translator: Optional[Callable[[str], str]] = None,
) -> Dict[str, list[Dict[str, str]]]:
    raw = settings.get("status_messages") if isinstance(settings, dict) else None
    overrides = normalize_status_messages(raw)
    resolved: Dict[str, list[Dict[str, str]]] = {}
    for group_key, defs in STATUS_GROUP_DEFS.items():
        group_overrides = overrides.get(group_key, {})
        items = []
        for item in defs:
            key = item["key"]
            override = group_overrides.get(key, {})
            label = (override.get("label") or "").strip()
            style = (override.get("style") or "").strip()
            if not label:
                label = default_label(item, translator)
            if not style:
                style = item.get("style", "")
            items.append({"key": key, "label": label, "style": style})
        resolved[group_key] = items
    return resolved


def build_status_context(
    settings: Dict[str, object],
    translator: Optional[Callable[[str], str]] = None,
) -> Dict[str, object]:
    resolved = resolve_status_messages(settings, translator)

    order_labels = {item["key"]: item["label"] for item in resolved.get("order", [])}
    order_styles = {item["key"]: item["style"] for item in resolved.get("order", [])}

    for legacy, canonical in LEGACY_ORDER_STATUS_MAP.items():
        if canonical in order_labels:
            order_labels.setdefault(legacy, order_labels[canonical])
        if canonical in order_styles:
            order_styles.setdefault(legacy, order_styles[canonical])

    print_labels = {item["key"]: item["label"] for item in resolved.get("print_job", [])}
    print_styles = {item["key"]: item["style"] for item in resolved.get("print_job", [])}

    return {
        "order_statuses": [(item["key"], item["label"]) for item in resolved.get("order", [])],
        "order_status_labels": order_labels,
        "order_status_styles": order_styles,
        "print_job_statuses": [(item["key"], item["label"]) for item in resolved.get("print_job", [])],
        "print_job_status_labels": print_labels,
        "print_job_status_styles": print_styles,
    }
