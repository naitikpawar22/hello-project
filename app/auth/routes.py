from flask import Blueprint, request, jsonify, session
from app.auth.service import authenticate, create_admin
from app.database import get_db
from app.utils.security import current_actor
from app.utils.audit import audit

bp=Blueprint("auth",__name__,url_prefix="/api/auth")

@bp.post("/login")
def login():
    data=request.get_json(silent=True) or {}
    actor=authenticate(data.get("email"),data.get("password"))
    if not actor: return jsonify(error="Invalid email or password"),401
    session.clear(); session["actor_id"]=actor["id"]; session["actor_role"]=actor["role"]
    audit(actor,"login")
    return jsonify(user=actor)

@bp.post("/logout")
def logout():
    actor=current_actor(); session.clear()
    if actor: audit(actor,"logout")
    return jsonify(message="Logged out")

@bp.get("/me")
def me():
    actor=current_actor()
    return (jsonify(user=actor),200) if actor else (jsonify(user=None),401)

@bp.post("/bootstrap")
def bootstrap():
    db=get_db(); count=db.execute("SELECT COUNT(*) c FROM admins").fetchone()["c"]
    if count: return jsonify(error="Admin bootstrap is already disabled because an admin exists."),403
    data=request.get_json(silent=True) or {}
    if not all(data.get(k) for k in ("name","email","password")): return jsonify(error="name, email and password are required"),400
    if len(data["password"])<8: return jsonify(error="Password must be at least 8 characters"),422
    aid=create_admin(data["name"].strip(),data["email"],data["password"])
    actor={"id":aid,"role":"admin","name":data["name"],"email":data["email"]}
    audit(actor,"admin_bootstrap", "admins", aid)
    return jsonify(message="Admin created",id=aid),201
