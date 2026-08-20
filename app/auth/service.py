from werkzeug.security import generate_password_hash, check_password_hash
from app.database import get_db
from app.utils.helpers import new_id, now_iso

def create_admin(name, email, password):
    db=get_db(); ts=now_iso(); aid=new_id()
    db.execute("INSERT INTO admins(id,name,email,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)",
               (aid,name,email.lower().strip(),generate_password_hash(password),ts,ts)); db.commit(); return aid

def create_teacher(name,email,password):
    db=get_db(); ts=now_iso(); tid=new_id()
    db.execute("INSERT INTO teachers(id,name,email,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)",
               (tid,name,email.lower().strip(),generate_password_hash(password),ts,ts)); db.commit(); return tid

def authenticate(email,password):
    db=get_db(); email=(email or "").strip().lower()
    for role, table in (("admin","admins"),("teacher","teachers")):
        row=db.execute(f"SELECT * FROM {table} WHERE email=?",(email,)).fetchone()
        if row and row["active"] and check_password_hash(row["password_hash"],password or ""):
            return {"id":row["id"],"name":row["name"],"email":row["email"],"role":role}
    return None
