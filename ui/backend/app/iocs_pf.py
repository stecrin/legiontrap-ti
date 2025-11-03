from typing import Any


def _extract_from_obj(obj: dict[str, Any] | None) -> str | None:
    """
    Extract an IP string from common shapes:
      - {"src_ip": "..."} / {"ip": "..."}            (flat)
      - {"data": {"src_ip": "..."}}
      - {"data": {"ip": "..."}}
    Returns None if not found.
    """
    if not isinstance(obj, dict):
        return None

    # flat
    for k in ("src_ip", "ip"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v

    # nested under 'data'
    data = obj.get("data")
    if isinstance(data, dict):
        for k in ("src_ip", "ip"):
            v = data.get(k)
            if isinstance(v, str) and v:
                return v

    return None
