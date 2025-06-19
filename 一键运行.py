import os
import sqlite3
from functools import wraps
from flask import Flask, request, redirect, url_for, session, g, send_from_directory, render_template_string, jsonify

# Flask setup
app = Flask(__name__)
app.secret_key = 'change-this-secret'

# Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'app.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----- Database -----
def get_db():
    db = getattr(g, '_db', None)
    if not db:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        g._db = db
    return db

@app.teardown_appcontext
def close_db(error):
    db = getattr(g, '_db', None)
    if db:
        db.close()

def init_db():
    db = get_db()
    c = db.cursor()
    # 用户表
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    db.commit()

init_db()

# ----- Auth -----
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kw)
    return wrapper

# ----- Path security -----
def safe_path(sub=''):
    p = os.path.normpath(os.path.join(UPLOAD_DIR, sub))
    if not p.startswith(UPLOAD_DIR):
        raise ValueError("Invalid path")
    return p

# ----- Template -----
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>File Manager</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    #dropzone { border:2px dashed #ccc; padding:20px; text-align:center; color:#666; margin-bottom:15px; }
    #ctxMenu { position:absolute; display:none; list-style:none; padding:0; margin:0; background:#fff; border:1px solid #ccc; z-index:1000; }
    #ctxMenu li { padding:5px 15px; cursor:pointer; }
    #ctxMenu li:hover { background:#eee; }
  </style>
</head>
<body class="p-4">
<div class="container">
  <div class="d-flex justify-content-between mb-3">
    <div>Logged in as {{ username }}</div>
    <div><a href="{{ url_for('logout') }}" class="btn btn-sm btn-secondary">Logout</a></div>
  </div>
  <h1 class="mb-3">File Manager</h1>
  <nav><ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="{{ url_for('index') }}">Home</a></li>
    {% if cur_path %}
      {% set parts = cur_path.split('/') %}
      {% for i in range(parts|length) %}
        <li class="breadcrumb-item">
          <a href="{{ url_for('index', subpath=parts[:i+1]|join('/')) }}">{{ parts[i] }}</a>
        </li>
      {% endfor %}
    {% endif %}
  </ol></nav>

  <div id="dropzone">Drag & drop or click to upload
    <input id="fileInput" type="file" multiple style="display:none">
  </div>
  <button id="btnNewFolder" class="btn btn-sm btn-secondary mb-3">New Folder</button>

  <table class="table table-striped">
    <thead><tr><th>Name</th><th>Type</th><th>Actions</th></tr></thead>
    <tbody id="fileList">
      {% for e in entries %}
      <tr data-name="{{ e.name }}" data-isdir="{{ e.isdir }}">
        <td>
          {% if e.isdir %}
            📁 <a href="{{ url_for('index', subpath=(cur_path + '/' + e.name).lstrip('/')) }}">{{ e.name }}</a>
          {% else %}
            📄 {{ e.name }}
          {% endif %}
        </td>
        <td>{{ 'Folder' if e.isdir else 'File' }}</td>
        <td>
          {% if not e.isdir %}
            <a href="{{ url_for('download', subpath=cur_path, filename=e.name) }}" class="btn btn-sm btn-outline-primary">Download</a>
            {% if e.name.lower().endswith(('.mp4','.webm')) %}
              <button class="btn btn-sm btn-outline-success play-video">Play Video</button>
            {% elif e.name.lower().endswith(('.mp3','.wav')) %}
              <button class="btn btn-sm btn-outline-success play-audio">Play Audio</button>
            {% elif e.name.lower().endswith(('.txt','.md','.py','.html')) %}
              <button class="btn btn-sm btn-outline-warning edit-file">Edit</button>
            {% endif %}
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<ul id="ctxMenu">
  <li id="ctxRename">Rename</li>
  <li id="ctxDelete">Delete</li>
</ul>

<div class="modal fade" id="modal" tabindex="-1"><div class="modal-dialog modal-lg">
  <div class="modal-content">
    <div class="modal-header">
      <h5 class="modal-title" id="modalTitle"></h5>
      <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
    </div>
    <div class="modal-body" id="modalBody"></div>
    <div class="modal-footer" id="modalFoot"></div>
  </div>
</div></div>

<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
let curPath = "{{ cur_path }}", selectedRow = null;

// Upload handlers
$("#dropzone")
  .on("click", ()=> $("#fileInput").click())
  .on("dragover", e=>{ e.preventDefault(); })
  .on("drop", e=>{ e.preventDefault(); upload(e.originalEvent.dataTransfer.files); });
$("#fileInput").on("change", e=> upload(e.target.files));

function upload(files) {
  let fd = new FormData();
  for (let f of files) fd.append("file", f);
  fd.append("path", curPath);
  $.ajax({ url:"/upload", type:"POST", data:fd, processData:false, contentType:false })
    .done(()=>location.reload()).fail(err=>alert(err.responseText));
}

// New folder
$("#btnNewFolder").click(()=>{
  let name = prompt("Folder name:");
  if (!name) return;
  $.ajax({
    url:"/mkdir", type:"POST", contentType:"application/json",
    data: JSON.stringify({ path:curPath, name:name })
  }).done(()=>location.reload()).fail(err=>alert(err.responseText));
});

// Context menu
$(document).on("contextmenu", "tr", function(e){
  e.preventDefault(); selectedRow = $(this);
  $("#ctxMenu").css({ top:e.pageY, left:e.pageX }).show();
});
$(document).click(()=> $("#ctxMenu").hide());

