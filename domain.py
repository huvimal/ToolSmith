"""Local scoped issue workflow. SQLite transactions protect approval/apply consistency."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parent
WORKSPACE='alpha'
STATUSES={'todo','in_progress','done'}
TRANSITIONS={'todo':{'in_progress'},'in_progress':{'todo','done'},'done':{'in_progress'}}


class PolicyError(ValueError):pass
class ConflictError(PolicyError):pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Store:
    def __init__(self,path=None):
        self.path=Path(path) if path else Path(os.environ.get('TOOLSMITH_DB',str(ROOT/'private/workflow.db')))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS issues(workspace TEXT,id TEXT,title TEXT,status TEXT,version INTEGER,description TEXT,PRIMARY KEY(workspace,id));
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,workspace TEXT,request_key TEXT,payload TEXT,payload_hash TEXT,state TEXT,created REAL,expires REAL,receipt_hash TEXT,result TEXT,UNIQUE(workspace,request_key));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,workspace TEXT,issue_id TEXT,action_id TEXT UNIQUE,before_status TEXT,after_status TEXT,version INTEGER,created REAL);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT,action_id TEXT,created REAL);
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('cursor_secret',secrets.token_hex(32)))
            for row in [('alpha','ALPHA-001','Review release checklist','todo',1,'Fictional release preparation; inspect release.md.'),
                        ('alpha','ALPHA-002','Investigate duplicate retries','in_progress',1,'Fictional retry issue; inspect retries.md.'),
                        ('alpha','ALPHA-003','Document schema limits','done',1,'Fictional completed documentation task.'),
                        ('beta','BETA-001','Excluded private task','todo',1,'BETA_ISSUE_MARKER')]:
                db.execute('INSERT OR IGNORE INTO issues VALUES(?,?,?,?,?,?)',row)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=3000')
        try:
            with db:yield db
        finally:db.close()

    def secret(self):
        with self.connect() as db:return db.execute("SELECT value FROM settings WHERE key='cursor_secret'").fetchone()[0].encode()

    def issue(self,issue_id):
        with self.connect() as db:row=db.execute('SELECT * FROM issues WHERE workspace=? AND id=?',(WORKSPACE,issue_id)).fetchone()
        if not row:raise PolicyError('Issue unavailable in the configured workspace')
        return dict(row)

    def list_issues(self,status=None,after='',limit=10):
        if status is not None and status not in STATUSES:raise PolicyError('Unsupported status')
        if not 1<=limit<=20:raise PolicyError('Issue limit must be 1–20')
        with self.connect() as db:
            rows=db.execute('SELECT id,title,status,version FROM issues WHERE workspace=? AND id>? AND (? IS NULL OR status=?) ORDER BY id LIMIT ?',
                (WORKSPACE,after,status,status,limit+1)).fetchall()
        return [dict(r) for r in rows[:limit]],len(rows)>limit

    def propose(self,issue_id,new_status,reason,request_key,expected_version,now=None):
        import re
        if type(expected_version) is not int or expected_version<1:raise PolicyError('Expected version must be a positive integer')
        if new_status not in STATUSES or not isinstance(reason,str) or not 1<=len(reason.strip())<=500:
            raise PolicyError('Use a supported status and 1–500 character reason')
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',request_key):raise PolicyError('Use an 8–64 character idempotency key')
        now=time.time() if now is None else now
        payload={'workspace':WORKSPACE,'issue_id':issue_id,'new_status':new_status,'reason':reason.strip(),'expected_version':expected_version}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT * FROM actions WHERE workspace=? AND request_key=?',(WORKSPACE,request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=digest(payload):raise ConflictError('Idempotency key already belongs to a different payload')
                return self.public_action(prior)
            issue=db.execute('SELECT * FROM issues WHERE workspace=? AND id=?',(WORKSPACE,issue_id)).fetchone()
            if not issue:raise PolicyError('Issue unavailable in the configured workspace')
            if issue['version']!=expected_version:raise ConflictError('Issue version changed; inspect and propose again')
            if new_status not in TRANSITIONS[issue['status']]:raise PolicyError('Transition is not allowed from the current status')
            action_id=secrets.token_hex(16)
            db.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?)',
                (action_id,WORKSPACE,request_key,canonical(payload),digest(payload),'pending',now,now+600,None,None))
            db.execute('INSERT INTO audit(event,action_id,created) VALUES(?,?,?)',('proposed',action_id,now))
            row=db.execute('SELECT * FROM actions WHERE id=?',(action_id,)).fetchone()
            return self.public_action(row)

    @staticmethod
    def public_action(row):
        return {'action_id':row['id'],'state':row['state'],'payload':json.loads(row['payload']),
            'payload_sha256':row['payload_hash'],'expires_at_unix':row['expires'],
            'result':json.loads(row['result']) if row['result'] else None}

    def action(self,action_id):
        with self.connect() as db:row=db.execute('SELECT * FROM actions WHERE workspace=? AND id=?',(WORKSPACE,action_id)).fetchone()
        if not row:raise PolicyError('Action unavailable')
        return self.public_action(row)

    def review(self,action_id,expected_hash,approve,now=None):
        """Host UI/CLI only. Deliberately not exposed as an MCP tool."""
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM actions WHERE workspace=? AND id=?',(WORKSPACE,action_id)).fetchone()
            if not row or row['state']!='pending':raise PolicyError('Only a pending action can be reviewed')
            if approve and row['expires']<=now:raise PolicyError('Proposal expired')
            if not hmac.compare_digest(row['payload_hash'],expected_hash) or digest(json.loads(row['payload']))!=row['payload_hash']:
                raise ConflictError('Reviewed payload hash differs')
            payload=json.loads(row['payload'])
            issue=db.execute('SELECT version FROM issues WHERE workspace=? AND id=?',(WORKSPACE,payload['issue_id'])).fetchone()
            if approve and (not issue or issue['version']!=payload['expected_version']):raise ConflictError('Issue version changed before review')
            receipt=secrets.token_urlsafe(32) if approve else None
            db.execute('UPDATE actions SET state=?,receipt_hash=? WHERE id=?',('approved' if approve else 'rejected',digest(receipt) if receipt else None,action_id))
            db.execute('INSERT INTO audit(event,action_id,created) VALUES(?,?,?)',('approved' if approve else 'rejected',action_id,now))
        return {'action_id':action_id,'state':'approved' if approve else 'rejected','receipt':receipt}

    def apply(self,action_id,receipt,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM actions WHERE workspace=? AND id=?',(WORKSPACE,action_id)).fetchone()
            if not row or not row['receipt_hash'] or not hmac.compare_digest(row['receipt_hash'],digest(receipt)):
                raise PolicyError('Valid locally approved receipt required')
            if row['state']=='applied':return {**json.loads(row['result']),'replayed':True}
            if row['state']!='approved' or now>=row['expires']:raise PolicyError('Approval is not active or has expired')
            payload=json.loads(row['payload'])
            if digest(payload)!=row['payload_hash'] or payload['workspace']!=WORKSPACE:raise ConflictError('Approved payload changed')
            issue=db.execute('SELECT * FROM issues WHERE workspace=? AND id=?',(WORKSPACE,payload['issue_id'])).fetchone()
            if not issue or issue['version']!=payload['expected_version']:raise ConflictError('Issue version changed after approval')
            if payload['new_status'] not in TRANSITIONS[issue['status']]:raise PolicyError('Transition no longer allowed')
            version=issue['version']+1
            db.execute('UPDATE issues SET status=?,version=? WHERE workspace=? AND id=?',(payload['new_status'],version,WORKSPACE,payload['issue_id']))
            db.execute('INSERT INTO events(workspace,issue_id,action_id,before_status,after_status,version,created) VALUES(?,?,?,?,?,?,?)',
                (WORKSPACE,payload['issue_id'],action_id,issue['status'],payload['new_status'],version,now))
            result={'action_id':action_id,'issue_id':payload['issue_id'],'status':payload['new_status'],'version':version,'replayed':False}
            db.execute("UPDATE actions SET state='applied',result=? WHERE id=?",(canonical(result),action_id))
            db.execute('INSERT INTO audit(event,action_id,created) VALUES(?,?,?)',('applied',action_id,now))
        return result

    def pending(self):
        with self.connect() as db:rows=db.execute("SELECT * FROM actions WHERE workspace=? AND state='pending' ORDER BY created DESC LIMIT 20",(WORKSPACE,)).fetchall()
        return [self.public_action(r) for r in rows]

    def events(self):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT seq,issue_id,action_id,before_status,after_status,version FROM events WHERE workspace=? ORDER BY seq DESC LIMIT 20',(WORKSPACE,))]
