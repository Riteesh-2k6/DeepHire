"""One-time download of the browser-side files, so the app runs offline afterwards.

    python scripts/fetch_vendor.py

Fetches MediaPipe Tasks Vision (JS + WebAssembly) and the Barlow Semi Condensed font
from the npm registry, and the Face Landmarker model from Google's model bucket,
into deephire/static/vendor/.
"""
import io
import os
import pathlib
import sys
import tarfile
import urllib.request

VENDOR = pathlib.Path(__file__).resolve().parent.parent / "deephire" / "static" / "vendor"

PACKAGES = [  # (npm package, version, files inside the tarball, output folder)
    ("@mediapipe/tasks-vision", "0.10.35",
     ["vision_bundle.mjs", "wasm/vision_wasm_internal.js", "wasm/vision_wasm_internal.wasm",
      "wasm/vision_wasm_nosimd_internal.js", "wasm/vision_wasm_nosimd_internal.wasm"], "mediapipe"),
    ("@fontsource/barlow-semi-condensed", "5.3.0",
     ["files/barlow-semi-condensed-latin-500-normal.woff2", "files/barlow-semi-condensed-latin-600-normal.woff2",
      "LICENSE"], "fonts"),
]
MODEL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
         VENDOR / "mediapipe" / "face_landmarker.task")


def fetch(url):
    print("downloading", url)
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def unpack(package, version, wanted, folder):
    name = package.split("/")[-1]
    data = fetch(f"https://registry.npmjs.org/{package}/-/{name}-{version}.tgz")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for path in wanted:
            target = VENDOR / folder / pathlib.Path(path).name if folder == "fonts" else VENDOR / folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(f"package/{path}").read())


def fetch_whisper():
    """The speech model goes into the Hugging Face cache; the app then loads it with no network call."""
    try:
        from faster_whisper import download_model
    except ImportError:
        print("skipping the Whisper model: pip install -r requirements.txt first")
        return
    name = os.getenv("WHISPER_MODEL", "base")
    print("downloading Whisper model", name)
    download_model(name)


# The interviewer's voice: Kokoro-82M in kokoro-onnx format, mirrored on Hugging Face (same files as the
# github.com/thewh1teagle/kokoro-onnx v1.0 release), checked against the published SHA-256.
KOKORO = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
KOKORO_DIR = VENDOR.parent.parent / "models" / "kokoro"


def fetch_kokoro():
    import hashlib
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name, sha in KOKORO.items():
        target = KOKORO_DIR / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
            continue
        data = fetch(f"https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/{name}")
        if hashlib.sha256(data).hexdigest() != sha:
            sys.exit(f"{name}: checksum mismatch, not saved")
        target.write_bytes(data)


def main():
    fetch_whisper()
    fetch_kokoro()
    for package in PACKAGES:
        unpack(*package)
    url, target = MODEL
    target.write_bytes(fetch(url))
    missing = [p for _, _, files, folder in PACKAGES for p in files
               if not (VENDOR / folder / (pathlib.Path(p).name if folder == "fonts" else p)).exists()]
    if missing:
        sys.exit(f"missing after download: {missing}")
    print("done:", VENDOR)


if __name__ == "__main__":
    main()
