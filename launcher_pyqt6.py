import sys
import os
import json
import time
import requests
import zipfile
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QScrollArea, QStackedWidget,
    QFrame, QSizePolicy, QListWidget, QListWidgetItem, QSystemTrayIcon,
    QFileDialog, QDialog, QGroupBox, QLineEdit
)
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon, QPainter
from PyQt6.QtCore import (
    Qt, QThread, QObject, pyqtSignal, QSize, QTimer
)
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from pypresence import Presence
import psutil
import shutil
import tempfile
import socket
import webbrowser
import functools
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# =============================================================================
# CONFIGURACIÓN Y LÓGICA DE DATOS
# =============================================================================

# URL del archivo JSON remoto
JSON_URL = "https://traduction-club.live/api/winapp/proyectos.json"
# Nombre del archivo JSON local para cache
LOCAL_JSON_FILE = "proyectos_cache.json"
# Carpeta para guardar imágenes de portada
IMAGE_CACHE_DIR = "image_cache"
# Tiempo en segundos para considerar el cache como válido antes de re-verificar
CACHE_EXPIRY_TIME = 3600  # 1 hora
# Directorio para los juegos instalados
GAMES_INSTALL_DIR = "installed_games"
# Ubicación por defecto
LIBRARIES_FILE = "libraries.json"
# Archivo de configs
SETTINGS_FILE = "settings.json"

# def send_overlay_rect(x, y, w, h, r, g, b, a):
#     try:
#         s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         s.connect(('127.0.0.1', 54321))
#         cmd = f"draw_rect {x} {y} {w} {h} {r} {g} {b} {a}\n"
#         s.sendall(cmd.encode('utf-8'))
#         s.close()
#     except Exception as e:
#         print(f"Error enviando overlay: {e}")

# def inject_overlay_dll(process_name, dll_path):
#     try:
#         injector_path = os.path.join("overlay_native", "injector.exe")
#         # Llama al inyector y espera a que termine (puedes usar Popen si prefieres no bloquear)
#         subprocess.Popen([injector_path, process_name, dll_path])
#     except Exception as e:
#         print(f"Error al inyectar overlay: {e}")

# TOKEN
TOKEN_FILE = "user_token.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"overlay_enabled": True}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def save_token(token, username=None, avatar_url=None):
    data = {"token": token}
    if username:
        data["username"] = username
    if avatar_url:
        data["avatar_url"] = avatar_url
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("token")
    return None

def load_user_info():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("username"), data.get("avatar_url")
    return None, None

def clear_token():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)

