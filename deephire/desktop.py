"""DeepHire for Windows: the engine runs inside this process and the app shows in a native window
(Edge WebView2). Nothing is served beyond this computer.

    python deephire/desktop.py          (or DeepHire.exe once packaged)
"""
import logging
import os
import socket
import sys
import threading
import time
import urllib.request

# Fixed: recordings live in the window's storage, which is per origin, and the origin includes the port.
PORT = int(os.getenv("DEEPHIRE_PORT", "47613"))   # override only for testing a second copy
DATA_DIR = os.path.join(os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "DeepHire")
os.makedirs(DATA_DIR, exist_ok=True)
os.environ.setdefault("DEEPHIRE_DATA", DATA_DIR)   # read by settings.py before anything else imports it

# A packaged (windowed) app has no console: keep a log next to the data.
logging.basicConfig(filename=os.path.join(DATA_DIR, "deephire.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
if sys.stdout is None:  # PyInstaller's windowed mode: some libraries write to stdout
    sys.stdout = sys.stderr = open(os.path.join(DATA_DIR, "console.log"), "a", encoding="utf-8")


def port_in_use():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def message(text):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "DeepHire", 0x40)


def main():
    if port_in_use():
        message("DeepHire is already running (or another program is using port 47613).")
        return

    import webview
    import app as engine   # after DEEPHIRE_DATA is set

    threading.Thread(target=lambda: engine.app.run(host="127.0.0.1", port=PORT, threaded=True,
                                                   use_reloader=False, debug=False), daemon=True).start()
    url = f"http://127.0.0.1:{PORT}/practice"
    for _ in range(100):  # wait for the engine before showing the window
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except OSError:
            time.sleep(0.1)

    webview.create_window("DeepHire", url, width=1360, height=880, min_size=(1000, 700),
                          background_color="#d6d8da", text_select=True)
    webview.start(private_mode=False, storage_path=os.path.join(DATA_DIR, "webview"))


if __name__ == "__main__":
    main()
