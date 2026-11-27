# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the offline portable Windows Start-Smriti.exe launcher."""

import importlib.util
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parents[1]
SRC = ROOT / "src"

datas = []
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "smriti.ui",
]

core_pkgs = ["langgraph", "langchain_core", "fastapi", "pydantic", "cryptography", "pypdf", "PIL", "docx"]
optional_ml_pkgs = ["sentence_transformers", "transformers", "huggingface_hub", "tokenizers", "torch", "numpy"]

for pkg in core_pkgs + [p for p in optional_ml_pkgs if importlib.util.find_spec(p) is not None]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

web_dist = SRC / "smriti" / "ui" / "web" / "dist"
if web_dist.is_dir():
    datas.append((str(web_dist), "smriti/ui/web/dist"))

demo_dir = ROOT / "evals" / "data" / "alex_demo"
if demo_dir.is_dir():
    datas.append((str(demo_dir), "alex_demo"))

a = Analysis(
    [str(SRC / "smriti" / "desktop.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "chainlit"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Start-Smriti",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Start-Smriti",
)
