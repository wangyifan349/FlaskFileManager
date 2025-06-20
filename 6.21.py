#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — 单文件云盘示例，含分享链接（30 天有效）
前端界面使用“面包屑 + 列表”视图，Bootstrap + Font Awesome 美化。
依赖:
    pip install Flask Flask-Login Flask-SQLAlchemy itsdangerous Werkzeug
运行:
    python app.py
访问:
    http://127.0.0.1:5000
"""

import os
import re
import shutil
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, send_from_directory,
    abort, jsonify, render_template_string, flash, safe_join
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as TimedSerializer, \
    BadSignature, SignatureExpired

# ----------------------------
# 配置
# ----------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

app = Flask(__name__)
app.config.update({
    'SECRET_KEY': 'change-me-to-a-random-secret',  # 请改成随机值
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + os.path.join(BASE_DIR, 'app.db'),
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'UPLOAD_FOLDER': UPLOAD_ROOT,
    'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,       # 限制单文件 100MB
})

# 分享 Token：30 天（以秒为单位）
share_serializer = TimedSerializer(app.config['SECRET_KEY'], expires_in=2592000)

# ----------------------------
# 扩展初始化
# ----------------------------
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----------------------------
# 简单文件名过滤（保留中英文、数字、点、下划线、连字符、空格）
# ----------------------------
_filename_re = re.compile(r'[^A-Za-z0-9\u4e00-\u9fa5\.\-_ ]+')
def sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = _filename_re.sub('', name)
    return name or 'file'

# ----------------------------
# 用户模型
# ----------------------------
class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

@app.before_first_request
def init_db():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------------
# 当前用户根目录帮助
# ----------------------------
def user_base():
    path = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
    os.makedirs(path, exist_ok=True)
    return path

# ----------------------------
# 注册 / 登录 / 登出
# ----------------------------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form['username'].strip()
        p = request.form['password']
        if not u or not p:
            flash('用户名和密码不能为空', 'warning')
        elif User.query.filter_by(username=u).first():
            flash('用户名已存在', 'danger')
        else:
            user = User(username=u, password=generate_password_hash(p))
            db.session.add(user)
            db.session.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('login'))
    return render_template_string(TPL_BASE, body=TPL_REGISTER)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form['username'].strip()
        p = request.form['password']
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password, p):
            login_user(user)
            return redirect(url_for('index'))
        flash('用户名或密码错误', 'danger')
    return render_template_string(TPL_BASE, body=TPL_LOGIN)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ----------------------------
# 主页面
# ----------------------------
@app.route('/')
@login_required
def index():
    return render_template_string(TPL_BASE, body=TPL_INDEX)

# ----------------------------
# API：目录树（返回整棵树，前端按需渲染）
# ----------------------------
@app.route('/api/tree')
@login_required
def api_tree():
    base = user_base()
    def walk(dirpath, rel=''):
        items = []
        for name in sorted(os.listdir(dirpath)):
            full = os.path.join(dirpath, name)
            stat = os.stat(full)
            node = {
                'id':      os.path.join(rel, name).replace('\\','/'),
                'text':    name,
                'size':    stat.st_size,
                'mtime':   datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'children': []
            }
            if os.path.isdir(full):
                node['children'] = walk(full, node['id'])
            items.append(node)
        return items

    tree = [{'id':'', 'text':'根', 'children': walk(base)}]
    return jsonify(tree)

# ----------------------------
# API：上传 / 下载
# ----------------------------
@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    f = request.files.get('file')
    rel = request.form.get('path','').lstrip('/')
    if not f or not f.filename:
        abort(400, '未选择文件')
    filename = sanitize_filename(f.filename)
    base = safe_join(user_base(), rel)
    if not os.path.isdir(base):
        abort(400, '目标目录不存在')
    dest = os.path.join(base, filename)
    f.save(dest)
    return 'OK', 200

@app.route('/api/download')
@login_required
def api_download():
    rel = request.args.get('path','').lstrip('/')
    full = safe_join(user_base(), rel)
    if not os.path.isfile(full):
        abort(404)
    d, fn = os.path.split(full)
    return send_from_directory(d, fn, as_attachment=True)

# ----------------------------
# API：分享链接（30 天有效）
# ----------------------------
@app.route('/api/share', methods=['POST'])
@login_required
def api_share():
    rel = request.form.get('path','').lstrip('/')
    full = safe_join(user_base(), rel)
    if not os.path.isfile(full):
        return '文件不存在', 404
    token = share_serializer.dumps({'path': rel}).decode('utf-8')
    share_url = url_for('download_shared', token=token, _external=True)
    return jsonify({'url': share_url})

@app.route('/share/<token>')
def download_shared(token):
    try:
        data = share_serializer.loads(token)
    except SignatureExpired:
        abort(410, '分享链接已过期')
    except BadSignature:
        abort(403, '无效分享链接')

    rel = data.get('path','').lstrip('/')
    full = safe_join(app.config['UPLOAD_FOLDER'], rel)
    if not os.path.isfile(full):
        abort(404)
    d, fn = os.path.split(full)
    return send_from_directory(d, fn, as_attachment=True)

# ----------------------------
# API：文件/目录操作（新建/删除/重命名/移动/复制）
# ----------------------------
@app.route('/api/mkdir', methods=['POST'])
@login_required
def api_mkdir():
    parent = request.form.get('path','').lstrip('/')
    name   = request.form.get('name','').strip()
    if not name:
        return '名称不能为空', 400
    base = safe_join(user_base(), parent)
    d = os.path.join(base, sanitize_filename(name))
    if os.path.exists(d):
        return '已存在同名项目', 400
    os.makedirs(d)
    return 'OK', 200

@app.route('/api/delete', methods=['POST'])
@login_required
def api_delete():
    rel    = request.form.get('path','').lstrip('/')
    target = safe_join(user_base(), rel)
    root   = user_base()
    if os.path.abspath(target) == os.path.abspath(root):
        return '不允许删除根目录', 400
    if not os.path.exists(target):
        return '不存在', 404
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)
    return 'OK', 200

@app.route('/api/rename', methods=['POST'])
@login_required
def api_rename():
    src_rel = request.form.get('src','').lstrip('/')
    newname = request.form.get('name','').strip()
    if not newname:
        return '名称不能为空', 400
    src = safe_join(user_base(), src_rel)
    if not os.path.exists(src):
        return '源不存在', 404
    dst = os.path.join(os.path.dirname(src), sanitize_filename(newname))
    if os.path.exists(dst):
        return '目标已存在', 400
    os.rename(src, dst)
    return 'OK', 200

@app.route('/api/move', methods=['POST'])
@login_required
def api_move():
    src_rel = request.form.get('src','').lstrip('/')
    dst_rel = request.form.get('dst','').lstrip('/')
    src = safe_join(user_base(), src_rel)
    dst = safe_join(user_base(), dst_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(src, dst)
    return 'OK', 200

@app.route('/api/copy', methods=['POST'])
@login_required
def api_copy():
    src_rel = request.form.get('src','').lstrip('/')
    dst_rel = request.form.get('dst','').lstrip('/')
    src = safe_join(user_base(), src_rel)
    dst = safe_join(user_base(), dst_rel)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return 'OK', 200

# ----------------------------
# HTML + JS 模板：美化后的界面
# ----------------------------
TPL_BASE = """
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
  <title>Flask 云盘（列表视图）</title>
  <!-- Bootstrap -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">
  <!-- Font Awesome 图标 -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@5.15.4/css/all.min.css">
  <style>
    /* 容器内边距 */
    #file-browser { padding:1rem; }
    /* 面包屑分隔符 */
    .breadcrumb-item + .breadcrumb-item::before { content: "›"; }
    /* 列表项悬停效果 */
    .file-item { cursor: pointer; }
    .file-item:hover { background:#f8f9fa; }
    /* 文件名过长省略 */
    .file-name { display:inline-block; max-width:200px; white-space:nowrap;
                 overflow:hidden; text-overflow:ellipsis; vertical-align:middle; }
    /* 操作按钮组 */
    .item-actions button { margin-left:0.3rem; }
  </style>
</head><body>
<nav class="navbar navbar-light bg-light">
  <a class="navbar-brand">云盘示例</a>
  <div class="ml-auto">
    {% if current_user.is_authenticated %}
      <span class="mr-3">{{ current_user.username }}</span>
      <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">登出</a>
    {% endif %}
  </div>
</nav>
<div class="container mt-3">
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in msgs %}
      <div class="alert alert-{{cat}}">{{msg}}</div>
    {% endfor %}
  {% endwith %}
  {{ body|safe }}
