import os
import hashlib
import time
from io import BytesIO
from flask import (
    Flask, request, flash, send_file,
    render_template_string, redirect, url_for,
    jsonify
)

# ─────────────────────────────────────────────────────
# 配置部分
# ─────────────────────────────────────────────────────

# 应用根目录
BASEDIR = os.path.abspath(os.path.dirname(__file__))

# 文件存储目录（自动创建）
STORAGE = os.path.join(BASEDIR, "storage")
os.makedirs(STORAGE, exist_ok=True)

app = Flask(__name__)

# 请务必设置一个随机的 secret_key，用于 Flash 消息等
app.secret_key = os.environ.get("FLASK_SECRET", "请替换为自己的随机字符串")

# 限制单文件最大上传 100 MB
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


# ─────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────

def sha256_bytes(data: bytes) -> str:
    """
    计算输入 bytes 的 SHA-256 哈希，并以十六进制字符串返回。
    这就是“CID”（Content ID）。
    """
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def format_time(ts: float) -> str:
    """
    将 UNIX 时间戳格式化为人类可读形式。
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def list_all_files() -> list:
    """
    遍历 STORAGE 目录，返回所有文件的元信息列表。
    每项包含：
      - cid: 文件名（SHA-256 哈希）
      - size: 文件大小（字节）
      - updated: 最后修改时间（字符串）
    """
    items = []
    for fname in os.listdir(STORAGE):
        path = os.path.join(STORAGE, fname)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        items.append({
            "cid": fname,
            "size": stat.st_size,
            "updated": format_time(stat.st_mtime)
        })
    # 按更新时间降序排序
    items.sort(key=lambda x: x["updated"], reverse=True)
    return items


# ─────────────────────────────────────────────────────
# HTML 基础模板（使用 Bootstrap 5 CDN）
# ─────────────────────────────────────────────────────

BASE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
        rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-primary">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">模拟 IPFS 存储</a>
  </div>
</nav>
<div class="container py-4">
  {% with msgs = get_flashed_messages() %}
    {% if msgs %}
      <div class="alert alert-warning">
        {% for m in msgs %}<div>{{ m }}</div>{% endfor %}
      </div>
    {% endif %}
  {% endwith %}
  {{ body }}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""


# ─────────────────────────────────────────────────────
# 路由：主页（上传表单 + 下载表单 + 文件列表）
# ─────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # —— 文件上传 —— 
        if "file" in request.files:
            f = request.files["file"]
            buf = f.read()
            if not buf:
                flash("⚠️ 上传文件为空，请重新选择。")
                return redirect(url_for("index"))

            # 计算 CID
            cid = sha256_bytes(buf)
            path = os.path.join(STORAGE, cid)

            # 如果第一次上传，则保存文件
            if not os.path.exists(path):
                with open(path, "wb") as wf:
                    wf.write(buf)

            # 上传结果页面
            body = f"""
            <div class="card">
              <div class="card-body">
                <h5 class="card-title text-success">上传成功 ✅</h5>
                <p class="card-text">CID：<code>{cid}</code></p>
                <p>文件大小：<strong>{len(buf):,} bytes</strong></p>
                <p>
                  <a href="{url_for('download_file', cid=cid)}" class="btn btn-primary">下载该文件</a>
                  <a href="{url_for('index')}" class="btn btn-secondary">返回首页</a>
                </p>
              </div>
            </div>
            """
            return render_template_string(BASE_HTML, title="上传结果", body=body)

        # —— 根据 CID 下载 —— 
        cid = request.form.get("cid", "").strip()
        if cid:
            return redirect(url_for("download_file", cid=cid))

    # GET 请求：渲染首页，含上传/下载表单和文件列表
    file_list = list_all_files()
    rows = ""
    for f in file_list:
        rows += (
            f"<tr>"
            f"<td>{f['cid']}</td>"
            f"<td>{f['size']:,}</td>"
            f"<td>{f['updated']}</td>"
            f"<td>"
            f"<a href='{url_for('download_file', cid=f['cid'])}' "
            f"class='btn btn-sm btn-outline-primary'>下载</a>"
            f"</td>"
            f"</tr>"
        )

    body = f"""
    <div class="row g-4 mb-4">
      <!-- 上传卡片 -->
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-header">上传文件 → 生成 CID</div>
          <div class="card-body">
            <form method="post" enctype="multipart/form-data">
              <input type="file" name="file" class="form-control mb-3" required>
              <button type="submit" class="btn btn-success">上传并生成 CID</button>
            </form>
          </div>
        </div>
      </div>
      <!-- 下载卡片 -->
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-header">根据 CID 下载文件</div>
          <div class="card-body">
            <form method="post">
              <input type="text" name="cid" class="form-control mb-3"
                     placeholder="请输入 SHA-256 哈希 (CID)" required>
              <button type="submit" class="btn btn-primary">下载文件</button>
            </form>
          </div>
        </div>
      </div>
    </div>
    <!-- 文件列表 -->
    <h5>已存储文件列表</h5>
    <table class="table table-sm">
      <thead>
        <tr><th>CID</th><th>大小（bytes）</th><th>更新时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    """
    return render_template_string(BASE_HTML, title="首页", body=body)


# ─────────────────────────────────────────────────────
# 路由：通过 CID 下载文件
# ─────────────────────────────────────────────────────

@app.route("/download/<cid>")
def download_file(cid):
    """
    根据路径参数 cid，检查存储目录是否存在对应文件，
    若存在则以附件形式返回二进制流，否则重定向回首页并给出警告。
    """
    path = os.path.join(STORAGE, cid)
    if not os.path.isfile(path):
        flash(f"⚠️ 未找到文件 CID：{cid}")
        return redirect(url_for("index"))

    # send_file 支持文件路径或 BytesIO
    return send_file(
        path,
        as_attachment=True,
        download_name=cid,
        mimetype="application/octet-stream"
    )


# ─────────────────────────────────────────────────────
# 开放 API：上传 / 下载 / 列表
# ─────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    接口：文件上传
    - 接收 multipart/form-data 下的 file 字段
    - 返回 JSON: {cid, size, url}
    """
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    f = request.files["file"]
    buf = f.read()
    if not buf:
        return jsonify({"error": "empty file"}), 400

    cid = sha256_bytes(buf)
    path = os.path.join(STORAGE, cid)
    if not os.path.exists(path):
        with open(path, "wb") as wf:
            wf.write(buf)

    return jsonify({
        "cid": cid,
        "size": len(buf),
        "url": url_for("api_download", cid=cid, _external=True)
    })


@app.route("/api/download/<cid>", methods=["GET"])
def api_download(cid):
    """
    接口：文件下载
    - 直接返回二进制流，未找到则返回 404 JSON
    """
    path = os.path.join(STORAGE, cid)
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=cid,
        mimetype="application/octet-stream"
    )


@app.route("/api/list", methods=["GET"])
def api_list():
    """
    接口：列出所有已存储文件
    - 返回 JSON 数组，每项包含 {cid, size, updated}
    """
    return jsonify(list_all_files())


# ─────────────────────────────────────────────────────
# 启动
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    # debug=True 仅用于开发，生产请关闭
    app.run(host="0.0.0.0", port=5000, debug=True)
