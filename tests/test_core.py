import io, json
from app import create_app
from app.auth.service import create_admin
from app.database import get_db
from app.questions.service import import_bank
from app.evaluation.service import evaluate_attempt

def make_app(tmp_path):
    db_path=tmp_path/"examforge.db"
    upload=tmp_path/"uploads"; upload.mkdir()
    app=create_app({"TESTING":True,"SECRET_KEY":"test","DATABASE":str(db_path),"UPLOAD_DIR":str(upload)})
    return app

def login(client):
    client.post('/api/auth/bootstrap',json={'name':'Admin','email':'admin@example.com','password':'password123'})
    return client.post('/api/auth/login',json={'email':'admin@example.com','password':'password123'})

def test_health_and_auth(tmp_path):
    app=make_app(tmp_path); c=app.test_client()
    assert c.get('/api/health').status_code==200
    assert c.get('/api/students').status_code==401
    assert login(c).status_code==200
    assert c.get('/api/auth/me').json['user']['role']=='admin'
    assert c.post('/api/auth/logout').status_code==200

def test_student_create_and_csv(tmp_path):
    app=make_app(tmp_path); c=app.test_client(); login(c)
    assert c.post('/api/students',json={'name':'A','email':'a@example.com','student_code':'A1'}).status_code==201
    resp=c.post('/api/students/import',data={'file':(io.BytesIO(b'name,email,student_code\nB,b@example.com,B1\nBad,b@example.com,B1\n'), 'students.csv')},content_type='multipart/form-data')
    assert resp.status_code==201 and resp.json['imported']==1 and len(resp.json['skipped'])==1

def test_evaluation_mcq_msq_negative(tmp_path):
    app=make_app(tmp_path)
    with app.app_context():
        actor={'id':'admin','role':'admin'}
        qs=[{'text':'2+2?','type':'MCQ','options':['3','4'],'correct':[1],'marks':2,'negative_marks':1,'topic':'Math','explanation':'4'},{'text':'Select vowels','type':'MSQ','options':['A','B','E'],'correct':[0,2],'marks':3,'negative_marks':1,'topic':'English','explanation':''}]
        bid=import_bank('T','', 'manual','csv',actor,qs)
        qids=[r['id'] for r in get_db().execute('SELECT id FROM questions WHERE bank_id=?',(bid,)).fetchall()]
        from app.exams.service import create_exam
        eid=create_exam({'title':'Test','duration_minutes':30,'pass_percentage':40,'question_ids':qids},actor)
        from app.attempts.service import start_attempt,save_answers,submit_attempt
        token='tokentest'
        from app.utils.helpers import token_hash
        get_db().execute("INSERT INTO exam_invitations(id,exam_id,email,token_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,datetime('now','+1 day'))",('inv',eid,'s@example.com',token_hash(token),'SENT','2026-08-19T00:00:00+00:00')); get_db().commit()
        aid=start_attempt(token,{'name':'S','email':'s@example.com'})
        save_answers(aid,{qids[0]:[1],qids[1]:[0,2]})
        rid=submit_attempt(aid)
        r=get_db().execute('SELECT * FROM results WHERE id=?',(rid,)).fetchone()
        assert r['score']==5 and r['correct_count']==2 and r['wrong_count']==0 and r['skipped_count']==0
