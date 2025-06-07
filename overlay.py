import sys
import time
import win32gui
import win32ui
import win32con
import win32process
import win32api
from PIL import Image
import keyboard
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer

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
        self.setWindowOpacity(0.3)
        self.setGeometry(*win32gui.GetWindowRect(hwnd))
        self.show()
        self.timer = QTimer()
        self.timer.timeout.connect(self.follow_game_window)
        self.timer.start(500)

    def follow_game_window(self):
        rect = win32gui.GetWindowRect(self.hwnd)
        self.setGeometry(*rect)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python overlay.py <nombre_ejecutable>")
        sys.exit(1)
    GAME_EXE_NAME = sys.argv[1]

    hwnd = None
    max_retries = 120  # 120 * 0.5s = 60 segundos
    for i in range(max_retries):
        hwnd = find_game_window(GAME_EXE_NAME)
        if hwnd:
            print(f"Ventana encontrada después de {i*0.5:.1f} segundos.")
            break
        time.sleep(0.5)
    if not hwnd:
        print("No se encontró la ventana del juego.")
        sys.exit(1)

    app = QApplication(sys.argv)
    overlay = Overlay(hwnd)

    def on_hotkey():
        timestamp = int(time.time())
        save_path = f"screenshot_{timestamp}.png"
        capture_window(hwnd, save_path)
        print(f"Captura guardada en {save_path}")

    keyboard.add_hotkey("F12", on_hotkey)

    sys.exit(app.exec())