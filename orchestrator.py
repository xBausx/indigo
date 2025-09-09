# orchestrator.py
import json
from datetime import datetime, timedelta
import logging
import configparser
import time
from pathlib import Path
import sys
from pywinauto.application import Application

# Import our custom libraries
import file_system
import indesign_ui
import api_client
import re

def _attempt_with_retries(label, fn, args, retries, delay, request_id):
    for attempt in range(1, retries + 1):
        logging.info(f"[ReqID: {request_id}] {label} - Attempt {attempt} of {retries}...")
        try:
            if fn(*args):
                logging.info(f"[ReqID: {request_id}] {label} - SUCCESS on attempt {attempt}.")
                return True
        except Exception:
            logging.error(f"[ReqID: {request_id}] {label} raised an exception.", exc_info=True)
        if attempt < retries:
            time.sleep(delay)
    logging.error(f"[ReqID: {request_id}] {label} - FAILED after {retries} attempts.")
    return False

def _kill_indesign_safely():
    try:
        Application(backend="win32").connect(title_re=".*InDesign.*").kill()
        return True
    except Exception:
        return False

def setup_logging_for_file(config, log_file_name, request_id):
    """
    Sets up logging to a specific file named with the request_id and filename
    in the detailed_logs folder.
    """
    project_root = Path().resolve()
    detailed_log_folder = project_root / config.get('Paths', 'detailed_log_folder')
    detailed_log_folder.mkdir(exist_ok=True)
    
    # --- Log filename now includes the request_id for easy lookup ---
    log_file_name_with_id = f"{request_id}_{log_file_name}.log"
    file_log_path = detailed_log_folder / log_file_name_with_id
    
    # --- Ensure any existing handlers are removed for a clean setup ---
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        handlers=[
            logging.FileHandler(file_log_path),
            logging.StreamHandler()
        ]
    )
    logging.info(f"Logging for Request ID {request_id} will be in: {file_log_path}")
    
def _warm_cfg(config):
    s = config['WarmSession'] if config.has_section('WarmSession') else {}
    return {
        "enabled": s.get('enabled', 'false').lower() == 'true',
        "max_files": int(s.get('max_files_per_session', 5)),
        "max_minutes": int(s.get('max_session_minutes', 45)),
        "fail_restart": int(s.get('consecutive_fail_restart', 2)),
    }

def _ledger_path(project_root):
    logs = project_root / '6_Logs'
    logs.mkdir(exist_ok=True)
    return logs / 'warm_session.json'

def _load_ledger(project_root):
    p = _ledger_path(project_root)
    if not p.exists():
        return {"started_at": None, "files_done": 0, "consecutive_failures": 0}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {"started_at": None, "files_done": 0, "consecutive_failures": 0}

def _save_ledger(project_root, data):
    _ledger_path(project_root).write_text(json.dumps(data), encoding='utf-8')

def _ledger_new():
    return {
        "started_at": datetime.utcnow().isoformat(),
        "files_done": 0,
        "consecutive_failures": 0
    }