// Rename
$("#ctxRename").click(()=>{
  let oldName = selectedRow.data("name");
  let newName = prompt("New name:", oldName);
  if (!newName || newName === oldName) return;
  $.ajax({
    url:"/rename", type:"POST", contentType:"application/json",
    data: JSON.stringify({ path:curPath, old:oldName, new:newName })
  }).done(()=>location.reload()).fail(err=>alert(err.responseText));
});

// Delete
$("#ctxDelete").click(()=>{
  let name = selectedRow.data("name");
  let isdir = selectedRow.data("isdir");
  if (!confirm("Delete?")) return;
  $.ajax({
    url:"/delete", type:"POST", contentType:"application/json",
    data: JSON.stringify({ path:curPath, name:name, isdir:isdir })
  }).done(()=>location.reload()).fail(err=>alert(err.responseText));
});

// Edit text
$(document).on("click", ".edit-file", function(){
  let name = $(this).closest("tr").data("name");
  $.get("/edit", { path:curPath, file:name }, data=>{
    $("#modalTitle").text("Edit: " + name);
    $("#modalBody").html('<textarea id="editor" class="form-control" rows="15"></textarea>');
    $("#editor").val(data);
    $("#modalFoot").html('<button id="saveEdit" class="btn btn-primary">Save</button>');
    new bootstrap.Modal($("#modal")).show();
    $("#saveEdit").click(()=>{
      $.ajax({
        url:"/edit", type:"POST", contentType:"application/json",
        data: JSON.stringify({ path:curPath, file:name, content:$("#editor").val() })
      }).done(()=>location.reload()).fail(err=>alert(err.responseText));
    });
  });
});

// Play video
$(document).on("click", ".play-video", function(){
  let name = $(this).closest("tr").data("name");
  $("#modalTitle").text("Video: " + name);
  $("#modalBody").html(`<video controls style="width:100%" src="/media/${encodeURIComponent(curPath)}/${encodeURIComponent(name)}"></video>`);
  $("#modalFoot").html('');
  new bootstrap.Modal($("#modal")).show();
});

// Play audio
$(document).on("click", ".play-audio", function(){
  let name = $(this).closest("tr").data("name");
  $("#modalTitle").text("Audio: " + name);
  $("#modalBody").html(`<audio controls style="width:100%" src="/media/${encodeURIComponent(curPath)}/${encodeURIComponent(name)}"></audio>`);
  $("#modalFoot").html('');
  new bootstrap.Modal($("#modal")).show();
});
</script>
</body>
</html>
"""

# ----- Routes -----
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        db = get_db()
        try:
            db.execute("INSERT INTO users(username,password) VALUES(?,?)", (u,p))
            db.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "User exists", 400
    return '''
    <form method="post">
      <input name="username" placeholder="Username" required>
      <input name="password" type="password" placeholder="Password" required>
      <button>Register</button>
    </form>
    '''

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']; p = request.form['password']
        row = get_db().execute("SELECT * FROM users WHERE username=? AND password=?", (u,p)).fetchone()
        if row:
            session['user_id'] = row['id']; session['username'] = row['username']
            return redirect(url_for('index'))
        return "Invalid", 400
    return '''
    <form method="post">
      <input name="username" placeholder="Username" required>
      <input name="password" type="password" placeholder="Password" required>
      <button>Login</button>
    </form>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/', defaults={'subpath': ''})
@app.route('/<path:subpath>')
@login_required
def index(subpath):
    base = safe_path(subpath)
    items = []
    for name in sorted(os.listdir(base)):
        items.append({'name': name, 'isdir': os.path.isdir(os.path.join(base, name))})
    return render_template_string(TEMPLATE, entries=items, cur_path=subpath, username=session['username'])

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    sub = request.form.get('path','')
    dest = safe_path(sub)
    f = request.files.get('file')
    if not f:
        return "No file", 400
    f.save(os.path.join(dest, f.filename))
    return "OK"

@app.route('/mkdir', methods=['POST'])
@login_required
def make_folder():
    j = request.get_json()
    dest = safe_path(j.get('path',''))
    name = j.get('name','').strip()
    if not name:
        return "Name required", 400
    os.makedirs(os.path.join(dest, name), exist_ok=False)
    return "OK"

@app.route('/rename', methods=['POST'])
@login_required
def rename_item():
    j = request.get_json()
    base = safe_path(j.get('path',''))
    old = os.path.join(base, j.get('old'))
    new = os.path.join(base, j.get('new'))
    if not os.path.exists(old):
        return "Not found", 404
    os.rename(old, new)
    return "OK"

@app.route('/delete', methods=['POST'])
@login_required
def delete_item():
    j = request.get_json()
    base = safe_path(j.get('path',''))
    target = os.path.join(base, j.get('name'))
    if j.get('isdir'):
        os.rmdir(target)
    else:
        os.remove(target)
    return "OK"

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
def edit_file():
    if request.method == 'GET':
        p = safe_path(request.args.get('path',''))
        fn = request.args.get('file')
        try:
            return open(os.path.join(p, fn), encoding='utf-8').read()
        except:
            return "Read error", 500
    data = request.get_json()
    p = safe_path(data.get('path',''))
    fn = data.get('file')
    try:
        open(os.path.join(p, fn), 'w', encoding='utf-8').write(data.get('content',''))
        return "OK"
    except:
        return "Write error", 500

if __name__ == '__main__':
    app.run(debug=True)
