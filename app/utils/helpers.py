import hashlib, json, secrets, uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def now_utc():
    return datetime.now(timezone.utc)

def now_iso():
    return now_utc().isoformat()

def parse_iso(value):
    if not value: return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def to_local_iso(value, tz_name="Asia/Kolkata"):
    dt = parse_iso(value) if isinstance(value, str) else value
    return dt.astimezone(ZoneInfo(tz_name)).isoformat()

def new_id(): return str(uuid.uuid4())

def secure_token(): return secrets.token_urlsafe(32)

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()

def json_dumps(value): return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

def json_loads(value, default):
    try: return json.loads(value)
    except Exception: return default
