"""One-time download of the browser-side files, so the app runs offline afterwards.

    python scripts/fetch_vendor.py

Fetches MediaPipe Tasks Vision (JS + WebAssembly) and the Barlow Semi Condensed font
from the npm registry, and the Face Landmarker model from Google's model bucket,
into deephire/static/vendor/.
"""
import io
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


def main():
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
