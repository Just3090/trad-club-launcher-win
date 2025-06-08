import sys
import time
import win32gui
import win32ui
import win32con
import win32process
import win32api
from PIL import Image
import keyboard
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QDialog, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QPixmap, QImage
import ctypes
import os
import json
import datetime
import shutil
import subprocess

SCREENSHOTS_DIR = "screenshots"

def load_user_info():
    if os.path.exists("user_token.json"):
        with open("user_token.json", "r") as f:
            data = json.load(f)
            return data.get("username"), data.get("avatar_url")
    return None, None

def download_and_cache_image(image_url, cache_name):
    if not image_url:
        return None
    filename = f"{cache_name}_{os.path.basename(image_url)}"
    safe_filename = "".join(c for c in filename if c.isalnum() or c in ['.', '_', '-']).rstrip()
    image_path = os.path.join("image_cache", safe_filename)
    if os.path.exists(image_path):
        return image_path
    try:
        import requests
        response = requests.get(image_url, stream=True, timeout=15)
        response.raise_for_status()
        with open(image_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
        return image_path
    except Exception as e:
        print(f"Error al descargar avatar: {e}")
        return None

def find_game_window(exe_name):
    hwnds = []
    def enum_windows_callback(hwnd, result):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if win32gui.IsWindowVisible(hwnd):
            try:
                process_handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
                exe_path = win32process.GetModuleFileNameEx(process_handle, 0)
                exe_base = exe_path.split("\\")[-1]
                win32api.CloseHandle(process_handle)
            except Exception:
                exe_base = ""
            title = win32gui.GetWindowText(hwnd)
            if exe_name.lower() in exe_base.lower() or exe_name.lower() in title.lower():
                result.append(hwnd)
    win32gui.EnumWindows(enum_windows_callback, hwnds)
    return hwnds[0] if hwnds else None

def capture_window(hwnd, save_path):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
    saveDC.SelectObject(saveBitMap)
    saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
    img.save(save_path)
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

def get_foreground_window():
    return win32gui.GetForegroundWindow()

class Overlay(QWidget):
    def __init__(self, hwnd, game_name="Juego"):
        super().__init__()
        self.hwnd = hwnd
        self.game_name = game_name
        self.session_start_time = time.time()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(1.0)
        if hwnd:
            self.setGeometry(*win32gui.GetWindowRect(hwnd))
        else:
            self.setGeometry(100, 100, 800, 400)
        self.timer = QTimer()
        if hwnd:
            self.timer.timeout.connect(self.follow_game_window)
            self.timer.start(500)

        self.focus_timer = QTimer()
        self.focus_timer.timeout.connect(self.check_game_focus)
        self.focus_timer.start(300)

        self.setStyleSheet("background-color: rgba(255,0,0,0.3);")

        # Mensaje tipo Steam en la esquina inferior izquierda
        self.message_label = QLabel("✔ Overlay de Tradu-Launcher iniciado correctamente.\nUsa Shift+F4 para abrir y cerrarlo.", self)
        self.message_label.setStyleSheet("""
            QLabel {
                color: #e6e6e6;
                background-color: rgba(24, 26, 32, 240);
                border-radius: 14px;
                font-size: 22px;
                font-weight: bold;
                padding: 22px 48px;
                border: 2px solid #89b4fa;
                min-width: 360px;
            }
        """)
        self.message_label.adjustSize()
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.message_label.setVisible(True)
        self.position_message_steam_style()

        self.fade_in_message()
        QTimer.singleShot(4000, self.fade_out_message)

        # --- Overlay tipo Steam ---
        self.steam_overlay = QWidget(self)
        self.steam_overlay.setStyleSheet("background-color: rgba(30, 30, 40, 0.95); border-radius: 0px")
        self.steam_overlay.setGeometry(0, 0, self.width(), self.height())
        self.steam_overlay.setVisible(False)

        # Etiqueta de nombre del juego y tiempo de sesión
        self.session_label = QLabel(self.steam_overlay)
        self.session_label.setStyleSheet("""
            QLabel {
                color: #89b4fa;
                background: transparent;
                font-size: 22px;
                font-weight: bold;
                padding: 12px 24px;
            }
        """)
        self.session_label.move(24, 18)
        self.session_label.setText(f"{self.game_name} - Tiempo: 00:00:00")
        self.session_label.show()

        # Timer para actualizar el tiempo de sesión
        self.session_timer = QTimer()
        self.session_timer.timeout.connect(self.update_session_time)
        self.session_timer.start(1000)

        # Botón de cerrar (tachita)
        self.close_btn = QPushButton("✕", self.steam_overlay)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #f38ba8;
                font-size: 28px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                color: #eba0ac;
            }
        """)
        self.close_btn.setFixedSize(40, 40)
        self.close_btn.move(self.steam_overlay.width() - 48, 8)
        self.close_btn.clicked.connect(self.toggle_steam_overlay)

        # Ajustar tamaño de la overlay al redimensionar
        self.steam_overlay.resizeEvent = self._steam_overlay_resize_event

        # Registrar hotkey Shift+F4
        keyboard.add_hotkey('shift+f4', self.toggle_steam_overlay)

        self.show()
        self.raise_()
        self.activateWindow()

        hwnd_overlay = int(self.winId())
        win32gui.SetWindowPos(
            hwnd_overlay,
            win32con.HWND_TOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
        )

        username, avatar_url = load_user_info()
        self.account_widget = QWidget(self.steam_overlay)
        self.account_widget.setGeometry(self.steam_overlay.width() - 260, 10, 250, 56)
        self.account_widget.setStyleSheet("background: transparent;")
        self.avatar_label = QLabel(self.account_widget)
        self.avatar_label.setGeometry(0, 0, 48, 48)
        self.avatar_label.setStyleSheet("border-radius: 24px; background: #232634;")
        if avatar_url:
            os.makedirs("image_cache", exist_ok=True)
            avatar_path = download_and_cache_image(avatar_url, f"{username}_avatar")
            if avatar_path and os.path.exists(avatar_path):
                pixmap = QPixmap(avatar_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.avatar_label.setPixmap(pixmap)
        self.name_label = QLabel(self.account_widget)
        self.name_label.setGeometry(56, 0, 180, 48)
        self.name_label.setStyleSheet("color: #cdd6f4; font-size: 18px; font-weight: bold; background: transparent;")
        if username:
            self.name_label.setText(username)
        self.account_widget.show()

        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

        # Hotkey para capturas
        keyboard.add_hotkey('f12', self.take_screenshot)

        # Aviso de captura
        self.screenshot_notice = QLabel(self)
        self.screenshot_notice.setStyleSheet("""
            QLabel {
                color: #e6e6e6;
                background-color: rgba(24, 26, 32, 240);
                border-radius: 14px;
                font-size: 18px;
                font-weight: bold;
                padding: 12px 24px;
                border: 2px solid #89b4fa;
                min-width: 220px;
            }
        """)
        self.screenshot_notice.setVisible(False)

        # Botón galería
        self.gallery_btn = QPushButton("📷 Capturas", self.steam_overlay)
        self.gallery_btn.setStyleSheet("""
            QPushButton {
                background: #313244;
                color: #89b4fa;
                font-size: 18px;
                border-radius: 18px;
                padding: 8px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #45475a;
            }
        """)
        self.gallery_btn.clicked.connect(self.show_screenshot_gallery)
        self.gallery_widget = QWidget(self.steam_overlay)
        self.gallery_widget.setStyleSheet("background: rgba(24,26,32,230); border-radius: 18px;")
        self.gallery_widget.setGeometry(
            (self.width() - 600) // 2, (self.height() - 420) // 2, 600, 420
        )
        self.gallery_widget.setVisible(False)

        self.gallery_layout = QVBoxLayout(self.gallery_widget)
        self.gallery_pixmap = QLabel()
        self.gallery_pixmap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gallery_pixmap.setFixedSize(480, 270)
        self.gallery_layout.addWidget(self.gallery_pixmap)

        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("<== Anterior")
        self.next_btn = QPushButton("Siguiente ==>")
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        self.gallery_layout.addLayout(nav_layout)

        btns = QHBoxLayout()
        self.open_btn = QPushButton("Abrir ubicación")
        self.delete_btn = QPushButton("Eliminar")
        btns.addWidget(self.open_btn)
        btns.addWidget(self.delete_btn)
        self.gallery_layout.addLayout(btns)

        self.gallery_files = []
        self.gallery_index = 0

        self.prev_btn.clicked.connect(self.gallery_prev)
        self.next_btn.clicked.connect(self.gallery_next)
        self.open_btn.clicked.connect(self.gallery_open)
        self.delete_btn.clicked.connect(self.gallery_delete)

    def show_screenshot_gallery(self):
        # Carga archivos y muestra la galería
        self.gallery_files = sorted(
            [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith(".png")], reverse=True
        )
        if not self.gallery_files:
            self.gallery_pixmap.setText("No hay capturas.")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.open_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
        else:
            self.gallery_index = 0
            self.update_gallery_image()
            self.prev_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.open_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
        self.gallery_widget.setVisible(True)
    
    def update_gallery_image(self):
        if not self.gallery_files:
            self.gallery_pixmap.setText("No hay capturas.")
            return
        img_path = os.path.join(SCREENSHOTS_DIR, self.gallery_files[self.gallery_index])
        pix = QPixmap(img_path).scaled(480, 270, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.gallery_pixmap.setPixmap(pix)

    def gallery_prev(self):
        if self.gallery_files:
            self.gallery_index = (self.gallery_index - 1) % len(self.gallery_files)
            self.update_gallery_image()

    def gallery_next(self):
        if self.gallery_files:
            self.gallery_index = (self.gallery_index + 1) % len(self.gallery_files)
            self.update_gallery_image()

    def gallery_open(self):
        if self.gallery_files:
            path = os.path.abspath(os.path.join(SCREENSHOTS_DIR, self.gallery_files[self.gallery_index]))
            if sys.platform == "win32":
                os.startfile(os.path.dirname(path))
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def gallery_delete(self):
        if self.gallery_files:
            path = os.path.join(SCREENSHOTS_DIR, self.gallery_files[self.gallery_index])
            os.remove(path)
            del self.gallery_files[self.gallery_index]
            if not self.gallery_files:
                self.gallery_pixmap.setText("No hay capturas.")
                self.gallery_widget.setVisible(False)
            else:
                self.gallery_index %= len(self.gallery_files)
                self.update_gallery_image()

    def update_session_time(self):
        elapsed = int(time.time() - self.session_start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        self.session_label.setText(f"{self.game_name} - Tiempo: {hours:02}:{minutes:02}:{seconds:02}")
    
    def _steam_overlay_resize_event(self, event):
        self.close_btn.move(self.steam_overlay.width() - 48, 8)

    def toggle_steam_overlay(self):
        visible = self.steam_overlay.isVisible()
        self.steam_overlay.setVisible(not visible)
        if not visible:
            self.steam_overlay.raise_()
            self.close_btn.setFocus()

    def check_game_focus(self):
        fg_hwnd = get_foreground_window()
        overlay_hwnd = int(self.winId())
        if fg_hwnd == self.hwnd or fg_hwnd == overlay_hwnd:
            if not self.isVisible():
                self.show()
        else:
            if self.isVisible():
                self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.gallery_widget.isVisible():
            self.gallery_widget.setVisible(False)
        else:
            super().keyPressEvent(event)

    def position_message_steam_style(self):
        rect = self.geometry()
        w = self.message_label.width()
        h = self.message_label.height()
        margin_x = 36
        margin_y = 36
        self.message_label.move(
            margin_x,
            rect.height() - h - margin_y
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_message_steam_style()
        if hasattr(self, "account_widget"):
            self.account_widget.move(self.steam_overlay.width() - 750, 10)
        self.steam_overlay.setGeometry(0, 0, self.width(), self.height())
        if hasattr(self, "gallery_btn"):
            self.gallery_btn.move((self.width() - self.gallery_btn.width()) // 2, self.height() - 60)
        if hasattr(self, "gallery_widget") and self.gallery_widget.isVisible():
            self.gallery_widget.setGeometry(
                (self.width() - 600) // 2, (self.height() - 420) // 2, 600, 420
            )
    
    def take_screenshot(self):
        if not self.hwnd:
            return
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"screenshot_{now}.png")
        capture_window(self.hwnd, screenshot_path)
        self.show_screenshot_notice(screenshot_path)

    def show_screenshot_notice(self, screenshot_path):
        pixmap = QPixmap(screenshot_path).scaled(80, 45, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        text = "¡Captura guardada!"
        html = f'<div style="display:flex;align-items:center;"><img src="{screenshot_path}" width="80" height="45" style="margin-right:12px;"/><p>Hola Mundo</p><span style="color:white;font-size:18px;font-weight:bold;">¡Captura guardada¡</span></div>'
        self.screenshot_notice.setText("")
        self.screenshot_notice.setPixmap(pixmap)
        self.screenshot_notice.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.screenshot_notice.setFixedSize(260, 60)
        self.screenshot_notice.move(self.width() - self.screenshot_notice.width() - 36, self.height() - self.screenshot_notice.height() - 36)
        self.screenshot_notice.setVisible(True)
        self.fade_in_notice()
        QTimer.singleShot(3500, self.fade_out_notice)
    
    def fade_in_notice(self):
        self.screenshot_notice.setWindowOpacity(0)
        self.screenshot_notice.setVisible(True)
        self.notice_anim = QPropertyAnimation(self.screenshot_notice, b"windowOpacity")
        self.notice_anim.setDuration(400)
        self.notice_anim.setStartValue(0)
        self.notice_anim.setEndValue(1)
        self.notice_anim.start()

    def fade_out_notice(self):
        self.notice_anim = QPropertyAnimation(self.screenshot_notice, b"windowOpacity")
        self.notice_anim.setDuration(800)
        self.notice_anim.setStartValue(1)
        self.notice_anim.setEndValue(0)
        self.notice_anim.finished.connect(lambda: self.screenshot_notice.setVisible(False))
        self.notice_anim.start()

    def show_screenshot_gallery(self):
        self.gallery_files = sorted(
            [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith(".png")], reverse=True
        )
        if not self.gallery_files:
            self.gallery_pixmap.setText("No hay capturas.")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.open_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
        else:
            self.gallery_index = 0
            self.update_gallery_image()
            self.prev_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.open_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
        self.gallery_widget.setVisible(True)

    def fade_in_message(self):
        self.anim = QPropertyAnimation(self.message_label, b"windowOpacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()

    def fade_out_message(self):
        self.anim = QPropertyAnimation(self.message_label, b"windowOpacity")
        self.anim.setDuration(800)
        self.anim.setStartValue(1)
        self.anim.setEndValue(0)
        self.anim.finished.connect(lambda: self.message_label.setVisible(False))
        self.anim.start()

    def follow_game_window(self):
        if self.hwnd:
            left_top = win32gui.ClientToScreen(self.hwnd, (0, 0))
            right_bottom = win32gui.ClientToScreen(self.hwnd, win32gui.GetClientRect(self.hwnd)[2:])
            left, top = left_top
            right, bottom = right_bottom
            width = right - left
            height = bottom - top
            self.setGeometry(left, top, width, height)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python overlay.py <nombre_ejecutable>")
        sys.exit(1)
    exe_name = sys.argv[1]
    app = QApplication(sys.argv)

    hwnd = None
    for _ in range(20):  # Intenta durante ~10 segundos
        hwnd = find_game_window(exe_name)
        if hwnd:
            break
        time.sleep(0.5)
    if hwnd:
        # Usa el nombre del ejecutable sin extensión como nombre del juego
        game_name = exe_name.rsplit(".", 1)[0]
        overlay = Overlay(hwnd, game_name=game_name)
    else:
        print(f"No se encontró la ventana de {exe_name}.")
        sys.exit(1)
    sys.exit(app.exec())