from functools import wraps
from flask import session, jsonify, request
from app.database import get_db

def current_actor():
    actor_id = session.get("actor_id")
    role = session.get("actor_role")
    if not actor_id or role not in {"admin", "teacher"}: return None
    table = "admins" if role == "admin" else "teachers"
    row = get_db().execute(f"SELECT id,name,email,active FROM {table} WHERE id=?", (actor_id,)).fetchone()
    if not row or not row["active"]: return None
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": role}

def admin_or_teacher_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        actor = current_actor()
        if not actor:
            if request.path.startswith("/api/"): return jsonify(error="Authentication required"), 401
            return jsonify(error="Authentication required"), 401
        return fn(*args, actor=actor, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        actor = current_actor()
        if not actor or actor["role"] != "admin": return jsonify(error="Admin access required"), 403
        return fn(*args, actor=actor, **kwargs)
    return wrapper
