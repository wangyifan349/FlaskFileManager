# 🗂️ Flask File Manager

一个基于 Flask 的轻量级文件管理系统，允许用户在浏览器中注册／登录后：

- 浏览和切换文件夹  
- 上传、下载文件  
- 创建新文件夹  
- 重命名和删除文件或文件夹  
- 拖拽上传 & 上下文菜单操作  

---

## 🚀 功能亮点

- **用户管理**：注册、登录、登出  
- **目录浏览**：面包屑导航，防止目录遍历攻击  
- **文件上传**：支持点击上传 + 拖拽上传  
- **文件下载**：一键下载并保存至本地  
- **文件/文件夹操作**：新建文件夹、重命名、删除  
- **响应式界面**：基于 Bootstrap 5，美观易用  

---

## 📦 仓库结构

```
FlaskFileManager/
├── app.py               # 后端主程序，包含路由、SQLite 数据库和文件操作
├── application.db       # SQLite 数据库文件（用户表，首次运行时自动创建）
├── uploads/             # 存储用户上传的所有文件和文件夹（首次运行时自动创建）
├── requirements.txt     # Python 依赖列表
├── LICENSE              # GNU GPLv3 开源许可证
└── templates/           # 前端 Jinja2 模板
    ├── base.html        # 通用布局和脚本
    ├── index.html       # 文件管理主界面
    ├── login.html       # 登录页面
    └── register.html    # 注册页面
```

---

## 🔧 安装与运行

1. 克隆仓库  
   ```bash
   git clone https://github.com/wangyifan349/FlaskFileManager.git
   cd FlaskFileManager
   ```

2. 创建并激活 Python 虚拟环境  
   ```bash
   python3 -m venv venv
   source venv/bin/activate       # macOS/Linux
   venv\Scripts\activate.bat      # Windows
   ```

3. 安装依赖  
   ```bash
   pip install -r requirements.txt
   ```

4. 启动服务  
   ```bash
   python app.py
   ```

5. 打开浏览器访问：  
   ```
   http://127.0.0.1:5000
   ```

---

## 🔐 配置

- `SECRET_KEY`：用于 Flask 会话加密，**务必在生产环境中更改**  
- `application.db`：SQLite 数据库文件路径  
- `uploads/`：上传文件存储目录  

可通过环境变量覆盖 `SECRET_KEY`：  
```bash
export SECRET_KEY="your-production-secret"
```

---

## 🎨 界面与使用

1. **注册新用户**  
   打开 `/register` 页面，填写用户名和密码。  

2. **用户登录**  
   打开 `/login` 页面，输入已注册的用户名和密码。  

3. **浏览文件系统**  
   登录后进入首页，默认显示根目录内容。  
   - 点击文件夹名称进入子目录  
   - 使用面包屑导航返回上级  

4. **上传文件**  
   - **拖拽**：将文件拖入“Drag files here”区域  
   - **点击**：点击区域并选择本地文件  

5. **新建文件夹**  
   点击 “New Folder” 按钮，输入新文件夹名称。  

6. **重命名 & 删除**  
   在文件/文件夹行上 **右键** 打开上下文菜单，选择 “Rename” 或 “Delete”。  

7. **下载文件**  
   点击文件行上的 “Download” 按钮，将文件下载到本地。  

---

## 🛡️ 安全机制

- **路径规范化**：所有文件操作通过 `os.path.normpath` + 前缀比对，防止目录遍历  
- **登录保护**：所有文件管理路由均由 `login_required` 装饰器保护，未登录用户重定向到登录页  
- **数据库安全**：使用 SQLite 参数化查询，防止 SQL 注入  

---

## ❤️ 致谢

感谢 [Flask](https://flask.palletsprojects.com/) 社区和所有开源贡献者！  
如果本项目对你有帮助，欢迎 ⭐️ Star 鼓励～

---

## 📄 许可证

本项目基于 GNU **通用公共许可证 第三版**（GNU GPLv3）授权：  

> 您可以自由地使用、修改和分发本软件，但在分发本软件或其任何派生作品时，必须在相同许可证下发布，并保留本许可证声明和作者信息。  

