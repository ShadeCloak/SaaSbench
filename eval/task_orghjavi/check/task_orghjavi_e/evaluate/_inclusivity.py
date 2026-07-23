import re as _re


def _resolve_dotted(context: dict, key: str):
    if not isinstance(context, dict) or not key:
        return None
    if key in context:
        return context[key]
    parts = key.split(".")
    cur = context
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _substitute_placeholders(text: str, context: dict) -> str:
    if not isinstance(text, str) or "{{" not in text:
        return text
    if not isinstance(context, dict):
        return text

    def _sub(m):
        key = m.group(1).strip()
        val = _resolve_dotted(context, key)
        if val is None:
            return m.group(0)
        return str(val)

    return _re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", _sub, text)