</div>
<!-- jQuery + Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
// 通用 POST 函数
function postForm(u, d){
  return fetch(u, {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body: new URLSearchParams(d)
  }).then(r=>r.text().then(t=>{ if(!r.ok) throw t; return t; }));
}

let treeData = {};      // 缓存整棵目录树
let currentPath = '';   // 当前相对路径

// 加载整棵目录树
function loadTree(){
  return fetch('/api/tree')
    .then(r=>r.json())
    .then(arr=>{
      treeData = {};
      function flatten(nodes){
        nodes.forEach(n=>{
          treeData[n.id] = n;
          if(n.children && n.children.length>0) flatten(n.children);
        });
      }
      flatten(arr[0].children);
    });
}

// 渲染面包屑
function renderBreadcrumb(){
  let container = $('#breadcrumb').empty();
  let parts = currentPath ? currentPath.split('/') : [];
  // 根目录
  container.append(
    `<li class="breadcrumb-item${parts.length? '' : ' active'}"
         ${parts.length? 'data-path=""' : ''}>根目录</li>`
  );
  let accum = '';
  parts.forEach((p,i)=>{
    accum = accum? accum + '/' + p : p;
    let active = (i===parts.length-1)? ' active': '';
    let attr = (i===parts.length-1)? '' : `data-path="${accum}"`;
    container.append(
      `<li class="breadcrumb-item${active}" ${attr}>${p}</li>`
    );
  });
}

