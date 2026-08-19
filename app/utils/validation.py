import re
from email.utils import parseaddr

def is_email(value):
    addr = parseaddr(value or "")[1]
    return bool(addr and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr))

def required(data, *fields):
    missing = [f for f in fields if data.get(f) in (None, "")]
    if missing: return f"Missing required fields: {', '.join(missing)}"
    return None

def non_negative_number(value, name):
    try:
        n = float(value)
        if n < 0: raise ValueError
        return n, None
    except Exception:
        return None, f"{name} must be a non-negative number."
