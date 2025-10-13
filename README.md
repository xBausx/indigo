# Indigo — InDesign Flyer Export Worker

Automates Adobe InDesign to export a flyer to HTML5 and JPEG, then runs a resize script and files outputs, with robust UI automation, retries, warm session handling, and detailed logging.

Typical flow per file:

(Optionally) clear InDesign cache/recovery folders

**Stage 1:** Open .indd → Export as HTML5 to /html-flyers-static/flyers/<STORE NAME>/

**Stage 2:** Export JPEG next to the generated index.html

**Stage 3:** Close the document to release file locks

**Stage 4:** Move the source .indd into 3_Processed_Files/<STORE NAME>/ (or 5_Error_Files on failure)

**Stage 5:** Run resize script on the processed folder

Send a completion callback to your API (optional)


```text
.
├─ 1_Input_Files/           # (gitignored) drop .indd files here to process
├─ 2_Output_HTML/           # (gitignored) legacy/output scratch (if used by your flow)
├─ 3_Processed_Files/       # (gitignored) .indd files moved here after success
├─ 4_Scripts/               # ExtendScript/JSX (e.g., resize scripts)
├─ 5_Error_Files/           # (gitignored) failed source files get moved here
├─ 6_Logs/                  # (gitignored) high-level run logs
├─ 7_Detailed_Logs/         # (gitignored) per-request detailed logs
├─ 8_Images/                # (gitignored) assets if needed
├─ api_client.py
├─ file_system.py
├─ indesign_ui.py
├─ main.py                  # single-file worker entrypoint
├─ orchestrator.py          # orchestration helpers
├─ requirements.txt
└─ config.ini               # project configuration
```
* Note : Several folders are intentionally gitignored. The commands below will create them locally with .gitkeep so your tree looks correct even when empty.

### Prerequisites

Adobe InDesign (tested with 2025 – adjust paths in config.ini if different)

Windows (UI automation requires Windows for pywinauto)

Python 3.10+ (logs show 3.13; any 3.10–3.13 is fine)

Optional: your API server if you want callbacks (otherwise you’ll see harmless “connection refused” warnings)

### Setup

# 1) Create and activate a virtual environment
**Windows (PowerShell):**
```bash
py -3 -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

**Linux/Mac OS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

# 2) Install dependencies
```bash
pip install -r requirements.txt
```

# 3) Configure `config.ini`
Create or edit config.ini in the repo root. Use this template as a starting point:
```text
[Paths]
# Where processed files (source .indd after success) are stored
processed_folder = 3_Processed_Files
# Where failed source files are moved
error_folder = 5_Error_Files
# Final HTML/JPEG output base (exporter will create a subfolder per job)
final_flyers_output_folder = C:/Users/<YOU>/Documents/nctv-repositories/html-flyers-static/flyers

# InDesign executable path
indesign_executable = C:/Program Files/Adobe/Adobe InDesign 2025/InDesign.exe

# (Optional) Folder containing ExtendScript/JSX files like resize scripts
scripts_folder = 4_Scripts

[Settings]
max_retries = 3
retry_delay_seconds = 10
# retries used after a warm restart (fallbacks to max_retries if omitted)
restart_retries = 2
# clear cache/recovery at the start of each run (recommended true)
clear_cache_on_start = true

[Warm]
enabled = true          ; keep a warm session and restart periodically
max_files = 10          ; restart after N successes
max_minutes = 60        ; or after this many minutes
fail_restart = 2        ; restart on consecutive failures

[API]
# Optional: if not running, the worker will log a connection error but continue
callback_url = http://localhost:3000/api/checkup/deploy-changes
```

# Create the local folders (one-liners)
Run one of the following. They create any missing folders and drop a .gitkeep in each so your tree is consistent.

** Windows (PowerShell): **
```bash
$dirs = @(
  '1_Input_Files','2_Output_HTML','3_Processed_Files','4_Scripts',
  '5_Error_Files','6_Logs','7_Detailed_Logs','8_Images'
)
foreach ($d in $dirs) {
  New-Item -ItemType Directory -Force -Path $d | Out-Null
  New-Item -ItemType File -Force -Path (Join-Path $d '.gitkeep') | Out-Null
}
```

** Linux/macOS (bash/zsh): **
```bash
for d in 1_Input_Files 2_Output_HTML 3_Processed_Files 4_Scripts 5_Error_Files 6_Logs 7_Detailed_Logs 8_Images; do
  mkdir -p "$d"
  : > "$d/.gitkeep"
done
```


# Usage
From the repo root (with your venv active):

** Windows (PowerShell): ** 
```bash
# Example: process one file with a fresh request ID
$req = [guid]::NewGuid()
py -3 .\main.py ".\1_Input_Files\01 FINE FARE 379 HORSEBLOCK RD.indd" $req
```

** Linux/macOS (for reference; UI automation requires Windows): ** 
```bash
REQ=$(uuidgen)
python3 ./main.py "./1_Input_Files/01 FINE FARE 379 HORSEBLOCK RD.indd" "$REQ"
```

