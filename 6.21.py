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
