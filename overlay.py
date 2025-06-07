import sys
import time
import win32gui
import win32ui
import win32con
import win32process
import win32api
from PIL import Image
import keyboard
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
import ctypes

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

class Overlay(QWidget):
    def __init__(self, hwnd):
        super().__init__()
        self.hwnd = hwnd
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
            self.setGeometry(100, 100, 800, 400)  # Tamaño y posición fijos para depuración
        self.timer = QTimer()
        if hwnd:
            self.timer.timeout.connect(self.follow_game_window)
            self.timer.start(500)

        # Fondo visible para depuración (elimina/commenta después de probar)
        self.setStyleSheet("background-color: rgba(255,0,0,0.3);")

        # Mensaje tipo Steam en la esquina inferior izquierda
        self.message_label = QLabel("✔ Overlay de Tradu-Launcher iniciado correctamente", self)
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
            rect = win32gui.GetWindowRect(self.hwnd)
            self.setGeometry(*rect)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    hwnd = find_game_window("notepad.exe")
    if hwnd:
        overlay = Overlay(hwnd)
    else:
        print("No se encontró la ventana de Notepad.")
        sys.exit(1)
    sys.exit(app.exec())