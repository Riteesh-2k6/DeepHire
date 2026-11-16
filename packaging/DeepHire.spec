# PyInstaller recipe for DeepHire.exe (one folder, windowed).
#   .venv\Scripts\pyinstaller packaging\DeepHire.spec --noconfirm
# Needs the models first: python scripts/fetch_vendor.py
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP = os.path.join(ROOT, "deephire")

datas = [
    (os.path.join(APP, "templates"), "templates"),
    (os.path.join(APP, "static"), "static"),                    # includes the vendored MediaPipe + font
    (os.path.join(APP, "interview_questions.db"), "."),
    (os.path.join(APP, "models"), "models"),                    # Kokoro voice + Whisper base
]
binaries, hiddenimports = [], []
# Libraries that carry data files or native DLLs PyInstaller can't see from imports alone.
for package in ("faster_whisper", "ctranslate2", "onnxruntime", "kokoro_onnx", "espeakng_loader",
                "phonemizer", "tokenizers", "av", "webview", "clr_loader", "pythonnet", "language_tags",
                "segments", "csvw"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(APP, "desktop.py")],
    pathex=[APP],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["app", "answer_evaluator", "delivery", "settings", "setup_check",
                                   "smar_selector", "speech", "stream", "tts", "clr"],
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DeepHire", console=False,
          icon=os.path.join(SPECPATH, "deephire.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="DeepHire")
