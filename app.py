import os
import sqlite3
from functools import wraps
from flask import Flask, request, redirect, url_for, session, g, send_from_directory, render_template

# 初始化
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret')

# 路径配置
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'app.db')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# DB 工具
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = get_db()
    db.execute('''
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
      )
    ''')
    db.commit()

# 安全路径
def safe_path(sub=''):
    path = os.path.normpath(os.path.join(UPLOAD_ROOT, sub))
    if not path.startswith(UPLOAD_ROOT):
        raise ValueError("Invalid path")
    return path

# 登录装饰
def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrapped

# 启动时初始化 DB
with app.app_context():
    init_db()

# --- Auth ---
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u = request.form['username']
        p = request.form['password']
        try:
            get_db().execute(
              "INSERT INTO users(username,password) VALUES(?,?)", (u,p)
            )
            get_db().commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "User exists", 400
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u,p = request.form['username'], request.form['password']
        row = get_db().execute(
          "SELECT * FROM users WHERE username=? AND password=?", (u,p)
        ).fetchone()
        if row:
            session['user_id'], session['username'] = row['id'], row['username']
            return redirect(url_for('index'))
        return "Invalid", 400
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- File Manager ---
@app.route('/', defaults={'subpath': ''})
@app.route('/<path:subpath>')
@login_required
def index(subpath):
    base = safe_path(subpath)
    entries = sorted(os.listdir(base))
    items = []
    for name in entries:
        full = os.path.join(base, name)
        items.append({'name': name, 'isdir': os.path.isdir(full)})
    return render_template('index.html',
                           entries=items,
                           cur_path=subpath,
                           username=session['username'])

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    sub = request.form.get('path','')
    dst = safe_path(sub)
    f = request.files.get('file')
    if not f: return "No file", 400
    f.save(os.path.join(dst, f.filename))
    return "OK"

@app.route('/mkdir', methods=['POST'])
@login_required
def mkdir():
    j = request.get_json()
    dst = safe_path(j.get('path',''))
    nm = j.get('name','').strip()
    if not nm: return "Name empty", 400
    os.makedirs(os.path.join(dst,nm), exist_ok=False)
    return "OK"

@app.route('/rename', methods=['POST'])
@login_required
def rename():
    j = request.get_json()
    base = safe_path(j.get('path',''))
    old, new = os.path.join(base,j['old']), os.path.join(base,j['new'])
    if not os.path.exists(old): return "Not found", 404
    os.rename(old,new)
    return "OK"

@app.route('/delete', methods=['POST'])
@login_required
def delete():
    j = request.get_json()
    base = safe_path(j.get('path',''))
    target = os.path.join(base, j['name'])
    if j.get('isdir'): os.rmdir(target)
    else:               os.remove(target)
    return "OK"

@app.route('/download/<path:subpath>/<path:filename>')
@login_required
def download(subpath, filename):
    base = safe_path(subpath)
    return send_from_directory(base, filename, as_attachment=True)

if __name__=='__main__':
    app.run(debug=True)
