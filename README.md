# FlaskFileManager 🗂️🚀

A lightweight, single-file Flask application for web-based file and folder management.  
Licensed under **GNU General Public License v3.0 (GPL-3.0)**.

---

## 🎯 Features

- **User Authentication**  
  - Registration & login powered by **Flask-Login**  
  - Secure password hashing with **Werkzeug**  
- **Directory Management**  
  - Browse nested directories  
  - Create new folders  
- **File Operations**  
  - Drag-and-drop or click-to-upload (allowed extensions: `.txt`, `.md`, `.py`, `.html`, `.mp4`, `.webm`, `.mp3`, `.wav`, `.jpg`, `.png`)  
  - Download files as attachments  
  - Rename & delete via right-click context menu (AJAX)  
- **Media & Text Handling**  
  - In-browser video (`.mp4`, `.webm`) and audio (`.mp3`, `.wav`) playback  
  - Modal-based text editing for `.txt`, `.md`, `.py`, `.html`  
- **Security**  
  - Path sanitization to prevent directory traversal  
  - Whitelisted file extensions  
  - Session management with `flask-login`

---

## 📦 Installation

1. Clone the repository  
   ```bash
   git clone https://github.com/wangyifan349/FlaskFileManager.git
   cd FlaskFileManager
   ```

2. (Optional) Create and activate a virtual environment  
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # Linux/macOS
   venv\Scripts\activate.bat     # Windows
   ```

3. Install dependencies  
   ```bash
   pip install Flask Flask-Login Werkzeug
   ```

---

## 🚀 Usage

1. Run the application  
   ```bash
   python app.py
   ```

2. Open your browser at  
   ```
   http://127.0.0.1:5000/register
   ```
   to create an account.

3. After registering, log in at  
   ```
   http://127.0.0.1:5000/login
   ```

4. You will be redirected to the file manager interface, where you can upload, download, rename, delete, play media, and edit text files.

---

## 📂 Project Structure

```
FlaskFileManager/
├── app.py              # Main Flask application (all backend logic)
├── uploads/            # Auto-created directory for storing user files
└── templates/          # HTML templates
    ├── base.html
    ├── login.html
    ├── register.html
    └── file_manager.html
```

- **app.py**  
  - Defines routes for authentication (`/register`, `/login`, `/logout`)  
  - Implements file management endpoints (`/upload`, `/mkdir`, `/rename`, `/delete`, `/download`, `/media`, `/edit`)  
  - Uses SQLite for user storage (`app.db`), automatically initialized on first run  
- **templates/**  
  - `base.html`: Common layout with Bootstrap & jQuery  
  - `login.html` / `register.html`: Simple forms for user auth  
  - `file_manager.html`: Main interface for browsing and managing files

---

## 🔧 Configuration

- **SECRET_KEY**  
  - Defined in `app.py` as `change-this-secret`.  
  - For production, set a strong secret key via environment variable or config file.  
- **UPLOAD_FOLDER**  
  - Located at `./uploads/`. Automatically created if missing.  
- **Allowed Extensions**  
  - Whitelisted in `app.py`:  
    ```python
    ALLOWED_EXT = {'txt','md','py','html','mp4','webm','mp3','wav','jpg','png'}
    ```

---

## ⚠️ Security Considerations

- **Path Sanitization**  
  - All file and directory operations use `safe_path()` to prevent escaping the upload directory.  
- **Password Storage**  
  - Passwords are hashed with `werkzeug.security.generate_password_hash`.  
- **File Validation**  
  - Uploads are validated against a whitelist of extensions.

---

## 📄 License

This project is released under the **GNU General Public License v3.0**.  
See the [LICENSE](LICENSE) file for full details.

---

Made with ❤️ by **wangyifan349**
