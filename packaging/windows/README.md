# Building the 100% Offline Windows Pen-Drive Distribution (`Start-Smriti.exe`)

This workflow prepares a **zero-internet, zero-prerequisite** portable folder (`dist\Start-Smriti\`) on your Windows build laptop so you can copy/zip it onto a pen drive, unzip it on your professor's Windows desktop (no Python, Node, or Ollama required there), and double-click **`Start-Smriti.exe`**.

## What Gets Bundled Offline

1. **`Start-Smriti.exe` + `_internal\`** — Frozen Python 3.11 + FastAPI + LangGraph + CPU PyTorch/SentenceTransformers + built React UI (`dist/`). No `.venv` or `node_modules` folder needed on the professor's PC.
2. **`ollama\ollama.exe` + `models\`** — Portable Windows Ollama daemon plus **both `qwen2.5:1.5b` (~1.0 GB, default fast CPU model) and `qwen2.5:3b` (~1.9 GB, selectable in the header)** stored offline in `models\`.
3. **`hf_cache\`** — Pre-downloaded `all-MiniLM-L6-v2` embeddings for offline hybrid BM25 + vector search.
4. **`tesseract\`** *(auto-copied if Tesseract-OCR is installed on your build laptop)* — Enables offline OCR on scanned DCRUST PYQ PDFs.
5. **`pyqs\` & `syllabus\`** — Deduplicated `pyqs\by_subject\` + `syllabus\by_branch\` + `index.json` (no duplicated `by_session/` or `by_year/` copies).

---

## Step-by-Step Build on Your Windows Laptop

1. **Copy the project source** (excluding Linux `.venv` and `node_modules`) from your Linux machine to your Windows build laptop (make sure `pyqs/` and `syllabus/` are included, or zip without `.venv`, `node_modules`, `pyqs/by_session`, `syllabus/by_year`).
2. *(Recommended before building)* Install [Tesseract OCR for Windows](https://github.com/UB-Mannheim/tesseract/wiki) on the build laptop (`C:\Program Files\Tesseract-OCR`) so the script automatically copies it into the portable bundle for scanned PYQs.
3. Ensure **Node.js 20+** and **Python 3.11** are installed on the build laptop, then run in PowerShell inside the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\prepare_bundle.ps1 -CreateZip
```

Or build an Inno Setup single-click installer (`Smriti-Setup.exe` + `.bin` slices, desktop icon included):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\prepare_bundle.ps1 -BuildInstaller
```

4. **Pen Drive Note:** Format the pen drive as **exFAT** or **NTFS** (not FAT32, which rejects single files over 4 GB). Copy `dist\Smriti-Windows-Offline.zip` (or the `dist\Start-Smriti\` folder directly) to the pen drive.
5. **On the Professor's Windows Desktop:** Unzip/copy to the Desktop and double-click **`Start-Smriti.exe`** (or click **`Start-Smriti.exe --demo`** / run the shortcut to preload demo notes). It automatically launches portable Ollama on an isolated port (`11435`), loads `qwen2.5:1.5b`, starts FastAPI + React, and opens the browser.
