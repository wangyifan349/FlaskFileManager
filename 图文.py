pip install flask flask-login
python app.py

import os
import sqlite3
import hashlib
import mimetypes
from math import ceil
from datetime import datetime
from flask import (
    Flask, g, render_template, request,
    redirect, url_for, flash, send_from_directory,
    abort, jsonify
)
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.utils import secure_filename, safe_join
from jinja2 import DictLoader

# ====== 配置 ======
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'app.db')
UPLOAD_ROOT = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXT = {'png','jpg','jpeg','gif','mp4','mov','avi','mkv'}
MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB
PER_PAGE = 5

os.makedirs(UPLOAD_ROOT, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config.update(
    DATABASE=DATABASE,
    UPLOAD_ROOT=UPLOAD_ROOT,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    JSON_AS_ASCII=False  # JSON 返回保留中文
)

# ====== 模板 ======
TEMPLATES = {
  'base.html': """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{% block title %}文件系统{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
        rel="stylesheet" crossorigin="anonymous">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-light bg-light">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">文件系统</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto">
        {% if current_user.is_authenticated %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}">面板</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('search') }}">搜索</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">登出</a></li>
        {% else %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('login_view') }}">登录</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
        {% endif %}
      </ul>
    </div>
  </div>
</nav>
<div class="container mt-4">
  {% with msgs = get_flashed_messages() %}
    {% if msgs %}
      <div class="alert alert-warning">
        <ul class="mb-0">
          {% for m in msgs %}<li>{{ m }}</li>{% endfor %}
        </ul>
      </div>
    {% endif %}
  {% endwith %}
  {% block body %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
        crossorigin="anonymous"></script>
</body>
</html>
""",
  'index.html': """
{% extends 'base.html' %}
{% block title %}首页{% endblock %}
{% block body %}
<div class="jumbotron p-4 bg-light rounded-3">
  <h1 class="display-5">欢迎来到文件上传系统</h1>
  <p class="lead">支持图片/视频上传与浏览，完全免费。</p>
</div>
{% endblock %}
""",
  'register.html': """
{% extends 'base.html' %}
{% block title %}注册{% endblock %}
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <h2>注册</h2>
    <form method="post">
      <div class="mb-3">
        <label class="form-label">用户名</label>
        <input name="username" class="form-control" required>
      </div>
      <div class="mb-3">
        <label class="form-label">密码</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button class="btn btn-primary">注册</button>
    </form>
  </div>
</div>
{% endblock %}
""",
  'login.html': """
{% extends 'base.html' %}
{% block title %}登录{% endblock %}
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <h2>登录</h2>
    <form method="post">
      <div class="mb-3">
        <label class="form-label">用户名</label>
        <input name="username" class="form-control" required>
      </div>
      <div class="mb-3">
        <label class="form-label">密码</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button class="btn btn-primary">登录</button>
    </form>
  </div>
</div>
{% endblock %}
""",
  'dashboard.html': """
{% extends 'base.html' %}
{% block title %}我的面板{% endblock %}
{% block body %}
<h2>你好，{{ current_user.username }}</h2>
<form method="post" enctype="multipart/form-data" class="mb-4">
  <div class="input-group">
    <input type="file" name="file" class="form-control" required>
    <button class="btn btn-success">上传</button>
  </div>
</form>
<h3>我的文件 (第 {{ page }}/{{ total_pages }} 页)</h3>
<div class="row">
  {% for fn, mime, ts in files %}
  <div class="col-md-4 mb-4">
    <div class="card">
      {% if mime.startswith('image') %}
        <img src="{{ url_for('uploaded_file', user_id=current_user.id, filename=fn) }}"
             class="card-img-top">
      {% elif mime.startswith('video') %}
        <video class="w-100" controls>
          <source src="{{ url_for('uploaded_file', user_id=current_user.id, filename=fn) }}"
                  type="{{ mime }}">
        </video>
      {% endif %}
      <div class="card-body">
        <p class="card-text">{{ fn }}</p>
        <p class="text-muted">{{ ts }}</p>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
<nav>
  <ul class="pagination">
    {% if page>1 %}
    <li class="page-item">
      <a class="page-link" href="{{ url_for('dashboard',page=page-1) }}">上一页</a>
    </li>
    {% endif %}
    {% if page<total_pages %}
    <li class="page-item">
      <a class="page-link" href="{{ url_for('dashboard',page=page+1) }}">下一页</a>
    </li>
    {% endif %}
  </ul>
</nav>
{% endblock %}
""",
  'search.html': """
{% extends 'base.html' %}
{% block title %}搜索{% endblock %}
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <h2>搜索用户</h2>
    <form method="post" class="input-group mb-3">
      <input name="username" class="form-control" placeholder="用户名" required>
      <button class="btn btn-primary">搜索</button>
    </form>
  </div>
</div>
{% endblock %}
""",
  'profile.html': """
{% extends 'base.html' %}
{% block title %}用户：{{ profile_user.username }}{% endblock %}
{% block body %}
<h2>用户：{{ profile_user.username }}</h2>
<h3>文件列表 (第 {{ page }}/{{ total_pages }} 页)</h3>
<div class="row">
  {% for fn, mime, ts in files %}
  <div class="col-md-4 mb-4">
    <div class="card">
      {% if mime.startswith('image') %}
        <img src="{{ url_for('uploaded_file', user_id=profile_user.id, filename=fn) }}"
             class="card-img-top">
      {% elif mime.startswith('video') %}
        <video class="w-100" controls>
          <source src="{{ url_for('uploaded_file', user_id=profile_user.id, filename=fn) }}"
                  type="{{ mime }}">
        </video>
      {% endif %}
      <div class="card-body">
        <p>{{ fn }}</p>
        <p class="text-muted">{{ ts }}</p>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
<nav>
  <ul class="pagination">
    {% if page>1 %}
    <li class="page-item">
      <a class="page-link"
         href="{{ url_for('profile',user_id=profile_user.id,page=page-1) }}">
        上一页
      </a>
    </li>
    {% endif %}
    {% if page<total_pages %}
    <li class="page-item">
      <a class="page-link"
         href="{{ url_for('profile',user_id=profile_user.id,page=page+1) }}">
        下一页
      </a>
    </li>
    {% endif %}
  </ul>
</nav>
{% endblock %}
"""
}
app.jinja_loader = DictLoader(TEMPLATES)

# ====== Flask-Login 设置 ======
login = LoginManager(app)
login.login_view = 'login_view'

# ====== 用户模型 ======
class User(UserMixin):
    def __init__(self, uid, username, pwd_hash):
        self.id = uid
        self.username = username
        self.pwd_hash = pwd_hash

    def check_password(self, pwd):
        return hashlib.sha256(pwd.encode()).hexdigest() == self.pwd_hash

# ====== 数据库操作 ======
def get_db():
    if not hasattr(g, 'db'):
        conn = sqlite3.connect(app.config['DATABASE'], detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON;')
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(exc):
    if hasattr(g, 'db'):
        g.db.close()

def init_db():
    schema = """
    CREATE TABLE IF NOT EXISTS user (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      pwd_hash TEXT NOT NULL
    );
    """
    db = get_db()
    db.executescript(schema)
    db.commit()

@app.before_first_request
def setup():
    init_db()

@login.user_loader
def load_user(user_id):
    row = get_db().execute('SELECT * FROM user WHERE id=?', (user_id,)).fetchone()
    return User(row['id'], row['username'], row['pwd_hash']) if row else None

# ====== 工具函数 ======
def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def get_user_folder(uid):
    path = os.path.join(app.config['UPLOAD_ROOT'], str(uid))
    os.makedirs(path, exist_ok=True)
    return path

def list_files(uid):
    folder = get_user_folder(uid)
    entries = []
    for fn in os.listdir(folder):
        full = os.path.join(folder, fn)
        if os.path.isfile(full):
            mime = mimetypes.guess_type(fn)[0] or 'application/octet-stream'
            ts = datetime.fromtimestamp(os.path.getmtime(full))\
                   .strftime('%Y-%m-%d %H:%M:%S')
            entries.append((fn, mime, ts))
    entries.sort(key=lambda x: x[2], reverse=True)
    return entries

def paginate_list(items, page, per_page=PER_PAGE):
    total = len(items)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return items[start:start+per_page], total_pages

# ====== 路由：Web 前端 ======
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','')
        if not u or not p:
            flash('用户名和密码不能为空')
        else:
            try:
                db = get_db()
                db.execute('INSERT INTO user(username,pwd_hash) VALUES(?,?)',
                           (u, hash_pwd(p)))
                db.commit()
                flash('注册成功，请登录')
                return redirect(url_for('login_view'))
            except sqlite3.IntegrityError:
                flash('用户名已存在')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login_view():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','')
        row = get_db().execute('SELECT * FROM user WHERE username=?', (u,)).fetchone()
        if row and hash_pwd(p) == row['pwd_hash']:
            login_user(User(row['id'], row['username'], row['pwd_hash']))
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard', methods=['GET','POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        f = request.files.get('file')
        if f and allowed_file(f.filename):
            fn = secure_filename(f.filename)
            f.save(os.path.join(get_user_folder(current_user.id), fn))
            flash('上传成功')
            return redirect(url_for('dashboard'))
        flash('请选择合法的文件（图片/视频）')
    page = request.args.get('page', 1, type=int)
    allf = list_files(current_user.id)
    files, total_pages = paginate_list(allf, page)
    return render_template('dashboard.html',
                           files=files, page=page, total_pages=total_pages)

@app.route('/search', methods=['GET','POST'])
@login_required
def search():
    if request.method == 'POST':
        name = request.form.get('username','').strip()
        row = get_db().execute('SELECT * FROM user WHERE username=?', (name,)).fetchone()
        if row:
            return redirect(url_for('profile', user_id=row['id']))
        flash('未找到该用户')
    return render_template('search.html')

@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    row = get_db().execute('SELECT * FROM user WHERE id=?', (user_id,)).fetchone()
    if not row:
        flash('用户不存在')
        return redirect(url_for('search'))
    page = request.args.get('page', 1, type=int)
    allf = list_files(user_id)
    files, total_pages = paginate_list(allf, page)
    return render_template('profile.html',
                           profile_user=row,
                           files=files, page=page, total_pages=total_pages)

# ====== 路由：安全文件访问 ======
@app.route('/uploads/<int:user_id>/<path:filename>')
def uploaded_file(user_id, filename):
    folder = get_user_folder(user_id)
    full = safe_join(folder, filename)
    if not full or not os.path.isfile(full):
        abort(404)
    return send_from_directory(folder, filename)

# ====== 路由：公开 API ======
@app.route('/api/user/<int:user_id>/media', methods=['GET'])
def api_user_media(user_id):
    if not get_db().execute('SELECT 1 FROM user WHERE id=?', (user_id,)).fetchone():
        return jsonify({"error":"User not found"}), 404
    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', PER_PAGE, type=int)
    mtype    = request.args.get('type', 'all').lower()

    allf = list_files(user_id)
    if mtype in ('image','video'):
        allf = [f for f in allf if f[1].startswith(mtype)]
    total = len(allf)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page-1)*per_page
    slice_ = allf[start:start+per_page]

    items = []
    for fn, mime, ts in slice_:
        items.append({
          "filename": fn,
          "mime": mime,
          "timestamp": ts,
          "url": url_for('uploaded_file',
                         user_id=user_id,
                         filename=fn,
                         _external=True)
        })

    return jsonify({
      "user_id": user_id,
      "page": page,
      "per_page": per_page,
      "total": total,
      "total_pages": total_pages,
      "items": items
    })

# ====== 启动 ======
if __name__ == '__main__':
    app.run(debug=True)
