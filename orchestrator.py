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
import api_client # <--  Import our API client

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


def main():
    """
    This script is a single-file worker. It processes one InDesign file
    and uses a requestId for end-to-end traceability.
    """
    if len(sys.argv) < 3:
        sys.exit("FATAL ERROR: InDesign file path and requestId were not provided.")
        
    indd_file_path = Path(sys.argv[1])
    request_id = sys.argv[2]
    
    project_root = Path().resolve()
    config = configparser.ConfigParser()
    config.read(project_root / 'config.ini')

    setup_logging_for_file(config, indd_file_path.stem, request_id)
    
    processed_folder = project_root / config.get('Paths', 'processed_folder')
    error_folder = project_root / config.get('Paths', 'error_folder')
    final_output_base_path = Path(config.get('Paths', 'final_flyers_output_folder'))
    
    app_is_running = False
    
    logging.info("==========================================================")
    logging.info(f"[ReqID: {request_id}] Indigo Worker started for file: {indd_file_path.name}")
    
    try:
        # --- STAGE 1: HTML EXPORT ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 1: HTML Export...")
        if not indesign_ui.export_html_via_ui(indd_file_path, config):
            raise RuntimeError("Stage 1: export_html_via_ui returned False.")
        app_is_running = True
        
        # --- STAGE 2: JPEG EXPORT ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 2: JPEG Export...")
        if not indesign_ui.export_jpeg_via_ui(indd_file_path, config):
            raise RuntimeError("Stage 2: export_jpeg_via_ui returned False.")

        # --- STAGE 3: CLOSE DOCUMENT TO RELEASE LOCK ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 3: Closing Document...")
        if not indesign_ui.close_document(config, indd_file_path.name):
            raise RuntimeError("Stage 3: close_document returned False.")

        # --- STAGE 4: MOVE FILE (Now Safe) ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 4: Moving File...")
        processed_subfolder = file_system.setup_processed_subfolder(indd_file_path, processed_folder)
        # Use the original, clean move function. The lock is gone.
        file_system.move_file_to_folder(indd_file_path, processed_subfolder)

        # --- STAGE 5: RESIZE PROCESS AND FINAL CLOSE ---
        logging.info(f"[ReqID: {request_id}] Starting Stage 5: Resize Script...")
        if indesign_ui.run_resize_on_folder(processed_subfolder, config):
            app_is_running = False # run_resize_on_folder now kills the app
            logging.info(f"[ReqID: {request_id}] Successfully processed and resized {indd_file_path.name}.")
            
            # --- FINAL CALLBACK ---
            final_output_folder_path = final_output_base_path / indd_file_path.stem
            if api_client.send_completion_callback(final_output_folder_path, request_id, indd_file_path.name, config):
                logging.info(f"[SUMMARY] [ReqID: {request_id}] Process complete. Callback successful.")
            else:
                logging.warning(f"[SUMMARY] [ReqID: {request_id}] Process complete, but the final API callback FAILED.")
        else:
            app_is_running = False # run_resize_on_folder kills the app even on failure
            raise RuntimeError(f"Stage 5: run_resize_on_folder returned False.")

    except Exception as e:
        logging.error(f"[ReqID: {request_id}] A critical error occurred: {e}", exc_info=True)
        
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