def _ledger_age_minutes(ledger):
    try:
        if not ledger.get("started_at"):
            return 0
        started = datetime.fromisoformat(ledger["started_at"])
        return max(0, int((datetime.utcnow() - started).total_seconds() // 60))
    except Exception:
        return 0


def _safe_stem(indd_path):
    """Normalize the folder name derived from the INDD file name."""
    s = Path(indd_path).stem
    s = s.strip().rstrip(".")                             # trim spaces / trailing dots
    s = re.sub(r'[<>:"/\\|?*]', "_", s)                  # replace illegal Win chars
    return s or "untitled"


def main():
    """
    This script is a single-file worker. It processes one InDesign file
    and uses a requestId for end-to-end traceability.
    """
    if len(sys.argv) < 3:
        sys.exit("FATAL ERROR: InDesign file path and requestId were not provided.")
        
    indd_file_path = Path(sys.argv[1])
    request_id = sys.argv[2]
    
    # Sanitize filename before any stage runs
    indd_file_path = file_system.sanitize_indd_filename(indd_file_path)
    
    project_root = Path().resolve()
    config = configparser.ConfigParser()
    config.read(project_root / 'config.ini')
    
    warm = _warm_cfg(config)
    ledger = _load_ledger(project_root)
    if warm["enabled"] and not ledger.get("started_at"):
        ledger = _ledger_new()
        _save_ledger(project_root, ledger)


    setup_logging_for_file(config, indd_file_path.stem, request_id)
    
    if (not warm["enabled"]) or ledger.get("files_done", 0) == 0:
        indesign_ui.kill_indesign_if_running(config)
        file_system.clear_indesign_cache()
        time.sleep(1)
    
    processed_folder = project_root / config.get('Paths', 'processed_folder')
    error_folder = project_root / config.get('Paths', 'error_folder')
    final_output_base_path = Path(config.get('Paths', 'final_flyers_output_folder'))
    max_retries   = config.getint('Settings', 'max_retries')
    retry_delay   = config.getint('Settings', 'retry_delay_seconds')
    restart_retries = config.getint('Settings', 'restart_retries', fallback=max_retries)
    
    app_is_running = False
    
    logging.info("==========================================================")
    logging.info(f"[ReqID: {request_id}] Indigo Worker started for file: {indd_file_path.name}")
    
    try:
        # --- STAGE 1: HTML EXPORT ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 1: HTML Export...")
        if not _attempt_with_retries("Stage 1: HTML Export", indesign_ui.export_html_via_ui,
                                    (indd_file_path, config), max_retries, retry_delay, request_id):
            raise RuntimeError(f"Error during Stage 1 phase; retried {max_retries} times. Returning as failed.")
        app_is_running = True
        
        # --- STAGE 2: JPEG EXPORT ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 2: JPEG Export...")

        # Retry in-place
        jpeg_ok = _attempt_with_retries("Stage 2: JPEG Export", indesign_ui.export_jpeg_via_ui,
                                        (indd_file_path, config), max_retries, retry_delay, request_id)

        if not jpeg_ok:
            logging.warning(f"[ReqID: {request_id}] Stage 2 failed after {max_retries} attempts; restarting InDesign and retrying Stage 2...")
            _kill_indesign_safely()
            app_is_running = False
            file_system.clear_indesign_cache()
            time.sleep(1)

            # Reopen the same document WITHOUT redoing HTML export
            if not indesign_ui.open_indd_only(indd_file_path, config):
                raise RuntimeError(f"Stage 2 restart: could not reopen document.")


            app_is_running = True

            # Retry Stage 2 again after restart
            jpeg_ok = _attempt_with_retries("Stage 2 (after restart): JPEG Export", indesign_ui.export_jpeg_via_ui,
                                            (indd_file_path, config), restart_retries, retry_delay, request_id)

            if not jpeg_ok:
                total = max_retries + restart_retries
                raise RuntimeError(f"Error during Stage 2 phase; retried {total} times (including after restart). Returning as failed.")

        # --- STAGE 3: CLOSE DOCUMENT TO RELEASE LOCK ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 3: Closing Document...")
        if not _attempt_with_retries("Stage 3: Close Document", indesign_ui.close_document,
                                    (config, indd_file_path.name), max_retries, retry_delay, request_id):
            logging.warning(f"[ReqID: {request_id}] Close Document failed; killing InDesign as fallback.")
            _kill_indesign_safely()
            app_is_running = False

        # --- STAGE 4: MOVE FILE (Now Safe) ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 4: Moving File...")
        processed_subfolder = file_system.setup_processed_subfolder(indd_file_path, processed_folder)

        # Normalize the returned folder name in case setup_* didn’t sanitize it
        safe_processed = processed_subfolder.parent / _safe_stem(processed_subfolder.name)
        if safe_processed != processed_subfolder:
            safe_processed.mkdir(parents=True, exist_ok=True)
            processed_subfolder = safe_processed

        # Prefer copy-then-delete to avoid sporadic lock errors
        file_system.copy_then_delete_indesign(indd_file_path, processed_subfolder, request_id)


        # --- STAGE 5: RESIZE PROCESS AND FINAL CLOSE ---
        resize_ok = _attempt_with_retries(
            "Stage 5: Resize Script",
            indesign_ui.run_resize_on_folder_keep_session,
            (processed_subfolder, config),
            max_retries,
            retry_delay,
            request_id
        )
        # run_resize_on_folder launches/kills its own app instance; after it returns, app shouldn't be running
        app_is_running = False

        if resize_ok:
            logging.info(f"[ReqID: {request_id}] Successfully processed and resized {indd_file_path.name}.")
            
            if warm["enabled"]:
                # Success resets consecutive failures
                ledger["consecutive_failures"] = 0
                # Count this file
                ledger["files_done"] = int(ledger.get("files_done", 0)) + 1
                age = _ledger_age_minutes(ledger)
                logging.info(f"[Warm] files_done={ledger['files_done']} age(min)={age}")

                # Restart if thresholds hit
                if ledger["files_done"] >= warm["max_files"] or age >= warm["max_minutes"]:
                    logging.info("[Warm] Session limit reached; restarting InDesign.")
                    indesign_ui.kill_indesign_if_running(config)
                    ledger = _ledger_new()
                _save_ledger(project_root, ledger)
            
            # Read page count written by resizeall.js
            safe_stem = _safe_stem(indd_file_path)
            page_count = file_system.read_page_count(safe_stem, config)
            logging.info(f"[ReqID: {request_id}] Page count: {page_count if page_count is not None else 'unknown'}")
            
            # --- FINAL CALLBACK ---
            final_output_folder_path = final_output_base_path / safe_stem
            if api_client.send_completion_callback(final_output_folder_path, request_id, indd_file_path.name, config, status="EXPORT_SUCCESS", pages=page_count):
                logging.info(f"[SUMMARY] [ReqID: {request_id}] Process complete. Callback successful.")
            else:
                logging.warning(f"[SUMMARY] [ReqID: {request_id}] Process complete, but the final API callback FAILED.")
        else:
            if warm["enabled"]:
                ledger["consecutive_failures"] = int(ledger.get("consecutive_failures", 0)) + 1
                logging.info(f"[Warm] consecutive_failures={ledger['consecutive_failures']}")
                if ledger["consecutive_failures"] >= warm["fail_restart"]:
                    logging.info("[Warm] Failure threshold reached; restarting InDesign.")
                    indesign_ui.kill_indesign_if_running(config)
                    ledger = _ledger_new()
                _save_ledger(project_root, ledger)
                
            raise RuntimeError(f"Stage 5: run_resize_on_folder failed after {max_retries} attempts.")

    except Exception as e:
        logging.error(f"[ReqID: {request_id}] A critical error occurred: {e}", exc_info=True)

        # Best-effort: notify failure (don't block if this fails)
        try:
            safe_stem = _safe_stem(indd_file_path)
            api_client.send_completion_callback(
                final_output_base_path / safe_stem,
                request_id,
                indd_file_path.name,
                config,
                status="EXPORT_FAILED",
                pages=None
            )
        except Exception:
            pass

        # 1) Try to close just the document to release the .indd lock
        try:
            indesign_ui.close_document(config, indd_file_path.name)
            time.sleep(1.0)
        except Exception:
            pass

        # 2) As a fallback, kill InDesign so no handles remain
        try:
            _kill_indesign_safely()
            time.sleep(1.0)
        except Exception:
            pass

        # 3) Now move the file/folder to Errors with a few retries
        moved = False
        for attempt in range(1, 4):
            try:
                if indd_file_path.exists():
                    file_system.move_file_to_folder(indd_file_path, error_folder)
                    moved = True
                    break
                elif 'processed_subfolder' in locals() and processed_subfolder.exists():
                    file_system.move_file_to_folder(processed_subfolder, error_folder)
                    moved = True
                    break
                else:
                    moved = True  # nothing to move
                    break
            except Exception as move_err:
                logging.warning(f"[ReqID: {request_id}] Move-to-error attempt {attempt}/3 failed: {move_err}")
                time.sleep(2)

        if not moved:
            logging.error(f"[ReqID: {request_id}] FINAL: Could not move to Errors; leaving in place to avoid data loss.")

        sys.exit(1)

    logging.info(f"Indigo Worker finished successfully for Request ID: {request_id}.")
    logging.info("==========================================================")
    
if __name__ == "__main__":
    try:
        # --- Added 'requests' to the dependency check ---
        import pyautogui, pywinauto, pyperclip, requests
        main()
    except ImportError:
        print("FATAL ERROR: A required library is not installed. Please run 'pip install -r requirements.txt'.")