def authenticate_user(username, password):
    url = "https://traduction-club.live/api/login/"
    try:
        response = requests.post(url, json={"username": username, "password": password}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("access"), data.get("username"), data.get("avatar_url")
        else:
            return None, None, None
    except Exception as e:
        print(f"Error autenticando: {e}")
        return None, None, None
    
def get_auth_headers():
    token = load_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def load_libraries():
    if os.path.exists(LIBRARIES_FILE):
        with open(LIBRARIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Por defecto, la carpeta de instalación
    default_library = os.path.abspath(GAMES_INSTALL_DIR)
    return [default_library]

def save_libraries(libraries):
    with open(LIBRARIES_FILE, "w", encoding="utf-8") as f:
        json.dump(libraries, f, indent=2)

def download_json(url):
    """Descargar el archivo JSON."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al descargar el JSON: {e}")
        return None

def get_local_json_version(filepath):
    """Obtener la versión del catálogo del archivo JSON local."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f).get("version_catalogo")
        except (json.JSONDecodeError, IOError):
            return None
    return None

def save_json_local(data, filepath):
    """Guardar los datos JSON en un archivo local."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error al guardar el JSON local: {e}")

def load_projects_data():
    """Cargar los datos de los proyectos, usando cache si es válido."""
    local_path = os.path.join(os.getcwd(), LOCAL_JSON_FILE)
    remote_data = download_json(JSON_URL)

    if remote_data:
        remote_version = remote_data.get("version_catalogo")
        local_version = get_local_json_version(local_path)
        if local_version and remote_version == local_version:
            if (time.time() - os.path.getmtime(local_path)) < CACHE_EXPIRY_TIME:
                print("Usando JSON local (caché válido).")
                with open(local_path, 'r', encoding='utf-8') as f:
                    return json.load(f)

        print("Usando JSON remoto (nuevo o actualizado).")
        save_json_local(remote_data, local_path)
        return remote_data
    else:
        print("Fallo en descarga remota. Intentando cargar desde caché local.")
        if os.path.exists(local_path):
            with open(local_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

def download_and_cache_image(image_url, project_id):
    """Descargar una imagen y la guarda en el caché si no existe."""
    if not image_url or not project_id:
        return None
    
    filename = f"{project_id}_{os.path.basename(image_url)}"
    safe_filename = "".join(c for c in filename if c.isalnum() or c in ['.', '_', '-']).rstrip()
    image_path = os.path.join(IMAGE_CACHE_DIR, safe_filename)

    if os.path.exists(image_path):
        return image_path

    try:
        response = requests.get(image_url, stream=True, timeout=15)
        response.raise_for_status()
        with open(image_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
        return image_path
    except requests.exceptions.RequestException as e:
        print(f"Error al descargar imagen {image_url}: {e}")
        return None

def select_library_dialog(self):
    libraries = load_libraries()
    # Mostrar un diálogo para elegir entre bibliotecas existentes o agregar nueva
    folder = QFileDialog.getExistingDirectory(self, "Selecciona una carpeta para la biblioteca")
    if folder:
        new_library = os.path.join(folder, "tradu-launcher-apps")
        os.makedirs(new_library, exist_ok=True)
        libraries.append(new_library)
        save_libraries(libraries)
        return new_library
    return None

# =============================================================================
# WORKER PARA TAREAS EN SEGUNDO PLANO
# =============================================================================

class DownloadWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    status = pyqtSignal(str)

    def __init__(self, project_data, install_dir):
        super().__init__()
        self.project_data = project_data
        self.install_dir = install_dir
        self._cancelled = False
        # self.sidebar = QListWidget()
        # self.sidebar.setObjectName("sidebar")
        # self.sidebar.setFixedWidth(220)
        # self.sidebar.itemClicked.connect(self.on_sidebar_item_clicked)
        # self.sidebar.itemDoubleClicked.connect(self.on_sidebar_item_double_clicked)
        # self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def cancel(self):
        self._cancelled = True

    def run(self):
        project_id = self.project_data.get("id_proyecto")
        download_url = self.project_data.get("url_descarga")
        if not project_id or not download_url:
            self.error.emit("Datos del proyecto incompletos.")
            return

        project_install_dir = os.path.join(self.install_dir, project_id)
        os.makedirs(project_install_dir, exist_ok=True)
        zip_filename = os.path.basename(download_url)
        zip_filepath = os.path.join(project_install_dir, zip_filename)

        try:
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            with open(zip_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._cancelled:
                        self.error.emit("Descarga cancelada por el usuario.")
                        try:
                            f.close()
                            os.remove(zip_filepath)
                        except Exception:
                            pass
                        return
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress_percentage = int((downloaded_size / total_size) * 100)
                        self.progress.emit(progress_percentage)
            self.progress.emit(100)
            self.status.emit("Extrayendo...")
            print(f"Extrayendo {zip_filepath}...")
            with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                zip_ref.extractall(project_install_dir)
            os.remove(zip_filepath)
            print("Extracción completa.")
            executable_path = os.path.join(project_install_dir, self.project_data['nombre_ejecutable'])
            self.finished.emit(executable_path)
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Error de descarga: {e}")
        except zipfile.BadZipFile:
            self.error.emit("Error: El archivo descargado no es un ZIP válido.")
        except Exception as e:
            self.error.emit(f"Error inesperado: {e}")


def refresh_access_token():
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
            refresh = data.get("refresh")
            if not refresh:
                return False
            try:
                resp = requests.post("https://traduction-club.live/api/token/refresh/", json={"refresh": refresh}, timeout=10)
                if resp.status_code == 200:
                    new_access = resp.json().get("access")
                    if new_access:
                        data["token"] = new_access
                        with open(TOKEN_FILE, "w") as f:
                            json.dump(data, f)
                        return True
            except Exception as e:
                print(f"Error refrescando token: {e}")
        return False


# =============================================================================
# INTERFAZ GRÁFICA (PyQt6)
# =============================================================================

class GameLauncherApp(QMainWindow):
    def __init__(self, projects_data):
        super().__init__()
        self.setWindowIcon(QIcon("icon.ico"))
        self.projects_data = projects_data
        self.current_project_id_in_detail_view = None
        self.currently_running_project_id = None
        self.thread = None
        self.worker = None
        self.discord_client_id = "1365476199777828978"
        self.rpc = None
        self.init_discord_rpc()
        self.settings = load_settings()

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("icon.png"))
        self.tray_icon.setVisible(True)

        # --- NAVBAR ---
        navbar = QWidget()
        navbar_layout = QHBoxLayout(navbar)
        navbar_layout.setContentsMargins(0, 0, 0, 0)
        navbar_layout.setSpacing(0)
        navbar.setObjectName("navbar")

        self.btn_library = QPushButton("Biblioteca")
        self.btn_library.setObjectName("navbarButton")
        self.btn_library.clicked.connect(self.show_library)

        self.btn_settings = QPushButton("Ajustes")
        self.btn_settings.setObjectName("navbarButton")
        self.btn_settings.clicked.connect(self.show_settings)

        self.btn_about = QPushButton("Acerca de")
        self.btn_about.setObjectName("navbarButton")
        self.btn_about.clicked.connect(self.show_about)

        self.btn_friends = QPushButton("Amigos")
        self.btn_friends.setObjectName("navbarButton")
        self.btn_friends.clicked.connect(self.show_friends)

        navbar_layout.addWidget(self.btn_library)
        navbar_layout.addWidget(self.btn_settings)
        navbar_layout.addWidget(self.btn_about)
        navbar_layout.addWidget(self.btn_friends)
        navbar_layout.addStretch()


        self.session_btn = QPushButton("Cerrar sesión")
        self.session_btn.setObjectName("navbarButton")
        self.session_btn.clicked.connect(self.logout)
        navbar_layout.addWidget(self.session_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.user_btn = QPushButton()
        self.user_btn.setObjectName("userButton")
        self.user_btn.setStyleSheet("""
            QPushButton#userButton {
                background: transparent;
                border: none;
                padding: 0 12px;
                min-width: 40px;
                min-height: 40px;
                border-radius: 20px;
                color: #cdd6f4;
                font-size: 15px;
                font-weight: bold;
                transition: background 0.2s;
            }
            QPushButton#userButton:hover {
                background: #313244;
                border: 1.5px solid #89b4fa;
                color: #89b4fa;
            }
        """)
        self.user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.user_btn.clicked.connect(self.show_account_details)
        username, avatar_url = load_user_info()
        if avatar_url:
            # Descarga el avatar si es necesario
            avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
            if avatar_path and os.path.exists(avatar_path):
                pixmap = QPixmap(avatar_path).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.user_btn.setIcon(QIcon(pixmap))
                self.user_btn.setIconSize(QSize(32, 32))
        if username:
            self.user_btn.setText(f"  {username}")
        navbar_layout.addWidget(self.user_btn, alignment=Qt.AlignmentFlag.AlignRight)
        navbar_layout.addWidget(self.session_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # --- Layout principal central ---
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        self.sidebar.itemClicked.connect(self.on_sidebar_item_clicked)
        self.sidebar.itemDoubleClicked.connect(self.on_sidebar_item_double_clicked)

        self.stacked_widget = QStackedWidget()

        # Páginas principales
        self.library_page = self._create_library_page()
        self.details_page = self._create_details_page()
        self.settings_page = self._create_settings_page()
        self.about_page = self._create_about_page()
        self.friends_page = self._create_friends_page()
        self.stacked_widget.addWidget(self.friends_page)
        self.stacked_widget.addWidget(self.library_page)
        self.stacked_widget.addWidget(self.details_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.stacked_widget.addWidget(self.about_page)

        # Layout vertical principal
        central_widget = QWidget()
        main_vlayout = QVBoxLayout(central_widget)
        main_vlayout.setContentsMargins(0, 0, 0, 0)
        main_vlayout.setSpacing(0)
        main_vlayout.addWidget(navbar)

        # Layout central para sidebar + contenido
        main_hlayout = QHBoxLayout()
        main_hlayout.setContentsMargins(0, 0, 0, 0)
        main_hlayout.setSpacing(0)
        main_hlayout.addWidget(self.sidebar)
        main_hlayout.addWidget(self.stacked_widget)
        main_vlayout.addLayout(main_hlayout)

        self.setCentralWidget(central_widget)

        # Para descargas activas
        self.active_downloads = {}  # {id_proyecto: {"thread": QThread, "worker": DownloadWorker, "progress": int, "error": str, "exe_path": str}}

        self.setWindowTitle("Tradu-Launcher")
        self.setGeometry(100, 100, 1100, 700)


        # Crear y añadir las dos vistas principales
        self.library_page = self._create_library_page()
        self.details_page = self._create_details_page()
        self.stacked_widget.addWidget(self.library_page)
        self.stacked_widget.addWidget(self.details_page)

        # Inicialmente, mostrar la biblioteca
        self.stacked_widget.setCurrentWidget(self.library_page)

        self.populate_sidebar()

        # Renderizar la biblioteca con los proyectos
        if self.projects_data and self.projects_data.get("proyectos"):
            for project in self.projects_data["proyectos"]:
                self._add_project_to_library(project)
        else:
            no_projects_label = QLabel("No se pudieron cargar los proyectos.")
            self.library_layout.addWidget(no_projects_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Buscar actualizaciones
        self.check_for_updates()
        self.migrate_installed_games_versions()
        self.update_my_status("Conectado")


    def update_my_status(self, status, game=None):
        data = {"status": status}
        if game:
            data["game"] = game
        self.api_post("https://traduction-club.live/api/friends/status/", data)

    def show_friends_window(self):
        friends = self.api_get("https://traduction-club.live/api/friends/list/")
        friends_data = friends.get("friends", []) if friends else []
        dlg = FriendsWindow(self, friends_data=friends_data)
        dlg.exec()

    def refresh_friends_page(self):
        self.friends_requests_received.clear()
        self.friends_requests_sent.clear()

        reqs = self.api_get("https://traduction-club.live/api/friends/requests/")
        if reqs:
            for req in reqs.get("received", []):
                username = req["from_user"]["username"]
                item = QListWidgetItem(username)
                avatar_url = req["from_user"].get("avatar_url")
                if avatar_url:
                    avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
                    if avatar_path and os.path.exists(avatar_path):
                        item.setIcon(QIcon(QPixmap(avatar_path).scaled(32, 32)))
                accept_btn = QPushButton("Aceptar")
                reject_btn = QPushButton("Rechazar")
                accept_btn.clicked.connect(functools.partial(self.respond_request, req["id"], "accept"))
                reject_btn.clicked.connect(functools.partial(self.respond_request, req["id"], "reject"))
                self.friends_requests_received.addItem(item)
                widget = QWidget()
                h = QHBoxLayout(widget)
                h.addWidget(accept_btn)
                h.addWidget(reject_btn)
                h.setContentsMargins(0,0,0,0)
                self.friends_requests_received.setItemWidget(item, widget)
            for req in reqs.get("sent", []):
                username = req["to_user"]["username"]
                item = QListWidgetItem(f"{username} (pendiente)")
                avatar_url = req["to_user"].get("avatar_url")
                if avatar_url:
                    avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
                    if avatar_path and os.path.exists(avatar_path):
                        item.setIcon(QIcon(QPixmap(avatar_path).scaled(32, 32)))
                self.friends_requests_sent.addItem(item)
    
    

    def api_get(self, url, params=None):
        try:
            headers = get_auth_headers()
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code == 401:
                if refresh_access_token():
                    headers = get_auth_headers()
                    r = requests.get(url, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API GET error: {e}")
            return None

    def api_post(self, url, data=None):
        try:
            headers = get_auth_headers()
            r = requests.post(url, headers=headers, json=data, timeout=10)
            if r.status_code == 401:
                if refresh_access_token():
                    headers = get_auth_headers()
                    r = requests.post(url, headers=headers, json=data, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API POST error: {e}")
            return None

    def refresh_friends_page(self):
        self.friends_requests_received.clear()
        self.friends_requests_sent.clear()

        reqs = self.api_get("https://traduction-club.live/api/friends/requests/")
        if reqs:
            for req in reqs.get("received", []):
                username = req["from_user"]["username"]
                item = QListWidgetItem(username)
                avatar_url = req["from_user"].get("avatar_url")
                if avatar_url:
                    avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
                    if avatar_path and os.path.exists(avatar_path):
                        item.setIcon(QIcon(QPixmap(avatar_path).scaled(32, 32)))
                accept_btn = QPushButton("Aceptar")
                reject_btn = QPushButton("Rechazar")
                accept_btn.clicked.connect(functools.partial(self.respond_request, req["id"], "accept"))
                reject_btn.clicked.connect(functools.partial(self.respond_request, req["id"], "reject"))
                self.friends_requests_received.addItem(item)
                widget = QWidget()
                h = QHBoxLayout(widget)
                h.addWidget(accept_btn)
                h.addWidget(reject_btn)
                h.setContentsMargins(0,0,0,0)
                self.friends_requests_received.setItemWidget(item, widget)
            for req in reqs.get("sent", []):
                username = req["to_user"]["username"]
                item = QListWidgetItem(f"{username} (pendiente)")
                avatar_url = req["to_user"].get("avatar_url")
                if avatar_url:
                    avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
                    if avatar_path and os.path.exists(avatar_path):
                        item.setIcon(QIcon(QPixmap(avatar_path).scaled(32, 32)))
                self.friends_requests_sent.addItem(item)

    def search_users(self):
        query = self.friends_search_input.text().strip()
        self.friends_search_results.clear()
        if not query:
            return
        my_username, _ = load_user_info()
        users = self.api_get("https://traduction-club.live/api/users/search/", params={"q": query})
        if not users:
            return
        if isinstance(users, dict) and "results" in users:
            user_list = users["results"]
        elif isinstance(users, list):
            user_list = users
        else:
            user_list = []
        for user in user_list:
            username = user["username"]
            if username == my_username:
                continue

            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(6, 2, 6, 2)
            layout.setSpacing(12)

            avatar_label = QLabel()
            avatar_url = user.get("avatar_url")
            if avatar_url:
                avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
                if avatar_path and os.path.exists(avatar_path):
                    pixmap = QPixmap(avatar_path).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    avatar_label.setPixmap(pixmap)
            avatar_label.setFixedSize(36, 36)
            layout.addWidget(avatar_label)

            name_label = QLabel(username)
            name_label.setStyleSheet("font-size: 15px; color: #cdd6f4;")
            layout.addWidget(name_label, stretch=1)

            add_btn = QPushButton("Agregar amigo")
            add_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e; border-radius: 8px; padding: 6px 16px; font-weight: bold;")
            add_btn.clicked.connect(functools.partial(self.send_friend_request, username))
            layout.addWidget(add_btn)

            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.friends_search_results.addItem(item)
            self.friends_search_results.setItemWidget(item, widget)

    def send_friend_request(self, username):
        resp = self.api_post("https://traduction-club.live/api/friends/request/", {"to_user": username})
        if resp and "detail" in resp:
            QMessageBox.information(self, "Solicitud enviada", resp["detail"])
        else:
            QMessageBox.information(self, "Solicitud enviada", "Solicitud de amistad enviada.")
        self.refresh_friends_page()

    def respond_request(self, request_id, action):
        url = f"https://traduction-club.live/api/friends/requests/{request_id}/{action}/"
        resp = self.api_post(url)
        if resp and "detail" in resp:
            QMessageBox.information(self, "Solicitud", resp["detail"])
        self.refresh_friends_page()

    def remove_friend(self, username):
        resp = self.api_post("https://traduction-club.live/api/friends/remove/", {"username": username})
        if resp and "detail" in resp:
            QMessageBox.information(self, "Amigos", resp["detail"])
        self.refresh_friends_page()

    def _create_friends_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # Buscador de usuarios
        search_layout = QHBoxLayout()
        self.friends_search_input = QLineEdit()
        self.friends_search_input.setPlaceholderText("Buscar usuario...")
        self.friends_search_btn = QPushButton("Buscar")
        self.friends_search_btn.clicked.connect(self.search_users)
        search_layout.addWidget(self.friends_search_input)
        search_layout.addWidget(self.friends_search_btn)
        layout.addLayout(search_layout)

        # Resultados de busqueda
        self.friends_search_results = QListWidget()
        layout.addWidget(QLabel("Resultados de búsqueda:"))
        layout.addWidget(self.friends_search_results)

        # Lista de amigos
        friends_btn = QPushButton("Ver lista de amigos")
        friends_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e; font-weight: bold; border-radius: 8px; padding: 10px;")
        friends_btn.clicked.connect(self.show_friends_window)
        layout.addWidget(friends_btn)


        # Solicitudes recibidas
        layout.addWidget(QLabel("Solicitudes recibidas:"))
        self.friends_requests_received = QListWidget()
        layout.addWidget(self.friends_requests_received)

        # Solicitudes enviadas
        layout.addWidget(QLabel("Solicitudes enviadas:"))
        self.friends_requests_sent = QListWidget()
        layout.addWidget(self.friends_requests_sent)

        return page

    def show_friends(self):
        self.refresh_friends_page()
        self.stacked_widget.setCurrentWidget(self.friends_page)
    
    def migrate_installed_games_versions(self):
        """
        Para cada juego instalado, si existe el ejecutable pero NO el version.txt,
        se pone el version.txt con la version del JSON.
        """
        if not self.projects_data or not self.projects_data.get("proyectos"):
            return
        for project in self.projects_data["proyectos"]:
            project_id = project.get("id_proyecto")
            exe_name = project.get("nombre_ejecutable")
            version = project.get("version")
            if not project_id or not exe_name or not version:
                continue
            for library in load_libraries():
                exe_path = os.path.join(library, project_id, exe_name)
                version_file = os.path.join(library, project_id, "version.txt")
                if os.path.exists(exe_path) and not os.path.exists(version_file):
                    try:
                        with open(version_file, "w", encoding="utf-8") as f:
                            f.write(str(version))
                        print(f"[DEBUG] Escrito version.txt para {project_id} en {version_file}")
                    except Exception as e:
                        print(f"[DEBUG] Error escribiendo version.txt para {project_id}: {e}")

    def show_account_details(self):
        username, avatar_url = load_user_info()
        dialog = QDialog(self)
        dialog.setWindowTitle("Detalles de la cuenta")
        layout = QVBoxLayout(dialog)
        if avatar_url:
            avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
            if avatar_path and os.path.exists(avatar_path):
                avatar_label = QLabel()
                avatar_label.setPixmap(QPixmap(avatar_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(avatar_label)
        layout.addWidget(QLabel(f"<b>Usuario:</b> {username}"))
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def logout(self):
        clear_token()
        QMessageBox.information(self, "Sesión cerrada", "Tu sesión ha sido cerrada.")
        self.close()
        python = sys.executable
        os.execl(python, python, *sys.argv)
    
    def check_for_updates(self, show_dialogs=False):
        UPDATE_INFO_URL = "https://traduction-club.live/api/winapp/launcher_update.json"
        try:
            info = requests.get(UPDATE_INFO_URL, timeout=10).json()
            latest_version = info["version"]
            download_url = info["installer_url"]
            if latest_version > self.get_current_version():
                reply = QMessageBox.question(
                    self,
                    "Actualización disponible",
                    f"Hay una nueva versión ({latest_version}). ¿Actualizar ahora?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.download_and_run_installer(download_url)
            else:
                if show_dialogs:
                    QMessageBox.information(
                        self,
                        "Sin actualizaciones",
                        f"Ya tienes la última versión ({self.get_current_version()})."
                    )
        except Exception as e:
            if show_dialogs:
                QMessageBox.warning(
                    self,
                    "Error de actualización",
                    f"No se pudo buscar actualizaciones: {e}"
                )

    def get_current_version(self):
        return "1.0"

    def download_and_run_installer(self, url):
        temp_dir = tempfile.gettempdir()
        installer_path = os.path.join(temp_dir, "launcher_update.msi")
        lock_path = os.path.join(temp_dir, "launcher_update.lock")
        with open(lock_path, "w") as f:
            f.write("LOCK")
        dialog = UpdateProgressDialog(self)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        dialog.show()
        QApplication.processEvents()
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(installer_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                percent = int(downloaded * 100 / total)
                                dialog.set_progress(percent)
                                QApplication.processEvents()
            dialog.set_label("Abriendo instalador...")
            dialog.set_progress(100)
            QApplication.processEvents()
            dialog.close()
            if os.path.exists(lock_path):
                os.remove(lock_path)
            QApplication.quit()
            subprocess.Popen(["msiexec", "/i", installer_path])
        except Exception as e:
            dialog.close()
            if os.path.exists(lock_path):
                os.remove(lock_path)
            QMessageBox.critical(self, "Error", f"No se pudo actualizar: {e}")
    
    def show_settings(self):
        self.stacked_widget.setCurrentWidget(self.settings_page)

    def show_about(self):
        self.stacked_widget.setCurrentWidget(self.about_page)

    def update_libraries_list(self):
        """Actualiza la lista de bibliotecas en la sección de ajustes."""
        if hasattr(self, 'libraries_list'):
            self.libraries_list.clear()
            self.libraries_list.addItems(load_libraries())

    def _create_settings_page(self):
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        label = QLabel("Ajustes")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setObjectName("settingsTitle")
        label.setStyleSheet("font-size: 26px; font-weight: bold; margin-bottom: 18px; color: #cdd6f4;")
        layout.addWidget(label)

        # --- Gestión de bibliotecas ---
        libraries_group = QGroupBox("Bibliotecas de juegos")
        libraries_group.setStyleSheet("QGroupBox { font-size: 18px; font-weight: bold; color: #89b4fa; border: 1px solid #45475a; border-radius: 8px; margin-top: 8px; padding: 12px; }")
        group_layout = QVBoxLayout(libraries_group)
        group_layout.setSpacing(10)

        self.libraries_list = QListWidget()
        self.libraries_list.addItems(load_libraries())
        self.libraries_list.setStyleSheet("background: #232634; color: #cdd6f4; border-radius: 6px; font-size: 15px;")
        group_layout.addWidget(self.libraries_list)

        btns_widget = QWidget()
        btns_layout = QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.setSpacing(10)

        remove_btn = QPushButton("Eliminar biblioteca seleccionada")
        remove_btn.setStyleSheet("background: #f38ba8; color: #fff; font-weight: bold; border-radius: 6px; padding: 8px 16px;")
        def remove_selected_library():
            selected = self.libraries_list.currentItem()
            if not selected:
                QMessageBox.warning(self, "Selecciona una biblioteca", "Selecciona una biblioteca para eliminar.")
                return
            library_path = selected.text()
            confirm = QMessageBox.question(
                self,
                "Eliminar biblioteca",
                f"¿Seguro que quieres eliminar la biblioteca?\nSe desinstalarán todos los juegos en esa carpeta.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                for folder in os.listdir(library_path):
                    full_path = os.path.join(library_path, folder)
                    if os.path.isdir(full_path):
                        try:
                            shutil.rmtree(full_path)
                        except Exception as e:
                            print(f"Error al eliminar {full_path}: {e}")
                libraries = load_libraries()
                libraries = [lib for lib in libraries if lib != library_path]
                save_libraries(libraries)
                self.update_libraries_list()
                self.populate_sidebar()  # Actualiza la barra lateral
                QMessageBox.information(self, "Biblioteca eliminada", "Biblioteca y juegos eliminados correctamente.")
        remove_btn.clicked.connect(remove_selected_library)
        btns_layout.addWidget(remove_btn)
        group_layout.addWidget(btns_widget)

        layout.addWidget(libraries_group)

        # --- Botón para abrir persistentes de RenPy ---
        renpy_group = QGroupBox("Persistentes de Ren'Py")
        renpy_group.setStyleSheet("QGroupBox { font-size: 18px; font-weight: bold; color: #89b4fa; border: 1px solid #45475a; border-radius: 8px; margin-top: 8px; padding: 12px; }")
        renpy_layout = QVBoxLayout(renpy_group)
        renpy_btn = QPushButton("Abrir carpeta de persistentes de Ren'Py")
        renpy_btn.setStyleSheet("background: #fab387; color: #1e1e2e; font-weight: bold; border-radius: 6px; padding: 8px 16px;")
        def open_renpy_persistent():
            renpy_path = os.path.expandvars(r"%appdata%\RenPy")
            if not os.path.exists(renpy_path):
                os.makedirs(renpy_path, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(renpy_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", renpy_path])
            else:
                subprocess.Popen(["xdg-open", renpy_path])
        renpy_btn.clicked.connect(open_renpy_persistent)
        renpy_layout.addWidget(renpy_btn)
        layout.addWidget(renpy_group)

        # --- Overlay toggle ---
        from PyQt6.QtWidgets import QCheckBox
        overlay_checkbox = QCheckBox("Activar overlay en los juegos (solo funciona en juegos con modo ventana)")
        overlay_checkbox.setChecked(self.settings.get("overlay_enabled", True))
        overlay_checkbox.setStyleSheet("font-size: 16px; color: #cdd6f4;")
        def on_overlay_toggle(state):
            self.settings["overlay_enabled"] = bool(state)
            save_settings(self.settings)
        overlay_checkbox.stateChanged.connect(on_overlay_toggle)
        layout.addWidget(overlay_checkbox)

        # --- Botón para buscar actualizaciones ---
        update_btn = QPushButton("Buscar actualizaciones")
        update_btn.setObjectName("updateButton")
        update_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e; font-weight: bold; border-radius: 6px; padding: 8px 16px;")
        update_btn.clicked.connect(lambda: self.check_for_updates(show_dialogs=True))
        layout.addWidget(update_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content_widget)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)
        return page

    def _create_about_page(self):
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        label = QLabel(
            "Acerca de<br>Tradu-Launcher<br>Versión 1.0<br><br>"
            "Traduction Club es un grupo de traducción y desarrollo de videojuegos (próximamente) sin fines de lucro.<br>"
            "No poseemos derechos sobre los materiales, juegos, imágenes o marcas mostradas en esta aplicación.<br>"
            "Todo el contenido pertenece a sus respectivos autores y propietarios legales.<br>"
            "Nuestra labor es completamente gratuita y colaborativa, sin obtener ningún beneficio económico.<br>"
            "Si eres propietario de algún contenido y deseas que sea retirado, por favor contáctanos a través de nuestra página web.<br><br>"
            'Sitio web: <a href="https://traduction-club.live/">https://traduction-club.live/</a><br>'
            "Contacto: soporte@traduction-club.live"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)  # Esto permite que el link sea clickeable
        layout.addWidget(label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content_widget)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)
        return page
    
    def init_discord_rpc(self):
        try:
            self.rpc = Presence(self.discord_client_id)
            self.rpc.connect()
            self.rpc.update(state="En el launcher", details="Explorando la biblioteca")
        except Exception as e:
            print(f"Error al conectar con Discord RPC: {e}")
    
    def populate_sidebar(self):
        self.sidebar.clear()
        if not self.projects_data or not self.projects_data.get("proyectos"):
            return
        for project in self.projects_data["proyectos"]:
            exe_path = self.check_if_game_installed(project)
            if exe_path:
                item = QListWidgetItem(project["titulo"])
                item.setData(Qt.ItemDataRole.UserRole, project["id_proyecto"])
                icon_path = None
                if project.get("icon"):
                    icon_path = download_and_cache_image(project["icon"], project["id_proyecto"] + "_icon")
                if icon_path and os.path.exists(icon_path):
                    item.setIcon(QIcon(icon_path))
                self.sidebar.addItem(item)
        self.update_sidebar_highlight()

    def update_sidebar_highlight(self):
        # Esto no funciona muy bien
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            pid = item.data(Qt.ItemDataRole.UserRole)
            if pid == self.currently_running_project_id:
                item.setBackground(Qt.GlobalColor.darkGreen)
                item.setForeground(Qt.GlobalColor.white)
            elif pid == self.current_project_id_in_detail_view:
                item.setBackground(Qt.GlobalColor.darkGray)
                item.setForeground(Qt.GlobalColor.white)
            else:
                item.setBackground(Qt.GlobalColor.transparent)
                item.setForeground(Qt.GlobalColor.white)

    def on_sidebar_item_clicked(self, item):
        pid = item.data(Qt.ItemDataRole.UserRole)
        for project in self.projects_data["proyectos"]:
            if project["id_proyecto"] == pid:
                self.show_project_details(project)
                self.update_sidebar_highlight()
                break

    def on_sidebar_item_double_clicked(self, item):
        pid = item.data(Qt.ItemDataRole.UserRole)
        for project in self.projects_data["proyectos"]:
            if project["id_proyecto"] == pid:
                exe_path = self.check_if_game_installed(project)
                if exe_path:
                    self.currently_running_project_id = pid
                    self.launch_game(exe_path)
                    self.update_sidebar_highlight()
                break

    def on_game_process_finished(self):
        self.currently_running_project_id = None
        self.update_sidebar_highlight()
        self.install_button.setText("Jugar")
        self.install_button.setEnabled(True)

    def uninstall_game(self, project_data):
        project_id = project_data.get("id_proyecto")
        # Busca en todas las bibliotecas
        removed = False
        for library in load_libraries():
            project_dir = os.path.join(library, project_id)
            if os.path.exists(project_dir):
                confirm = QMessageBox.question(self, "Desinstalar", f"¿Seguro que quieres desinstalar '{project_data['titulo']}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if confirm == QMessageBox.StandardButton.Yes:
                    try:
                        import shutil
                        shutil.rmtree(project_dir)
                        removed = True
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"No se pudo desinstalar: {e}")
                break
        if removed:
            QMessageBox.information(self, "Desinstalado", "Juego desinstalado correctamente.")
        self.show_project_details(project_data)
        self.populate_sidebar()

    def _create_library_page(self):
        """Crear el widget de la página de la biblioteca."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Biblioteca")
        title.setObjectName("pageTitle") # Para QSS
        layout.addWidget(title)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll_content = QWidget()
        self.library_layout = QVBoxLayout(self.scroll_content)
        self.library_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_area.setWidget(self.scroll_content)
        layout.addWidget(scroll_area)
        
        return page

    def _add_project_to_library(self, project_data):
        project_id = project_data['id_proyecto']
        image_path = download_and_cache_image(project_data['imagen_portada'], project_id)

        item_frame = QPushButton()
        item_frame.setObjectName("gameCard")
        item_frame.setMinimumHeight(150)
        item_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        item_frame.clicked.connect(lambda: self.show_project_details(project_data))

        item_layout = QHBoxLayout(item_frame)
        item_layout.setContentsMargins(18, 10, 18, 10)
        item_layout.setSpacing(18)

        # Imagen
        image_label = QLabel()
        image_label.setFixedSize(192, 108)
        image_label.setObjectName("gameImage")
        image_label.setStyleSheet("background: transparent;")

        if image_path:
            pixmap = QPixmap(image_path)
            target_size = image_label.size()
            transparent_pixmap = QPixmap(target_size)
            transparent_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(transparent_pixmap)
            scaled_pixmap = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (target_size.width() - scaled_pixmap.width()) // 2
            y = (target_size.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()
            image_label.setPixmap(transparent_pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Contenedor para el texto
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title_label = QLabel(project_data['titulo'])
        title_label.setObjectName("gameTitle")

        desc_label = QLabel(project_data['descripcion'])
        desc_label.setWordWrap(True)
        desc_label.setObjectName("gameDescription")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # desc_label.setMaximumHeight(60)

        text_layout.addWidget(title_label)
        text_layout.addWidget(desc_label)

        item_layout.addWidget(image_label)
        item_layout.addWidget(text_container, stretch=1)

        self.library_layout.addWidget(item_frame)

    def _create_details_page(self):
        # --- HEADER: Botón Volver ---
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        self.back_button = QPushButton("← Volver")
        self.back_button.setObjectName("backButton")
        self.back_button.clicked.connect(self.show_library)
        header_layout.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        header_layout.addStretch()

        self.locate_folder_button = QPushButton("Localizar carpeta del juego")
        self.locate_folder_button.setObjectName("locateFolderButton")
        self.locate_folder_button.setVisible(False)
        self.locate_folder_button.clicked.connect(self._on_locate_folder_clicked)
        header_layout.addWidget(self.locate_folder_button, alignment=Qt.AlignmentFlag.AlignRight)

        # --- SCROLLABLE CONTENT ---
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.detail_title = QLabel("Título")
        self.detail_title.setObjectName("detailTitle")
        self.detail_image = QLabel()
        self.detail_image.setFixedSize(640, 360)
        self.detail_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_desc = QLabel("Descripción...")
        self.detail_desc.setWordWrap(True)
        self.detail_desc.setObjectName("detailDescription")
        self.detail_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.size_label = QLabel("")
        self.size_label.setObjectName("sizeLabel")
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.size_label.setStyleSheet("""
            background-color: #fab387;
            color: #1e1e2e;
            font-size: 15px;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px 24px;
            margin: 12px 0px 0px 0px;
            border: none;
            max-width: 220px;
            min-width: 120px;
            qproperty-alignment: AlignCenter;
        """)

        content_layout.addWidget(self.detail_title, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.detail_image, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.detail_desc)
        content_layout.addWidget(self.size_label, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content_widget)

        # --- FOOTER: Botones y barra de progreso ---
        footer_widget = QWidget()
        footer_layout = QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(16)
        self.install_button = QPushButton("Instalar")
        self.install_button.setObjectName("installButton")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setVisible(False)
        self.uninstall_button = QPushButton("Desinstalar")
        self.uninstall_button.setObjectName("uninstallButton")
        self.uninstall_button.setVisible(False)
        buttons_layout.addWidget(self.install_button)
        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addWidget(self.uninstall_button)

        footer_layout.addWidget(self.progress_bar)
        footer_layout.addWidget(buttons_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # --- PAGE LAYOUT ---
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(header_widget)
        page_layout.addWidget(scroll_area, stretch=1)
        page_layout.addWidget(footer_widget)

        return page

    def check_if_game_installed(self, project_data):
        project_id = project_data.get("id_proyecto")
        exe_name = project_data.get("nombre_ejecutable")
        if not project_id or not exe_name:
            return None

        for library in load_libraries():
            executable_path = os.path.join(library, project_id, exe_name)
            if os.path.exists(executable_path):
                return executable_path
        return None
    
    def _on_locate_folder_clicked(self):
        if hasattr(self, "_current_exe_path") and self._current_exe_path:
            folder = os.path.dirname(self._current_exe_path)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

    def get_installed_game_version(self, project_id, library_path):
        version_file = os.path.join(library_path, project_id, "version.txt")
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None

    def show_project_details(self, project_data):
        self.current_project_id_in_detail_view = project_data['id_proyecto']
        self.detail_title.setText(project_data['titulo'])

        # Mostrar descripción principal
        desc = project_data.get('descripcion', '')

        custom_desc = project_data.get('custom_desc')
        if custom_desc:
            desc += "\n\n" + custom_desc

        self.detail_desc.setText(desc)

        tamano_gb = project_data.get('tamano_gb')
        if tamano_gb:
            self.size_label.setText(f"Tamaño de descarga: {tamano_gb} GB")
            self.size_label.setVisible(True)
        else:
            self.size_label.setVisible(False)

        image_path = download_and_cache_image(project_data['imagen_portada'], project_data['id_proyecto'])
        if image_path:
            pixmap = QPixmap(image_path)
            self.detail_image.setPixmap(pixmap.scaled(self.detail_image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        executable_path = self.check_if_game_installed(project_data)
        self._current_exe_path = executable_path
        installed_version = None
        for library in load_libraries():
            installed_version = self.get_installed_game_version(project_data['id_proyecto'], library)
            if installed_version:
                break
        remote_version = project_data.get("version")
        needs_update = installed_version and remote_version and installed_version != remote_version
        if executable_path:
            self.locate_folder_button.setVisible(True)
        else:
            self.locate_folder_button.setVisible(False)
        try:
            self.install_button.clicked.disconnect()
        except TypeError:
            pass
        try:
            self.cancel_button.clicked.disconnect()
        except TypeError:
            pass
        try:
            self.uninstall_button.clicked.disconnect()
        except TypeError:
            pass

        active = self.active_downloads.get(project_data['id_proyecto'])
        if active:
            self.install_button.setText("Descargando...")
            self.install_button.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(active.get("progress", 0))
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)
            self.cancel_button.clicked.connect(lambda: self.cancel_download(project_data['id_proyecto']))
            self.uninstall_button.setVisible(False)
        elif executable_path:
            if needs_update:
                self.install_button.setText("Actualizar")
                self.install_button.setEnabled(True)
                self.install_button.clicked.connect(lambda: self.update_game(project_data))
                self.cancel_button.setVisible(False)
                self.uninstall_button.setVisible(True)
                self.uninstall_button.setEnabled(True)
                self.uninstall_button.clicked.connect(lambda: self.uninstall_game(project_data))
            else:
                self.install_button.setText("Jugar")
                self.install_button.setEnabled(True)
                self.progress_bar.setVisible(False)
                self.install_button.clicked.connect(lambda: self.launch_game(executable_path))
                self.cancel_button.setVisible(False)
                self.uninstall_button.setVisible(True)
                self.uninstall_button.setEnabled(True)
                self.uninstall_button.clicked.connect(lambda: self.uninstall_game(project_data))
        else:
            self.install_button.setText("Instalar")
            self.install_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.install_button.clicked.connect(lambda: self.start_installation(project_data))
            self.cancel_button.setVisible(False)
            self.uninstall_button.setVisible(False)

        self.stacked_widget.setCurrentWidget(self.details_page)
    
    def update_game(self, project_data):
        self.start_installation(project_data)

    def cancel_download(self, project_id):
        active = self.active_downloads.get(project_id)
        if active:
            thread = active["thread"]
            worker = active["worker"]
            worker.cancel()
            thread.quit()
            thread.wait()
            project_install_dir = os.path.join(GAMES_INSTALL_DIR, project_id)
            for f in os.listdir(project_install_dir):
                if f.endswith(".zip"):
                    try:
                        os.remove(os.path.join(project_install_dir, f))
                    except Exception:
                        pass
            self.cleanup_download(project_id)
            self.progress_bar.setVisible(False)
            self.install_button.setText("Instalar")
            self.install_button.setEnabled(True)
            self.cancel_button.setVisible(False)

    def show_library(self):
        """Muestra la página de la biblioteca."""
        self.stacked_widget.setCurrentWidget(self.library_page)

    def start_installation(self, project_data):
        project_id = project_data['id_proyecto']
        if project_id in self.active_downloads:
            return  # Ya hay una descarga activa

        # Seleccionar biblioteca antes de instalar
        libraries = load_libraries()
        from PyQt6.QtWidgets import QInputDialog
        items = libraries + ["Agregar nueva ubicación..."]
        selected, ok = QInputDialog.getItem(self, "Seleccionar biblioteca", "Elige una ubicación para instalar el juego:", items, 0, False)
        if not ok:
            return

        if selected == "Agregar nueva ubicación...":
            folder = QFileDialog.getExistingDirectory(self, "Selecciona una carpeta para la nueva biblioteca")
            if not folder:
                return
            new_library = os.path.join(folder, "tradu-launcher-apps")
            os.makedirs(new_library, exist_ok=True)
            libraries.append(new_library)
            save_libraries(libraries)
            self.update_libraries_list()
            self.populate_sidebar()
            library_path = new_library
        else:
            library_path = selected

        self.install_button.setEnabled(False)
        self.install_button.setText("Descargando...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # Pasa la ruta de instalación al worker
        thread = QThread()
        worker = DownloadWorker(project_data, library_path)
        worker.moveToThread(thread)

        self.active_downloads[project_id] = {
            "thread": thread,
            "worker": worker,
            "progress": 0,
            "error": "",
            "exe_path": ""
        }

        thread.started.connect(worker.run)
        worker.finished.connect(lambda exe_path, pid=project_id: self.on_installation_finished(exe_path, pid))
        worker.error.connect(lambda msg, pid=project_id: self.on_installation_error(msg, pid))
        worker.progress.connect(lambda val, pid=project_id: self.on_installation_progress(val, pid))
        worker.status.connect(lambda msg, pid=project_id: self.on_installation_status(msg, pid))

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda pid=project_id: self.cleanup_download(pid))

        thread.start()

        if self.current_project_id_in_detail_view == project_id:
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)
            try:
                self.cancel_button.clicked.disconnect()
            except TypeError:
                pass
            self.cancel_button.clicked.connect(lambda: self.cancel_download(project_id))

    # --- slots para manejar las señales del worker ---

    def on_installation_status(self, msg, project_id):
        if self.current_project_id_in_detail_view == project_id:
            self.install_button.setText(msg)

    def cleanup_download(self, project_id):
        if project_id in self.active_downloads:
            del self.active_downloads[project_id]
    
    def on_installation_progress(self, value, project_id):
        if project_id in self.active_downloads:
            self.active_downloads[project_id]["progress"] = value
        if self.current_project_id_in_detail_view == project_id:
            self.progress_bar.setValue(value)
            self.progress_bar.setVisible(True)
            self.install_button.setText("Descargando...")
            self.install_button.setEnabled(False)

    def on_installation_finished(self, executable_path, project_id):
        print(f"Instalación finalizada. Ejecutable en: {executable_path}")
        if project_id in self.active_downloads:
            self.active_downloads[project_id]["exe_path"] = executable_path
        if self.current_project_id_in_detail_view == project_id:
            self.progress_bar.setVisible(False)
            self.install_button.setText("Jugar")
            self.install_button.setEnabled(True)
            self.cancel_button.setVisible(False)

            self.uninstall_button.setVisible(True)
            self.uninstall_button.setEnabled(True)
            try:
                self.uninstall_button.clicked.disconnect()
            except TypeError:
                pass
            current_project = None
            if self.projects_data and self.projects_data.get("proyectos"):
                for p in self.projects_data["proyectos"]:
                    if p["id_proyecto"] == project_id:
                        current_project = p
                        break
            if current_project:
                self.uninstall_button.clicked.connect(lambda: self.uninstall_game(current_project))

            try:
                self.install_button.clicked.disconnect()
            except TypeError:
                pass
            self.install_button.clicked.connect(lambda: self.launch_game(executable_path))
            self.locate_folder_button.setVisible(True)

        # notificación con icono dinámico
        project_title = None
        icon_path = None
        if self.projects_data and self.projects_data.get("proyectos"):
            for p in self.projects_data["proyectos"]:
                if p["id_proyecto"] == project_id:
                    project_title = p["titulo"]
                    # descargar y cachear el icono si existe
                    if p.get("icon"):
                        icon_path = download_and_cache_image(p["icon"], project_id + "_icon")
                    break
        if project_title:
            if icon_path and os.path.exists(icon_path):
                icon = QIcon(icon_path)
                self.tray_icon.showMessage(
                    "Instalación completada",
                    f"¡{project_title} está listo para jugar!",
                    icon,
                    5000
                )
            else:
                self.tray_icon.showMessage(
                    "Instalación completada",
                    f"¡{project_title} está listo para jugar!",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000
                )
        
        project = next((p for p in self.projects_data["proyectos"] if p["id_proyecto"] == project_id), None)
        if project and project.get("version"):
            for library in load_libraries():
                version_file = os.path.join(library, project_id, "version.txt")
                if os.path.exists(os.path.join(library, project_id)):
                    with open(version_file, "w", encoding="utf-8") as f:
                        f.write(str(project["version"]))

        self.populate_sidebar()

    def on_installation_error(self, message, project_id):
        print(f"Error de instalación: {message}")
        if project_id in self.active_downloads:
            self.active_downloads[project_id]["error"] = message
        if self.current_project_id_in_detail_view == project_id:
            self.progress_bar.setVisible(False)
            self.install_button.setText(f"Error: Reintentar")
            self.install_button.setEnabled(True)

    def launch_game(self, executable_path):
        try:
            abs_executable_path = os.path.abspath(executable_path)
            norm_executable_path = os.path.normpath(abs_executable_path)
            game_dir = os.path.dirname(norm_executable_path)
            exe_name = os.path.basename(norm_executable_path)
            print(f"Lanzando {norm_executable_path} en el directorio {game_dir}")
            if not os.path.exists(norm_executable_path):
                print(f"Error: El archivo ejecutable NO EXISTE en {norm_executable_path}")
                self.install_button.setText("Ejecutable no encontrado")
                self.install_button.setEnabled(False)
                return
            process = subprocess.Popen([norm_executable_path], cwd=game_dir)

            # if self.settings.get("overlay_enabled", True):
            #     overlay_path = os.path.abspath("overlay.py")
            #     python_exe = sys.executable
            #     self.overlay_process = subprocess.Popen([python_exe, overlay_path, exe_name])

            if self.settings.get("overlay_enabled", True):
                overlay_path = os.path.abspath("overlay.exe")
                self.overlay_process = subprocess.Popen([overlay_path, exe_name])

            self.install_button.setText("Ejecutando...")
            self.install_button.setEnabled(False)

            self.game_monitor_thread = QThread()
            self.game_monitor_worker = GameProcessMonitor(process, exe_name)
            self.game_monitor_worker.moveToThread(self.game_monitor_thread)
            self.game_monitor_thread.started.connect(self.game_monitor_worker.run)
            self.game_monitor_worker.finished.connect(self.on_game_process_finished)
            self.game_monitor_worker.finished.connect(self.game_monitor_thread.quit)
            self.game_monitor_worker.finished.connect(self.game_monitor_worker.deleteLater)
            self.game_monitor_thread.finished.connect(self.game_monitor_thread.deleteLater)
            self.game_monitor_thread.start()
        except Exception as e:
            print(f"Error al lanzar el juego: {e}")
            self.install_button.setText("Error al lanzar")
            self.install_button.setEnabled(False)

        project = None
        for p in self.projects_data["proyectos"]:
            if self.current_project_id_in_detail_view == p["id_proyecto"]:
                project = p
                break
        if project:
            self.update_my_status("En juego", project["titulo"])
        if self.rpc and project:
            try:
                self.rpc.update(
                    state=f"Jugando: {project['titulo']}",
                    details="En juego",
                    large_image="logo",
                    start=int(time.time()),
                    buttons=[{"label": "Página Web", "url": "https://traduction-club.live/"}]
                )
            except Exception as e:
                print(f"Error al actualizar Rich Presence: {e}")

    def on_game_process_finished(self):
        if hasattr(self, "overlay_process") and self.overlay_process and self.overlay_process.poll() is None:
            try:
                self.overlay_process.terminate()
            except Exception as e:
                print(f"Error cerrando overlay: {e}")
            self.overlay_process = None
        
        self.update_my_status("Conectado")

        # restaurar el botón "Jugar" cuando el juego se cierre
        self.install_button.setText("Jugar")
        self.install_button.setEnabled(True)
        if self.rpc:
            try:
                self.rpc.update(
                    state="En el launcher", 
                    details="Explorando la biblioteca",
                    buttons=[{"label": "Página Web", "url": "https://traduction-club.live/"}]
                )
            except Exception as e:
                print(f"Error al actualizar Rich Presence: {e}")

    def closeEvent(self, event):
        try:
            self.update_my_status("Desconectado")
        except Exception as e:
            print(f"Error al actualizar estado a Desconectado: {e}")
        super().closeEvent(event)

# =============================================================================
# MONITOR DE JUEGOS
# =============================================================================
class GameProcessMonitor(QObject):
    started = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, process, exe_name):
        super().__init__()
        self.process = process
        self.exe_name = exe_name

    def run(self):
        self.started.emit()
        self.process.wait()
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and self.exe_name.lower() in proc.info['name'].lower():
                    proc.wait()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self.finished.emit()

# =============================================================================
# ANIMACIONES (en un futuro)
# =============================================================================
def fade_in_widget(widget, duration=500):
    effect = QGraphicsOpacityEffect()
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(0)
    anim.setEndValue(1)
    anim.start()
    widget._fade_anim = anim

# =============================================================================
# GESTOR DE UPDATES
# =============================================================================
class UpdateProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Actualizando Tradu-Launcher")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        layout = QVBoxLayout(self)
        self.label = QLabel("Descargando actualización...")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        self.setFixedSize(400, 120)

    def set_progress(self, value):
        self.progress.setValue(value)

    def set_label(self, text):
        self.label.setText(text)

# =============================================================================
# GESTOR DE CUENTAS
# =============================================================================
class LoginWidget(QWidget):
    login_success = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #1e1e2e;")

        self.title = QLabel("Iniciar sesión en Tradu-Launcher")
        self.title.setStyleSheet("font-size: 22px; font-weight: bold; color: #cdd6f4;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Usuario")
        self.user_input.setStyleSheet("font-size: 16px; padding: 8px;")
        layout.addWidget(self.user_input)

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Contraseña")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setStyleSheet("font-size: 16px; padding: 8px;")
        layout.addWidget(self.pass_input)

        self.login_btn = QPushButton("Iniciar sesión")
        self.login_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e; font-weight: bold; border-radius: 8px; padding: 10px;")
        self.login_btn.clicked.connect(self.try_login)
        layout.addWidget(self.login_btn)

        self.error_label = QLabel("o")
        self.error_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.error_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.web_login_btn = QPushButton("Iniciar sesión en la web")
        self.web_login_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e; font-weight: bold; border-radius: 8px; padding: 10px;")
        self.web_login_btn.clicked.connect(self.web_login)
        layout.addWidget(self.web_login_btn)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f38ba8; font-size: 14px;")
        layout.addWidget(self.error_label)

        self.register_btn = QPushButton("Registrarse en la web")
        self.register_btn.setStyleSheet("background: #fab387; color: #1e1e2e; font-weight: bold; border-radius: 8px; padding: 8px;")
        self.register_btn.clicked.connect(lambda: webbrowser.open("https://traduction-club.live/signup/"))
        layout.addWidget(self.register_btn)

    def get_user_info_from_token(self, token):
        try:
            resp = requests.get(
                "https://traduction-club.live/api/userinfo/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("username"), data.get("avatar_url")
        except Exception as e:
            print(f"Error obteniendo info de usuario: {e}")
        return None

    def web_login(self):
        port = 54321
        server = start_token_server(port)
        login_url = f"https://traduction-club.live/accounts/launcher-login/?redirect_uri=http://localhost:{port}/"
        webbrowser.open(login_url)
        token, username, avatar_url = wait_for_token(timeout=120)
        server.shutdown()
        if token:
            if username:
                self.login_success.emit((token, username, avatar_url))
            else:
                self.error_label.setText("No se recibió el usuario. Intenta de nuevo.")
        else:
            self.error_label.setText("No se recibió el token. Intenta de nuevo.")

    def try_login(self):
        username_input = self.user_input.text().strip()
        password = self.pass_input.text().strip()
        self.error_label.setText("")
        if not username_input or not password:
            self.error_label.setText("Completa usuario y contraseña.")
            return
        token, username, avatar_url = authenticate_user(username_input, password)
        print("DEBUG login:", token, username, avatar_url)
        if token:
            # Si username es None, usa el que escribió el usuario
            if not username:
                username = username_input
            self.login_success.emit((token, username, avatar_url))
        else:
            self.error_label.setText("Usuario o contraseña incorrectos.")

class TokenHandler(BaseHTTPRequestHandler):
    token = None
    username = None
    avatar_url = None
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs, unquote
        qs = parse_qs(urlparse(self.path).query)
        if "token" in qs:
            TokenHandler.token = qs["token"][0]
            TokenHandler.username = qs.get("username", [None])[0]
            TokenHandler.avatar_url = qs.get("avatar_url", [None])[0]
            if TokenHandler.avatar_url:
                TokenHandler.avatar_url = unquote(TokenHandler.avatar_url)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Login exitoso. Puedes cerrar esta ventana y volver al launcher.</h2></body></html>")
            import threading
            threading.Timer(5.0, self.server.shutdown).start()
        elif self.path.startswith("/favicon.ico"):
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(400)
            self.end_headers()

def start_token_server(port=54321):
    TokenHandler.token = None
    server = HTTPServer(("localhost", port), TokenHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

def wait_for_token(timeout=360):
    import time
    start = time.time()
    while TokenHandler.token is None and (time.time() - start) < timeout:
        time.sleep(0.5)
    return TokenHandler.token, TokenHandler.username, TokenHandler.avatar_url

# =============================================================================
# VENTANA DE AMIGOS
# =============================================================================
class FriendsWindow(QDialog):
    def __init__(self, parent=None, friends_data=None):
        super().__init__(parent)
        self.setWindowTitle("Amigos")
        self.setMinimumSize(350, 500)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setSpacing(10)
        vbox.setContentsMargins(10, 10, 10, 10)

        # friends_data: lista de dicts con username, avatar_url, status, game
        if friends_data:
            for friend in friends_data:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                # Avatar
                avatar = QLabel()
                avatar.setFixedSize(36, 36)
                avatar_path = download_and_cache_image(friend.get("avatar_url"), f"{friend['username']}_avatar")
                if avatar_path and os.path.exists(avatar_path):
                    pixmap = QPixmap(avatar_path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    avatar.setPixmap(pixmap)
                row_layout.addWidget(avatar)
                # Nombre y estado
                info = QLabel(f"{friend['username']}\n{friend.get('status', 'Desconectado')}")
                info.setStyleSheet("font-size: 15px; color: #cdd6f4;")
                row_layout.addWidget(info, stretch=1)
                # Juego actual
                game = QLabel(friend.get("game", ""))
                game.setStyleSheet("font-size: 13px; color: #a6e3a1;")
                row_layout.addWidget(game)
                vbox.addWidget(row)
        else:
            vbox.addWidget(QLabel("No tienes amigos aún."))

        content.setLayout(vbox)
        scroll.setWidget(content)
        layout.addWidget(scroll)

# =============================================================================
# MIGRACION MOMENTANEA PARA EL CAMBIO DE VERSION DE LAUNCHER Y EXTENDER
# COMPATIBILIDAD ENTRE VERIONES DEL MISMO
# =============================================================================
def migrate_installed_games_versions(self):
    """
    Para cada juego instalado, si existe el ejecutable pero NO el version.txt,
    se pone el version.txt con la version del JSON.
    """
    if not self.projects_data or not self.projects_data.get("proyectos"):
        return
    for project in self.projects_data["proyectos"]:
        project_id = project.get("id_proyecto")
        exe_name = project.get("nombre_ejecutable")
        version = project.get("version")
        if not project_id or not exe_name or not version:
            continue
        for library in load_libraries():
            exe_path = os.path.join(library, project_id, exe_name)
            version_file = os.path.join(library, project_id, "version.txt")
            if os.path.exists(exe_path) and not os.path.exists(version_file):
                try:
                    with open(version_file, "w", encoding="utf-8") as f:
                        f.write(str(version))
                    print(f"[DEBUG] Escrito version.txt para {project_id} en {version_file}")
                except Exception as e:
                    print(f"[DEBUG] Error escribiendo version.txt para {project_id}: {e}")

# =============================================================================
# ESTILOS (QSS) Y EL def main()
# =============================================================================

STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}
#pageTitle, #detailTitle {
    color: #cdd6f4;
    font-size: 24px;
    font-weight: bold;
    padding: 10px;
}
#detailTitle {
    font-size: 30px;
}
QScrollArea {
    border: none;
}
#gameCard {
    background-color: #313244;
    border-radius: 8px;
    border: 1px solid #45475a;
    text-align: left;
    padding: 10px;
    margin: 5px 10px;
}
#gameCard:hover {
    background-color: #45475a;
    border: 1px solid #89b4fa;
}
#gameTitle {
    color: #cdd6f4;
    font-size: 16px;
    font-weight: bold;
}
#gameDescription, QLabel {
    color: #bac2de;
    font-size: 13px;
}
#gameImage {
    background-color: #11111b;
    border-radius: 4px;
}
#installButton, #backButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-size: 16px;
    font-weight: bold;
    border-radius: 8px;
    padding: 10px;
    border: none;
}
#installButton:hover, #backButton:hover {
    background-color: #74c7ec;
}
#installButton:disabled {
    background-color: #585b70;
    color: #a6adc8;
}
#cancelButton {
    background-color: #f38ba8;
    color: #fff;
    font-size: 16px;
    font-weight: bold;
    border-radius: 8px;
    padding: 10px;
    border: none;
}
#cancelButton:hover {
    background-color: #eba0ac;
}
#uninstallButton {
    background-color: #fab387;
    color: #fff;
    font-size: 16px;
    font-weight: bold;
    border-radius: 8px;
    padding: 10px;
    border: none;
}
#uninstallButton:hover {
    background-color: #f9e2af;
    color: #1e1e2e;
}
#backButton {
    background-color: #45475a;
    color: #cdd6f4;
    max-width: 200px;
}
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 5px;
    text-align: center;
    color: #cdd6f4;
    background-color: #313244;
}
QProgressBar::chunk {
    background-color: #a6e3a1;
    border-radius: 5px;
}
#gameDescription, #detailDescription {
    color: #bac2de;
    font-size: 13px;
    text-align: center;
    padding-left: 32px;
    padding-right: 32px;
}
#sidebar {
    background-color: #232634;
    border-right: 1px solid #45475a;
    color: #cdd6f4;
    font-size: 15px;
    outline: none;
}
QListWidget#sidebar::item:selected {
    background: #585b70;
    color: #a6e3a1;
}
QListWidget#sidebar::item {
    padding: 10px 16px;
    border-radius: 4px;
}
#navbar {
    background-color: #181825;
    border-bottom: 1px solid #45475a;
}
#navbarButton {
    background: transparent;
    color: #cdd6f4;
    font-size: 16px;
    font-weight: bold;
    border: none;
    padding: 14px 32px;
}
#navbarButton:hover {
    background: #313244;
    color: #89b4fa;
}
"""

def main():

    def on_login_success(user_data):
        token, username, avatar_url = user_data
        save_token(token, username, avatar_url)
        login_widget.close()
        projects_data = load_projects_data()
        window = GameLauncherApp(projects_data)
        window.show()
    # Crear directorios necesarios
    for dir_path in [IMAGE_CACHE_DIR, GAMES_INSTALL_DIR]:
        os.makedirs(dir_path, exist_ok=True)

    temp_dir = tempfile.gettempdir()
    update_lock_path = os.path.join(temp_dir, "launcher_update.lock")
    if os.path.exists(update_lock_path):
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "Actualización en curso", "El launcher se está actualizando. Por favor, espera a que termine la instalación antes de volver a abrirlo.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    token = load_token()
    if not token:
        login_widget = LoginWidget()
        login_widget.show()
        login_widget.login_success.connect(on_login_success)
        sys.exit(app.exec())
    else:
        projects_data = load_projects_data()
        window = GameLauncherApp(projects_data)
        window.show()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