// 渲染当前目录列表
function renderList(){
  let list = $('#file-list').empty();
  let children = treeData[currentPath]? treeData[currentPath].children : [];
  // 先文件夹后文件，并按名称排序
  children.sort((a,b)=>{
    let fa = !!a.children, fb = !!b.children;
    if(fa !== fb) return fa? -1:1;
    return a.text.localeCompare(b.text);
  });
  children.forEach(item=>{
    let isFolder = Array.isArray(item.children);
    let icon = isFolder? 'fa-folder': 'fa-file';
    let li = $(`
      <li class="list-group-item file-item" data-id="${item.id}">
        <i class="fas ${icon} mr-2"></i>
        <span class="file-name">${item.text}</span>
        <div class="item-actions">
          ${isFolder
            ? `<button class="btn btn-sm btn-outline-primary btn-open-folder" title="打开">
                 <i class="fas fa-folder-open"></i></button>`
            : `<button class="btn btn-sm btn-outline-success btn-download" title="下载">
                 <i class="fas fa-download"></i></button>
               <button class="btn btn-sm btn-outline-info btn-share" title="分享">
                 <i class="fas fa-link"></i></button>`
          }
          <button class="btn btn-sm btn-outline-secondary btn-rename" title="重命名">
            <i class="fas fa-edit"></i></button>
          <button class="btn btn-sm btn-outline-danger btn-delete" title="删除">
            <i class="fas fa-trash"></i></button>
        </div>
      </li>`);
    list.append(li);
  });
}

// 切换到某个路径
function goPath(path){
  currentPath = path;
  renderBreadcrumb();
  renderList();
}

$(function(){
  // 初次加载
  loadTree().then(_=> goPath(''));

  // 面包屑点击跳转
  $('#breadcrumb').on('click','li[data-path]', function(){
    goPath($(this).data('path'));
  });

  // 打开文件夹
  $('#file-list').on('click','.btn-open-folder', function(){
    let id = $(this).closest('li').data('id');
    goPath(id);
  });

  // 下载文件
  $('#file-list').on('click','.btn-download', function(){
    let id = $(this).closest('li').data('id');
    location = '/api/download?path=' + encodeURIComponent(id);
  });

  // 生成分享链接
  $('#file-list').on('click','.btn-share', function(){
    let id = $(this).closest('li').data('id');
    postForm('/api/share',{path:id})
      .then(r=>JSON.parse(r))
      .then(o=>prompt('分享链接（30天有效）', o.url))
      .catch(alert);
  });

  // 重命名
  $('#file-list').on('click','.btn-rename', function(){
    let li = $(this).closest('li'), id = li.data('id');
    let newname = prompt('新名称', li.find('.file-name').text());
    if(!newname) return;
    postForm('/api/rename',{src:id,name:newname})
      .then(_=> loadTree().then(_=> goPath(currentPath)))
      .catch(alert);
  });

  // 删除
  $('#file-list').on('click','.btn-delete', function(){
    if(!confirm('确认删除？')) return;
    let id = $(this).closest('li').data('id');
    postForm('/api/delete',{path:id})
      .then(_=> loadTree().then(_=> goPath(currentPath)))
      .catch(alert);
  });

  // 顶层上传
  $('#uploader').on('change', function(){
    let f=this.files[0]; if(!f) return;
    let fd=new FormData(); fd.append('file',f); fd.append('path','');
    fetch('/api/upload',{method:'POST',body:fd})
      .then(r=>r.text().then(t=>{ if(!r.ok) throw t; alert('上传成功'); }))
      .then(_=> loadTree().then(_=> goPath(currentPath)))
      .catch(alert);
  });
});
</script>
</body></html>
"""

TPL_REGISTER = """
<h3>注册</h3>
<form method="post">
  <div class="form-group">
    <label>用户名</label>
    <input name="username" class="form-control" required>
  </div>
  <div class="form-group">
    <label>密码</label>
    <input type="password" name="password" class="form-control" required>
  </div>
  <button class="btn btn-primary">注册</button>
  <a href="{{url_for('login')}}" class="btn btn-link">已有账号？登录</a>
