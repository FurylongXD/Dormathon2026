"""SQLite persistence for anonymous local sessions; no client financial overrides."""
import json
from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import time

class Store:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY,csrf TEXT,created REAL,version INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS documents (session TEXT,kind TEXT,state TEXT,payload TEXT,image BLOB,source TEXT,
                PRIMARY KEY(session,kind));
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,session TEXT,state TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS results (session TEXT PRIMARY KEY,version INTEGER,payload TEXT);
            CREATE TABLE IF NOT EXISTS bank_contexts (code TEXT PRIMARY KEY,payload TEXT);
            ''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=20); db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def session(self,sid=None):
        with self.db() as db:
            # Remove stored data after a day. SQLite logical deletion is not secure erasure of backups.
            old=[r['id'] for r in db.execute('SELECT id FROM sessions WHERE created<?',(time.time()-86400,))]
            for oldid in old:
                for table in ('documents','jobs','results'): db.execute(f'DELETE FROM {table} WHERE session=?',(oldid,))
                db.execute('DELETE FROM sessions WHERE id=?',(oldid,))
            row=db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone() if sid else None
            if row: return dict(row),False
            sid=secrets.token_hex(24); csrf=secrets.token_hex(24)
            db.execute('INSERT INTO sessions(id,csrf,created) VALUES(?,?,?)',(sid,csrf,time.time()))
            return {'id':sid,'csrf':csrf,'version':0},True

    def existing(self,sid):
        with self.db() as db:
            r=db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
            return dict(r) if r else None

    def documents(self,sid):
        with self.db() as db:
            return {r['kind']:{'state':r['state'],'doc':json.loads(r['payload']),'source':r['source']}
                    for r in db.execute('SELECT kind,state,payload,source FROM documents WHERE session=?',(sid,))}

    def put_document(self,sid,kind,doc,content,source,state='verified'):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?)',
                       (sid,kind,state,json.dumps(doc),content,source))
            db.execute('UPDATE sessions SET version=version+1 WHERE id=?',(sid,))
            db.execute('DELETE FROM results WHERE session=?',(sid,))

    def save_document(self,sid,kind,digest):
        with self.db() as db:
            r=db.execute('SELECT payload FROM documents WHERE session=? AND kind=?',(sid,kind)).fetchone()
            if not r or json.loads(r['payload'])['source_sha256']!=digest: return False
            db.execute('UPDATE documents SET state=? WHERE session=? AND kind=?',('saved',sid,kind))
            db.execute('UPDATE sessions SET version=version+1 WHERE id=?',(sid,))
            return True

    def image(self,sid,kind):
        with self.db() as db:
            r=db.execute('SELECT image FROM documents WHERE session=? AND kind=?',(sid,kind)).fetchone()
            return r['image'] if r else None

    def remove_document(self,sid,kind):
        with self.db() as db:
            db.execute('DELETE FROM documents WHERE session=? AND kind=?',(sid,kind))
            db.execute('DELETE FROM results WHERE session=?',(sid,))
            db.execute('UPDATE sessions SET version=version+1 WHERE id=?',(sid,))

    def clear(self,sid):
        with self.db() as db:
            for table in ('documents','jobs','results'): db.execute(f'DELETE FROM {table} WHERE session=?',(sid,))
            db.execute('UPDATE sessions SET version=version+1 WHERE id=?',(sid,))

    def job(self,sid,payload):
        jid=secrets.token_hex(16)
        with self.db() as db: db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(jid,sid,'running',json.dumps(payload)))
        return jid

    def update_job(self,jid,state,payload):
        with self.db() as db: db.execute('UPDATE jobs SET state=?,payload=? WHERE id=?',(state,json.dumps(payload),jid))

    def get_job(self,sid,jid):
        with self.db() as db:
            r=db.execute('SELECT * FROM jobs WHERE session=? AND id=?',(sid,jid)).fetchone()
            return {'id':jid,'state':r['state'],**json.loads(r['payload'])} if r else None

    def running(self,sid):
        with self.db() as db: return bool(db.execute('SELECT 1 FROM jobs WHERE session=? AND state=?',(sid,'running')).fetchone())

    def active_job(self,sid):
        with self.db() as db:
            row=db.execute('SELECT id FROM jobs WHERE session=? AND state=? LIMIT 1',(sid,'running')).fetchone()
        return self.get_job(sid,row['id']) if row else None

    def recover_interrupted_jobs(self):
        # Called once when the local server starts; tasks cannot survive a process restart.
        with self.db() as db:
            db.execute('UPDATE jobs SET state=?,payload=? WHERE state=?',('failed',json.dumps({
                'message':'The server restarted. Your saved uploads remain available; submit them again.',
                'progress':100}),'running'))

    def put_result(self,sid,version,result):
        with self.db() as db:
            current=db.execute('SELECT version FROM sessions WHERE id=?',(sid,)).fetchone()
            if not current or current['version']!=version: return False
            db.execute('INSERT OR REPLACE INTO results VALUES(?,?,?)',(sid,version,json.dumps(result,allow_nan=False)))
            return True

    def result(self,sid):
        with self.db() as db:
            r=db.execute('SELECT r.payload FROM results r JOIN sessions s ON s.id=r.session AND s.version=r.version WHERE r.session=?',(sid,)).fetchone()
            return json.loads(r['payload']) if r else None

    def bank(self,code):
        with self.db() as db:
            r=db.execute('SELECT payload FROM bank_contexts WHERE code=?',(code,)).fetchone()
            return json.loads(r['payload']) if r else None

    def put_bank(self,code,value):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO bank_contexts VALUES(?,?)',(code,json.dumps(value)))
