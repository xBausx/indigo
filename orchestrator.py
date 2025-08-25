# orchestrator.py
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

def _safe_stem(stem: str) -> str:
    """Trim trailing spaces/dots and replace Windows-illegal chars for folder names."""
    s = stem.strip().rstrip('.')              # trim whitespace ends + trailing dots
    return re.sub(r'[<>:"/\\|?*]', '_', s)    # make it filesystem safe


def main():
    """
    This script is a single-file worker. It processes one InDesign file
    and uses a requestId for end-to-end traceability.
    """
    if len(sys.argv) < 3:
        sys.exit("FATAL ERROR: InDesign file path and requestId were not provided.")
        
    indd_file_path = Path(sys.argv[1])
    request_id = sys.argv[2]
    safe_stem = _safe_stem(indd_file_path)
    
    project_root = Path().resolve()
    config = configparser.ConfigParser()
    config.read(project_root / 'config.ini')

    setup_logging_for_file(config, indd_file_path.stem, request_id)
    
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

        # Use the original, clean move function. The lock is gone.
        file_system.move_file_to_folder(indd_file_path, processed_subfolder)

        # --- STAGE 5: RESIZE PROCESS AND FINAL CLOSE ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 5: Resize Script...")
        resize_ok = _attempt_with_retries("Stage 5: Resize Script", indesign_ui.run_resize_on_folder,
                                (processed_subfolder, config), max_retries, retry_delay, request_id)
        # run_resize_on_folder launches/kills its own app instance; after it returns, app shouldn't be running
        app_is_running = False

        if resize_ok:
            logging.info(f"[ReqID: {request_id}] Successfully processed and resized {indd_file_path.name}.")
            
            # Read page count written by resizeall.js
            safe_stem = _safe_stem(indd_file_path.stem)
            page_count = file_system.read_page_count(safe_stem, config)
            logging.info(f"[ReqID: {request_id}] Page count: {page_count if page_count is not None else 'unknown'}")
            
            # --- FINAL CALLBACK ---
            final_output_folder_path = final_output_base_path / safe_stem
            if api_client.send_completion_callback(final_output_folder_path, request_id, indd_file_path.name, config, status="EXPORT_SUCCESS", pages=page_count):
                logging.info(f"[SUMMARY] [ReqID: {request_id}] Process complete. Callback successful.")
            else:
                logging.warning(f"[SUMMARY] [ReqID: {request_id}] Process complete, but the final API callback FAILED.")
        else:
            raise RuntimeError(f"Stage 5: run_resize_on_folder failed after {max_retries} attempts.")

    except Exception as e:
        logging.error(f"[ReqID: {request_id}] A critical error occurred: {e}", exc_info=True)
        
        # notify failure with status
        try:
            safe_stem = _safe_stem(indd_file_path.stem)
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
        
        # Graceful error handling
        if app_is_running:
            try: Application(backend="win32").connect(title_re=".*InDesign.*").kill()
            except Exception: pass
        
        if indd_file_path.exists():
            file_system.move_file_to_folder(indd_file_path, error_folder)
        elif 'processed_subfolder' in locals() and processed_subfolder.exists():
            file_system.move_file_to_folder(processed_subfolder, error_folder)
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