</form>
"""

TPL_LOGIN = """
<h3>登录</h3>
<form method="post">
  <div class="form-group">
    <label>用户名</label>
    <input name="username" class="form-control" required>
  </div>
  <div class="form-group">
    <label>密码</label>
    <input type="password" name="password" class="form-control" required>
  </div>
  <button class="btn btn-primary">登录</button>
  <a href="{{url_for('register')}}" class="btn btn-link">没有账号？注册</a>
</form>
"""

TPL_INDEX = """
<div class="mb-2">
  <input type="file" id="uploader" class="form-control-file">
</div>
<!-- 文件浏览器容器 -->
<div id="file-browser">
  <nav aria-label="breadcrumb">
    <ol class="breadcrumb" id="breadcrumb"></ol>
  </nav>
  <ul class="list-group" id="file-list"></ul>
</div>
"""

# ----------------------------
# 启动
# ----------------------------
if __name__ == '__main__':
    app.run(debug=True)







# app.py
import os
import shutil
from flask import (
    Flask, request, jsonify, send_from_directory, abort,
    render_template_string
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
ROOT_DIR = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(ROOT_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'mp4', 'avi',
    'mkv', 'mpeg', 'mov', 'webm'
}
TEXT_EXTENSIONS = {'txt', 'md', 'json', 'xml', 'csv', 'log', 'py', 'html', 'js', 'css'}

def safe_path(path: str) -> str:
    abs_path = os.path.abspath(os.path.join(ROOT_DIR, path))
    if not abs_path.startswith(os.path.abspath(ROOT_DIR)):
        raise Exception("非法路径访问")
    return abs_path

def allowed_file(filename: str) -> bool:
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXTENSIONS

def is_text_file(filename: str) -> bool:
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in TEXT_EXTENSIONS

def format_size(size: int) -> str:
    for unit in ['B','KB','MB','GB','TB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"

def list_directory(path: str):
    abs_dir = safe_path(path)
    if not os.path.isdir(abs_dir):
        raise Exception("目录不存在")
    folders, files = [], []
    for entry in os.listdir(abs_dir):
        entry_path = os.path.join(abs_dir, entry)
        stat = os.stat(entry_path)
        item = {'name': entry, 'mtime': int(stat.st_mtime), 'size': stat.st_size}
        if os.path.isdir(entry_path):
            folders.append(item)
        else:
            files.append(item)
    folders.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())
    return folders, files

@app.route('/')
def route_index():
    return render_template_string(MAIN_PAGE_TEMPLATE)

@app.route('/api/list', methods=['GET'])
def api_list():
    path = request.args.get('path', '')
    try:
        folders, files = list_directory(path)
        return jsonify({'ok': True, 'path': path, 'folders': folders, 'files': files})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/mkdir', methods=['POST'])
def api_mkdir():
    data = request.json or {}
    path = data.get('path', '')
    folder_name = (data.get('name') or '').strip()
    if not folder_name:
        return jsonify({'ok': False, 'error': '文件夹名不能为空'}), 400
    if any(c in folder_name for c in r'\/:*?"<>|'):
        return jsonify({'ok': False, 'error': '文件夹名包含非法字符'}), 400
    try:
        abs_dir = safe_path(path)
        new_folder_path = os.path.join(abs_dir, folder_name)
        if os.path.exists(new_folder_path):
            return jsonify({'ok': False, 'error': '文件夹已存在'}), 400
        os.mkdir(new_folder_path)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/upload', methods=['POST'])
def api_upload():
    path = request.form.get('path', '')
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': '未找到文件'}), 400
    files = request.files.getlist('file')
    try:
        abs_dir = safe_path(path)
        count = 0
        for f in files:
            filename = secure_filename(f.filename)
            if not filename or not allowed_file(filename):
                return jsonify({'ok': False, 'error': f'文件类型不允许: {filename}'}), 400
            filepath = os.path.join(abs_dir, filename)
            if os.path.exists(filepath):
                name, ext = os.path.splitext(filename)
                for i in range(1, 1000):
                    newname = f"{name}({i}){ext}"
                    filepath = os.path.join(abs_dir, newname)
                    if not os.path.exists(filepath):
                        filename = newname
                        break
            f.save(filepath)
            count += 1
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/delete', methods=['POST'])
def api_delete():
    data = request.json or {}
    path = data.get('path', '')
    name = data.get('name')
    if not name:
        return jsonify({'ok': False, 'error': '缺少参数name'}), 400
    try:
        abs_dir = safe_path(path)
        target_Path = os.path.join(abs_dir, name)
        if not os.path.exists(target_Path):
            return jsonify({'ok': False, 'error': '文件或文件夹不存在'}), 404
        if os.path.isfile(target_Path):
            os.remove(target_Path)
        else:
            shutil.rmtree(target_Path)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/rename', methods=['POST'])
def api_rename():
    data = request.json or {}
    path = data.get('path', '')
    oldname = data.get('oldname')
    newname = (data.get('newname') or '').strip()
    if not oldname or not newname:
        return jsonify({'ok': False, 'error': '缺少重命名参数'}), 400
    if any(c in newname for c in r'\/:*?"<>|'):
        return jsonify({'ok': False, 'error': '名称包含非法字符'}), 400
    try:
        abs_dir = safe_path(path)
        old_path = os.path.join(abs_dir, oldname)
        new_path = os.path.join(abs_dir, newname)
        if not os.path.exists(old_path):
            return jsonify({'ok': False, 'error': '原文件不存在'}), 404
        if os.path.exists(new_path):
            return jsonify({'ok': False, 'error': '新名称已存在'}), 400
        os.rename(old_path, new_path)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/move', methods=['POST'])
def api_move():
    data = request.json or {}
    src_path = data.get('src_path', '')
    name = data.get('name')
    dst_path = data.get('dst_path', '')
    if not src_path or not dst_path or not name:
        return jsonify({'ok': False, 'error': '缺少参数'}), 400
    try:
        abs_src = safe_path(src_path)
        abs_dst = safe_path(dst_path)
        src_file = os.path.join(abs_src, name)
        if not os.path.exists(src_file):
            return jsonify({'ok': False, 'error': '源文件不存在'}), 404
        dst_file = os.path.join(abs_dst, name)
        if os.path.exists(dst_file):
            return jsonify({'ok': False, 'error': '目标路径存在同名文件'}), 400
        shutil.move(src_file, dst_file)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/download')
def route_download():
    path = request.args.get('path', '')
    name = request.args.get('name', '')
    if not name:
        abort(404)
    try:
        abs_dir = safe_path(path)
        return send_from_directory(abs_dir, name, as_attachment=True)
    except Exception:
        abort(404)

@app.route('/api/view/text', methods=['GET'])
def api_view_text():
    path = request.args.get('path', '')
    name = request.args.get('name', '')
    if not name:
        return jsonify({'ok': False, 'error': '必须提供文件名'}), 400
    try:
        abs_dir = safe_path(path)
        filepath = os.path.join(abs_dir, name)
        if not os.path.isfile(filepath) or not is_text_file(name):
            return jsonify({'ok': False, 'error': '文件不存在或不可查看'}), 404
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return jsonify({'ok': True, 'content': content})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/save/text', methods=['POST'])
def api_save_text():
    data = request.json or {}
    path = data.get('path', '')
    name = data.get('name')
    content = data.get('content', '')
    if not name:
        return jsonify({'ok': False, 'error': '必须提供文件名'}), 400
    if not is_text_file(name):
        return jsonify({'ok': False, 'error': '仅支持文本文件保存'}), 400
    try:
        abs_dir = safe_path(path)
        filepath = os.path.join(abs_dir, name)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/file/<path:filepath>')
def route_file(filepath):
    try:
        abs_fp = safe_path(filepath)
        if not os.path.isfile(abs_fp):
            abort(404)
        return send_from_directory(ROOT_DIR, filepath)
    except Exception:
        abort(404)

MAIN_PAGE_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Flask 云盘示例</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css" rel="stylesheet"/>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" rel="stylesheet"/>
<style>
  body {padding:10px; background:#f8f9fa;}
  .file-list li:hover {background:#e9ecef;}
  .file-list li.dragging {opacity:0.4;}
  .context-menu {
    position: fixed;
    z-index: 1050;
    display:none;
    background: white;
    border: solid 1px #ccc;
    border-radius: 3px;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.15);
    width:150px;
  }
  .context-menu ul {
    list-style:none;
    margin:0; padding:5px 0;
  }
  .context-menu ul li {
    padding: 6px 12px;
    cursor:pointer;
  }
  .context-menu ul li:hover {
    background:#007bff;
    color:#fff;
  }
  #breadcrumb a {
    cursor:pointer;
  }
  #viewer {
    max-height: 60vh;
    overflow:auto;
  }
  #viewer img, #viewer video {
    max-width: 100%;
    max-height: 60vh;
  }
  #text-editor {
    height: 400px;
    width: 100%;
    font-family: monospace;
    white-space: pre-wrap;
    background: #fff;
    border: 1px solid #ccc;
    padding: 10px;
    box-sizing: border-box;
  }
</style>
</head>
<body>
<h3 class="mb-3"><i class="fas fa-hdd"></i> Flask 云盘示例</h3>

<nav aria-label="breadcrumb">
  <ol class="breadcrumb" id="breadcrumb"></ol>
</nav>

<div class="mb-3">
  <input type="file" id="file-upload" style="display:none;" multiple webkitdirectory directory />
  <button id="btn-upload" class="btn btn-primary btn-sm"><i class="fas fa-upload"></i> 上传文件/文件夹</button>
  <button id="btn-newfolder" class="btn btn-success btn-sm"><i class="fas fa-folder-plus"></i> 新建文件夹</button>
  <button id="btn-refresh" class="btn btn-outline-secondary btn-sm"><i class="fas fa-sync-alt"></i> 刷新</button>
</div>

<ul class="list-group file-list" id="file-list" style="user-select:none;"></ul>

<hr/>

<div id="viewer-section" style="display:none;">
  <h5>文件查看器</h5>
  <div id="viewer"></div>
  <button id="btn-close-viewer" class="btn btn-secondary btn-sm mt-2">关闭查看器</button>
</div>

<div id="edit-section" style="display:none;">
  <h5>文本编辑器</h5>
  <div>
    <textarea id="text-editor"></textarea>
  </div>
  <button id="btn-save-text" class="btn btn-primary btn-sm mt-2">保存</button>
  <button id="btn-close-editor" class="btn btn-secondary btn-sm mt-2">关闭编辑器</button>
</div>

<div class="context-menu" id="context-menu">
  <ul>
    <li data-action="upload">上传文件/文件夹</li>
    <li data-action="newfolder">新建文件夹</li>
    <li data-action="rename">重命名</li>
    <li data-action="delete" style="color:#c00;">删除</li>
  </ul>
</div>

<script src="https://cdn.jsdelivr.net/npm/jquery@3.6.1/dist/jquery.min.js"></script>
<script>
const rootPath = "";
let currentPath = "";
let selectedItem = null;

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>"']/g, m=>{
    switch(m){
      case '&':return '&amp;';
      case '<':return '&lt;';
      case '>':return '&gt;';
      case '"':return '&quot;';
      case "'":return '&#39;';
      default: return m;
    }
  });
}

function formatDate(ts){
  let d= new Date(ts*1000);
  return d.toLocaleString();
}

function refreshList(path){
  if(path === undefined) path = currentPath;
  $.getJSON('/api/list', {path: path}, function(res){
    if(!res.ok){alert(res.error);return;}
    currentPath = res.path;
    renderBreadcrumb(currentPath);
    renderFileList(res.folders, res.files);
    selectedItem = null;
  }).fail(xhr=>{
    alert('加载失败:'+(xhr.responseJSON?.error || xhr.statusText));
  });
}

function renderBreadcrumb(path){
  let crumbs = path.split('/').filter(x => x.length > 0);
  let html = `<li class="breadcrumb-item"><a href="#" data-path="">根目录</a></li>`;
  let acc = "";
  crumbs.forEach((c,i)=>{
    acc += "/" + c;
    if(i === crumbs.length-1){
      html += `<li class="breadcrumb-item active" aria-current="page">${escapeHtml(c)}</li>`;
    } else {
      html += `<li class="breadcrumb-item"><a href="#" data-path="${acc}">${escapeHtml(c)}</a></li>`;
    }
  });
  $('#breadcrumb').html(html);
}

$('#breadcrumb').on('click', 'a', function(e){
  e.preventDefault();
  let path= $(this).data('path');
  refreshList(path);
});

function renderFileList(folders, files){
  let ul = $('#file-list').empty();
  folders.forEach(f=>{
    let li = $(`
      <li class="list-group-item d-flex justify-content-between align-items-center" draggable="true" data-type="folder" data-name="${escapeHtml(f.name)}">
        <span><i class="fas fa-folder"></i> ${escapeHtml(f.name)}</span>
        <small class="text-muted">${formatDate(f.mtime)}</small>
      </li>`);
    ul.append(li);
  });
  files.forEach(f=>{
    let ext = f.name.split('.').pop().toLowerCase();
    let icon = 'fa-file';
    if(['png','jpg','jpeg','gif','bmp'].includes(ext)) icon='fa-file-image';
    else if(['mp4','avi','mkv','webm','mov'].includes(ext)) icon='fa-file-video';
    else if(['txt','md','json','xml','csv','log','py','html','js','css'].includes(ext)) icon = 'fa-file-alt';
    let li = $(`
      <li class="list-group-item d-flex justify-content-between align-items-center" draggable="true" data-type="file" data-name="${escapeHtml(f.name)}">
        <span><i class="fas ${icon}"></i> ${escapeHtml(f.name)}</span>
        <small class="text-muted">${formatDate(f.mtime)} / ${(f.size/1024).toFixed(1)} KB</small>
      </li>`);
    ul.append(li);
  });
}

$('#file-list').on('click', 'li', function(){
  let type = $(this).data('type');
  let name = $(this).data('name');
  if(type === 'folder'){
    let newPath = currentPath ? currentPath + '/' + name : name;
    refreshList(newPath);
  } else {
    openFileViewer(name);
  }
});

function openFileViewer(filename){
  let ext = filename.split('.').pop().toLowerCase();
  if(['png','jpg','jpeg','gif','bmp'].includes(ext)){
    $("#viewer").html(`<img src="/file/${encodeURI(currentPath? currentPath+"/"+filename:filename)}" alt="">`);
    showViewer();
  } else if(['mp4','avi','mkv','webm','mov'].includes(ext)){
    $("#viewer").html(`
      <video controls autoplay style="max-width:100%;max-height:60vh">
        <source src="/file/${encodeURI(currentPath? currentPath+"/"+filename:filename)}" />
        您的浏览器不支持视频播放。
      </video>
    `);
    showViewer();
  } else if(isTextExtension(ext)){
    $.getJSON('/api/view/text', {path: currentPath, name: filename}, function(res){
      if(res.ok){
        $("#text-editor").val(res.content).data('filename', filename);
        showEditor();
      } else {
        alert("加载文件失败：" + res.error);
      }
    }).fail(()=>alert("加载文件失败"));
  } else {
    alert("不支持在线预览此文件类型。");
  }
}

function isTextExtension(ext){
  return ['txt','md','json','xml','csv','log','py','html','js','css'].includes(ext);
}

function showViewer(){
  $('#viewer-section').show();
  $('#edit-section').hide();
  clearSelection();
}
function showEditor(){
  $('#edit-section').show();
  $('#viewer-section').hide();
  clearSelection();
}

$('#btn-close-viewer').click(() => {
  $('#viewer-section').hide();
  clearSelection();
});
$('#btn-close-editor').click(() => {
  $('#edit-section').hide();
  clearSelection();
});
$('#btn-save-text').click(() => {
  let content = $('#text-editor').val();
  let filename = $('#text-editor').data('filename');
  if(!filename){
    alert("无效文件");
    return;
  }
  $.ajax({
    url: '/api/save/text',
    type: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({path: currentPath, name: filename, content}),
    success(res){
      if(res.ok){
        alert('保存成功');
      } else {
        alert('保存失败: ' + res.error);
      }
    },
    error(xhr){
      alert('保存失败: ' + (xhr.responseJSON?.error || xhr.statusText));
    }
  });
});

function clearSelection(){
  selectedItem=null;
  $('.file-list li').removeClass('active');
  hideContextMenu();
}

$('#btn-upload').click(()=>$('#file-upload').click());
$('#file-upload').change(function(){
  if(this.files.length === 0) return;
  uploadFiles(this.files);
  $(this).val('');
});

function uploadFiles(files){
  let formData = new FormData();
  for(let f of files) formData.append('file', f);
  formData.append('path', currentPath);
  $.ajax({
    url: '/api/upload',
    type: 'POST',
    processData: false,
    contentType: false,
    data: formData,
    success(res){
      if(res.ok){
        alert(`${res.count} 个文件上传成功`);
        refreshList();
      } else {
        alert('上传失败: ' + res.error);
      }
    },
    error(xhr){
      alert('上传失败: ' + (xhr.responseJSON?.error || xhr.statusText));
    }
  });
}

$('#btn-newfolder').click(() => {
  let folderName = prompt('请输入文件夹名称:');
  if(!folderName) return;
  folderName = folderName.trim();
  if(!folderName){
    alert('名称不能为空');
    return;
  }
  $.ajax({
    url: '/api/mkdir',
    type: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({path: currentPath, name: folderName}),
    success(res){
      if(res.ok){
        alert('创建成功');
        refreshList();
      } else {
        alert('创建失败: ' + res.error);
      }
    },
    error(xhr){
      alert('创建失败: ' + (xhr.responseJSON?.error || xhr.statusText));
    }
  });
});

$('#btn-refresh').click(() => refreshList());

let contextMenu = $('#context-menu');
$('#file-list').on('contextmenu', 'li', function(e){
  e.preventDefault();
  selectedItem = $(this);
  $('.file-list li').removeClass('active');
  selectedItem.addClass('active');
  showContextMenu(e.pageX, e.pageY);
});

$('#file-list').on('contextmenu', function(e){
  if(e.target === this){
    selectedItem = null;
    $('.file-list li').removeClass('active');
    showContextMenu(e.pageX, e.pageY, true);
    e.preventDefault();
  }
});

function showContextMenu(x,y,isRoot=false){
  if(isRoot){
    contextMenu.find('[data-action="rename"], [data-action="delete"]').hide();
  } else {
    contextMenu.find('[data-action="rename"], [data-action="delete"]').show();
  }
  contextMenu.css({top: y + 'px', left: x + 'px'}).show();
}
function hideContextMenu(){
  contextMenu.hide();
}
$(window).click(hideContextMenu);

contextMenu.on('click', 'li', function(){
  const action = $(this).data('action');
  if(action === 'upload'){
    $('#file-upload').click();
  } else if(action === 'newfolder'){
    let fname = prompt('请输入文件夹名称:');
    if(!fname) return;
    fname = fname.trim();
    if(!fname){
      alert('名称不能为空');
      return;
    }
    $.ajax({
      url: '/api/mkdir',
      contentType: 'application/json',
      type: 'POST',
      data: JSON.stringify({path: currentPath, name: fname}),
      success(res){
        if(res.ok){
          alert('创建成功');
          refreshList();
        } else {
          alert('创建失败: ' + res.error);
        }
      }
    });
  } else if(action === 'rename'){
    if(!selectedItem){
      alert('未选择文件');
      return;
    }
    let oldname = selectedItem.data('name');
    let newname = prompt('请输入新名称:', oldname);
    if(!newname)return;
    newname = newname.trim();
    if(newname === oldname)return;
    $.ajax({
      url: '/api/rename',
      contentType: 'application/json',
      type: 'POST',
      data: JSON.stringify({path: currentPath, oldname, newname}),
      success(res){
        if(res.ok){
          alert('重命名成功');
          refreshList();
        } else {
          alert('重命名失败: ' + res.error);
        }
      }
    });
  } else if(action === 'delete'){
    if(!selectedItem){
      alert('未选择文件');
      return;
    }
    let delname = selectedItem.data('name');
    if(!confirm(`确定删除【${delname}】吗？此操作不可恢复！`)) return;
    $.ajax({
      url: '/api/delete',
      contentType: 'application/json',
      type: 'POST',
      data: JSON.stringify({path: currentPath, name: delname}),
      success(res){
        if(res.ok){
          alert('删除成功');
          refreshList();
        } else {
          alert('删除失败: ' + res.error);
        }
      }
    });
  }
  hideContextMenu();
});

let dragSrc = null;
$('#file-list').on('dragstart', 'li', function(e){
  dragSrc = this;
  $(this).addClass('dragging');
  e.originalEvent.dataTransfer.effectAllowed = 'move';
  e.originalEvent.dataTransfer.setData('text/plain', $(this).data('name'));
});
$('#file-list').on('dragend', 'li', function(){
  $(this).removeClass('dragging');
  dragSrc = null;
});

$('#file-list').on('dragover', 'li', function(e){
  e.preventDefault();
  if(this === dragSrc) return;
  if($(this).data('type') !== 'folder') return;
  $(this).addClass('drag-over');
});
$('#file-list').on('dragleave', 'li', function(){
  $(this).removeClass('drag-over');
});
$('#file-list').on('drop', 'li', function(e){
  e.preventDefault();
  $(this).removeClass('drag-over');
  if(!dragSrc) return;
  if($(this).data('type') !== 'folder') return;
  let srcName = $(dragSrc).data('name');
  let dstFolder = currentPath ? currentPath + '/' + $(this).data('name') : $(this).data('name');
  if(!confirm(`确认将【${srcName}】移动到【${dstFolder}】吗？`)) return;
  $.ajax({
    url: '/api/move',
    contentType: 'application/json',
    type: 'POST',
    data: JSON.stringify({src_path: currentPath, name: srcName, dst_path: dstFolder}),
    success(res){
      if(res.ok){
        alert('移动成功');
        refreshList();
      } else {
        alert('移动失败: '+ res.error);
      }
    }
  });
  dragSrc = null;
});

$(function(){
  refreshList();
});
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True, port=5000)



