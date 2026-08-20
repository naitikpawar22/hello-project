from app.database import get_db
from app.utils.helpers import new_id, now_iso, json_dumps

def audit(actor, action, entity=None, entity_id=None, metadata=None):
    db = get_db()
    db.execute("INSERT INTO audit_logs(id,actor_id,actor_role,action,entity,entity_id,metadata_json,timestamp) VALUES(?,?,?,?,?,?,?,?)",
               (new_id(), actor.get("id") if actor else None, actor.get("role") if actor else None, action, entity, entity_id, json_dumps(metadata or {}), now_iso()))
    db.commit()
