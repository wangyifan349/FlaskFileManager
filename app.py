import os
import sqlite3
import shutil
from flask import (Flask, g, render_template, request, redirect,
                   url_for, session, send_from_directory, jsonify, flash)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user, UserMixin)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- 配置 ---
BASE_DIR      = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH       = os.path.join(BASE_DIR, 'app.db')
SECRET_KEY    = 'change-this-secret'
ALLOWED_EXT    = set(['txt','md','py','html','mp4','webm','mp3','wav','jpg','png'])

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Flask & 登录管理 ---
app = Flask(__name__)
app.secret_key = SECRET_KEY
login_mgr = LoginManager(app)
login_mgr.login_view = 'login'

# --- 用户模型（sqlite3 + flask-login） ---
class User(UserMixin):
    def __init__(self, id_, username, pwd_hash):
        self.id = id_
        self.username = username
        self.pwd_hash = pwd_hash

    def check_password(self, password):
        return check_password_hash(self.pwd_hash, password)

@login_mgr.user_loader
def load_user(user_id):
    con = get_db()
    row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row: return None
    return User(row['id'], row['username'], row['password'])

# --- DB 辅助 ---
def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        g._db = db
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_db', None)
    if db: db.close()

def init_db():
    db = get_db()
    db.execute("""
      CREATE TABLE IF NOT EXISTS users (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         username TEXT UNIQUE NOT NULL,
         password TEXT NOT NULL
      )
    """)
    db.commit()

# --- 路径安全 ---
def safe_path(subpath=''):
    # 规范化并禁止跳出 UPLOAD_FOLDER
    full = os.path.normpath(os.path.join(UPLOAD_FOLDER, subpath))
    if not full.startswith(UPLOAD_FOLDER):
        raise ValueError("Invalid path")
    return full

def allowed_file(fname):
    ext = fname.rsplit('.',1)[-1].lower()
    return '.' in fname and ext in ALLOWED_EXT

# --- 启动前建表 ---
with app.app_context():
    init_db()

# --- 认证路由 ---
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u = request.form['username'].strip()
        p = request.form['password']
        if not u or not p:
            flash("用户名/密码不能为空", "warning")
        else:
            db = get_db()
            try:
                db.execute("INSERT INTO users(username,password) VALUES(?,?)",
                           (u, generate_password_hash(p)))
                db.commit()
                flash("注册成功，请登录", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("用户名已存在", "danger")
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u = request.form['username'].strip()
        p = request.form['password']
        row = get_db().execute(
            "SELECT * FROM users WHERE username=?", (u,)
        ).fetchone()
        if row and check_password_hash(row['password'], p):
            user = User(row['id'], row['username'], row['password'])
            login_user(user)
            return redirect(url_for('index'))
        flash("用户名或密码错误", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- 文件管理路由 ---
@app.route('/', defaults={'subpath': ''})
@app.route('/<path:subpath>')
@login_required
def index(subpath):
    try:
        base = safe_path(subpath)
    except:
        return "路径非法", 400
    items=[]
    for name in sorted(os.listdir(base)):
        path_full = os.path.join(base, name)
        items.append({
            'name': name,
            'is_dir': os.path.isdir(path_full)
        })
    return render_template('file_manager.html',
                           entries=items,
                           cur_path=subpath,
                           username=current_user.username)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    sub = request.form.get('path','')
    file = request.files.get('file')
    if not file or file.filename=='':
        return "没选文件", 400
    if not allowed_file(file.filename):
        return "不支持的文件类型", 400
    fn = secure_filename(file.filename)
    dest = safe_path(sub)
    file.save(os.path.join(dest, fn))
    return "OK", 200

@app.route('/mkdir', methods=['POST'])
@login_required
def mkdir():
    j = request.get_json()
    name = secure_filename(j.get('name','').strip())
    if not name:
        return "名称不能为空", 400
    dest = safe_path(j.get('path',''))
    try:
        os.makedirs(os.path.join(dest, name), exist_ok=False)
        return "OK", 200
    except FileExistsError:
        return "已存在同名文件/文件夹", 400

@app.route('/rename', methods=['POST'])
@login_required
def rename():
    j = request.get_json()
    base = safe_path(j.get('path',''))
    old = os.path.join(base, j.get('old',''))
    new = os.path.join(base, secure_filename(j.get('new','')))
    if not os.path.exists(old):
        return "不存在", 404
    os.rename(old, new)
    return "OK", 200

@app.route('/delete', methods=['POST'])
@login_required
def delete():
    j = request.get_json()
    base = safe_path(j.get('path',''))
    target = os.path.join(base, j.get('name',''))
    if j.get('isdir'):
        shutil.rmtree(target)
    else:
        os.remove(target)
    return "OK", 200

@app.route('/download/<path:subpath>/<path:filename>')
@login_required
def download(subpath, filename):
    d = safe_path(subpath)
    return send_from_directory(d, filename, as_attachment=True)

@app.route('/media/<path:subpath>/<path:filename>')
@login_required
def media(subpath, filename):
    d = safe_path(subpath)
    return send_from_directory(d, filename)

@app.route('/edit', methods=['GET','POST'])
@login_required
def edit():
    if request.method=='GET':
        p = safe_path(request.args.get('path',''))
        f = request.args.get('file','')
        try:
            return open(os.path.join(p,f), encoding='utf-8').read()
        except:
            return "读取出错", 500
    data = request.get_json()
    p = safe_path(data.get('path',''))
    f = data.get('file','')
    try:
        open(os.path.join(p,f), 'w', encoding='utf-8').write(data.get('content',''))
        return "OK", 200
    except:
        return "写入出错", 500

if __name__ == '__main__':
    app.run(debug=True)
