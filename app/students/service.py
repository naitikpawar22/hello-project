from werkzeug.security import generate_password_hash
from app.database import get_db
from app.utils.helpers import new_id, now_iso
from app.utils.validation import is_email

def create_student(data):
    if not data.get("name") or not is_email(data.get("email")) or not data.get("student_code"):
        raise ValueError("name, valid email and student_code are required")
    db=get_db(); ts=now_iso(); sid=new_id()
    pw=generate_password_hash(data["password"]) if data.get("password") else None
    db.execute("INSERT INTO students(id,name,email,student_code,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",
               (sid,data["name"].strip(),data["email"].strip().lower(),data["student_code"].strip(),pw,ts,ts)); db.commit(); return sid

def update_student(sid,data):
    db=get_db(); row=db.execute("SELECT * FROM students WHERE id=?",(sid,)).fetchone()
    if not row: raise LookupError("Student not found")
    name=data.get("name",row["name"]); email=data.get("email",row["email"]); code=data.get("student_code",row["student_code"])
    if not name or not is_email(email) or not code: raise ValueError("Invalid student fields")
    password_hash=row["password_hash"]
    if data.get("password"): password_hash=generate_password_hash(data["password"])
    active=1 if bool(data.get("active",row["active"])) else 0
    db.execute("UPDATE students SET name=?,email=?,student_code=?,password_hash=?,active=?,updated_at=? WHERE id=?",
               (name.strip(),email.strip().lower(),code.strip(),password_hash,active,now_iso(),sid)); db.commit()

def serialize(row): return dict(row) if row else None
