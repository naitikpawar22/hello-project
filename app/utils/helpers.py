import hashlib, json, secrets, uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import socket

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_shareable_url(req, relative_path=""):
    host = req.host if req else ""
    if not host or "localhost" in host or "127.0.0.1" in host:
        port = host.split(":")[-1] if ":" in host else "5000"
        lan_ip = get_lan_ip()
        host = f"{lan_ip}:{port}"
    
    scheme = req.scheme if req else "http"
    relative_path = relative_path.lstrip("/")
    return f"{scheme}://{host}/{relative_path}"

def now_utc():
    return datetime.now(timezone.utc)

def now_iso():
    return now_utc().isoformat()

def parse_iso(value):
    if not value: return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

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
