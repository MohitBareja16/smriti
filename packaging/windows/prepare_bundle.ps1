#Requires -Version 5.1
<#
.SYNOPSIS
  Build a 100% offline, single-click Windows distribution of Smriti AI:
  - Frozen Python FastAPI + LangGraph + CPU ML runtime (Start-Smriti.exe)
  - Built React Web UI (no Node/npm needed on professor PC)
  - Portable Windows ollama.exe + BOTH qwen2.5:1.5b AND qwen2.5:3b models
  - Pre-cached all-MiniLM-L6-v2 embeddings + optional portable Tesseract OCR
  - DCRUST PYQs (pyqs/by_subject + index.json) & Syllabi (syllabus/by_branch + index.json)
#>
param(
    [string[]]$Models = @("qwen2.5:1.5b", "qwen2.5:3b"),
    [switch]$SkipUiBuild,
    [switch]$SkipEmbeddings,
    [switch]$SkipPdfAssets,
    [switch]$CreateZip,
    [switch]$BuildInstaller
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$DistIndex = Join-Path $RepoRoot "src\smriti\ui\web\dist\index.html"
$HasNpm = $null -ne (Get-Command "npm" -ErrorAction SilentlyContinue)
Write-Host "==> [1/8] Checking React Web UI..." -ForegroundColor Cyan
if ((-not $SkipUiBuild) -and $HasNpm) {
    Push-Location "src\smriti\ui\web"
    if (Test-Path "package-lock.json") {
        npm ci
    } else {
        npm install
    }
    npm run build
    Pop-Location
} elseif (Test-Path $DistIndex) {
    Write-Host "    Reusing pre-built React Web UI at src\smriti\ui\web\dist (Node.js/npm not needed)." -ForegroundColor Green
} else {
    throw "Pre-built UI not found at $DistIndex and npm is not installed. Install Node.js LTS or include web\dist."
}

Write-Host "==> [2/8] Setting up Windows .venv with CPU-only PyTorch + ML extras..." -ForegroundColor Cyan
$PyCmd = @("python")
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    foreach ($ver in @("-3.11", "-3.12", "-3.13")) {
        & py $ver --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $PyCmd = @("py", $ver)
            break
        }
    }
}
if ($PyCmd.Length -gt 1) {
    $PyVerStr = (& $PyCmd[0] $PyCmd[1] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
} else {
    $PyVerStr = (& $PyCmd[0] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
}
Write-Host "    Using Python $PyVerStr ($($PyCmd -join ' '))"
if ([version]$PyVerStr -ge [version]"3.14") {
    Write-Warning "Python $PyVerStr detected. PyTorch/PyInstaller wheels may fail on 3.14; Python 3.11 is recommended (winget install -e --id Python.Python.3.11)."
}
if (-not (Test-Path ".venv")) {
    if ($PyCmd.Length -gt 1) {
        & $PyCmd[0] $PyCmd[1] -m venv .venv
    } else {
        & $PyCmd[0] -m venv .venv
    }
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
if (-not $SkipEmbeddings) {
    & ".\.venv\Scripts\pip.exe" install torch --index-url https://download.pytorch.org/whl/cpu
    & ".\.venv\Scripts\pip.exe" install -e ".[ui,docx,ml]" pyinstaller
} else {
    & ".\.venv\Scripts\pip.exe" install -e ".[ui,docx]" pyinstaller
}

Write-Host "==> [3/8] Freezing Start-Smriti.exe via PyInstaller..." -ForegroundColor Cyan
& ".\.venv\Scripts\pyinstaller.exe" --noconfirm --clean packaging\windows\smriti.spec

$BundleDir = Join-Path $RepoRoot "dist\Start-Smriti"
New-Item -ItemType File -Path (Join-Path $BundleDir ".portable") -Force | Out-Null

Write-Host "==> [4/8] Downloading portable Ollama for Windows..." -ForegroundColor Cyan
$OllamaDir = Join-Path $BundleDir "ollama"
if (-not (Test-Path (Join-Path $OllamaDir "ollama.exe"))) {
    New-Item -ItemType Directory -Path $OllamaDir -Force | Out-Null
    $OllamaZip = Join-Path $RepoRoot "build\ollama-windows-amd64.zip"
    New-Item -ItemType Directory -Path (Split-Path $OllamaZip) -Force | Out-Null
    if (-not (Test-Path $OllamaZip)) {
        Invoke-WebRequest -Uri "https://ollama.com/download/ollama-windows-amd64.zip" -OutFile $OllamaZip
    }
    Expand-Archive -Path $OllamaZip -DestinationPath $OllamaDir -Force
}

Write-Host "==> [5/8] Pulling offline Qwen models ($($Models -join ', ')) into bundle\models..." -ForegroundColor Cyan
$ModelsDir = Join-Path $BundleDir "models"
New-Item -ItemType Directory -Path $ModelsDir -Force | Out-Null
$env:OLLAMA_MODELS = $ModelsDir
$env:OLLAMA_HOST = "127.0.0.1:11439"
$OllamaExe = Join-Path $OllamaDir "ollama.exe"
$srv = Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WorkingDirectory $OllamaDir -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
try {
    foreach ($m in $Models) {
        Write-Host "    Pulling $m ..."
        & $OllamaExe pull $m
    }
}
finally {
    if ($srv -and -not $srv.HasExited) {
        Stop-Process -Id $srv.Id -Force
    }
}

Write-Host "==> [6/8] Pre-caching local embedding model (all-MiniLM-L6-v2) for offline hybrid search..." -ForegroundColor Cyan
if (-not $SkipEmbeddings) {
    $HfCache = Join-Path $BundleDir "hf_cache"
    New-Item -ItemType Directory -Path $HfCache -Force | Out-Null
    $env:HF_HOME = $HfCache
    $env:SENTENCE_TRANSFORMERS_HOME = $HfCache
    & ".\.venv\Scripts\python.exe" -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
}

Write-Host "==> [7/8] Bundling Tesseract OCR (if installed on build PC) for offline scanned PYQ OCR..." -ForegroundColor Cyan
$TessDst = Join-Path $BundleDir "tesseract"
$TessSrc = @("C:\Program Files\Tesseract-OCR", "C:\Program Files (x86)\Tesseract-OCR") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($TessSrc) {
    robocopy $TessSrc $TessDst /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    Write-Host "    Bundled Tesseract from $TessSrc"
} else {
    Write-Warning "Tesseract-OCR not found on build laptop; text-layer PDFs work offline, install Tesseract-OCR to bundle scanned-PDF OCR."
}

Write-Host "==> [8/8] Copying DCRUST PYQs & Syllabus datasets (deduplicated)..." -ForegroundColor Cyan
if (-not $SkipPdfAssets) {
    $PyqDst = Join-Path $BundleDir "pyqs"
    if (Test-Path (Join-Path $RepoRoot "pyqs\index.json")) {
        New-Item -ItemType Directory -Path $PyqDst -Force | Out-Null
        Copy-Item (Join-Path $RepoRoot "pyqs\index.json") (Join-Path $PyqDst "index.json") -Force
        if (Test-Path (Join-Path $RepoRoot "pyqs\by_subject")) {
            robocopy (Join-Path $RepoRoot "pyqs\by_subject") (Join-Path $PyqDst "by_subject") /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
        }
    }
    $SylDst = Join-Path $BundleDir "syllabus"
    if (Test-Path (Join-Path $RepoRoot "syllabus\index.json")) {
        New-Item -ItemType Directory -Path $SylDst -Force | Out-Null
        Copy-Item (Join-Path $RepoRoot "syllabus\index.json") (Join-Path $SylDst "index.json") -Force
        if (Test-Path (Join-Path $RepoRoot "syllabus\by_branch")) {
            robocopy (Join-Path $RepoRoot "syllabus\by_branch") (Join-Path $SylDst "by_branch") /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
        }
    }
}

if ($CreateZip) {
    $ZipOut = Join-Path $RepoRoot "dist\Smriti-Windows-Offline.zip"
    Write-Host "==> Creating pen-drive archive $ZipOut (use exFAT/NTFS pen drive for >4 GB files)..." -ForegroundColor Cyan
    if (Test-Path $ZipOut) { Remove-Item $ZipOut -Force }
    Compress-Archive -Path $BundleDir -DestinationPath $ZipOut -CompressionLevel Optimal
}

if ($BuildInstaller) {
    $iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($null -eq $iscc -and (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) {
        $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    }
    if ($iscc) {
        Write-Host "==> Compiling Smriti-Setup.exe via Inno Setup..." -ForegroundColor Green
        & $iscc (Join-Path $PSScriptRoot "SmritiSetup.iss")
    } else {
        Write-Warning "Inno Setup (ISCC.exe) not found. Portable folder is ready at: $BundleDir"
    }
}

Write-Host "`nDone! Completely offline portable Windows bundle: $BundleDir" -ForegroundColor Green
Write-Host "Copy/extract onto the professor's Windows desktop and double-click Start-Smriti.exe." -ForegroundColor Green
