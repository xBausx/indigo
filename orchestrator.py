# orchestrator.py
import logging
import configparser
import time
from pathlib import Path
import sys

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
    # --- Now expects two arguments: file path and requestId ---
    if len(sys.argv) < 3:
        print("FATAL ERROR: InDesign file path and requestId were not provided.")
        sys.exit(1)
        
    indd_file_path = Path(sys.argv[1])
    request_id = sys.argv[2]
    
    project_root = Path().resolve()
    config = configparser.ConfigParser()
    config.read(project_root / 'config.ini')

    # --- Pass requestId to the logging setup ---
    setup_logging_for_file(config, indd_file_path.stem, request_id)
    
    # --- All subsequent log messages will be manually tagged with the Request ID ---
    
    processed_folder = project_root / config.get('Paths', 'processed_folder')
    error_folder = project_root / config.get('Paths', 'error_folder')
    final_output_base_path = Path(config.get('Paths', 'final_flyers_output_folder'))
    max_retries = config.getint('Settings', 'max_retries')
    retry_delay = config.getint('Settings', 'retry_delay_seconds')

    logging.info("==========================================================")
    logging.info(f"[ReqID: {request_id}] Indigo Worker started for file: {indd_file_path.name}")
    
    try:
        # --- STAGE 1: HTML EXPORT ---
        export_successful = False
        for attempt in range(max_retries):
            logging.info(f"[ReqID: {request_id}] HTML Export - Attempt {attempt + 1} of {max_retries}...")
            try:
                file_system.clear_indesign_cache()
                if indesign_ui.export_html_via_ui(indd_file_path, config):
                    export_successful = True
                    break
                else:
                    raise RuntimeError("export_html_via_ui returned False.")
            except Exception:
                logging.error(f"[ReqID: {request_id}] FAILURE: HTML Export attempt {attempt + 1} failed.", exc_info=True)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        # --- STAGE 2: RESIZE PROCESS AND CALLBACK ---
        if export_successful:
            processed_subfolder = file_system.setup_processed_subfolder(indd_file_path, processed_folder)
            file_system.move_file_to_folder(indd_file_path, processed_subfolder)
            
            if indesign_ui.run_resize_on_folder(processed_subfolder, config):
                logging.info(f"[ReqID: {request_id}] Successfully processed and resized {indd_file_path.name}.")
                
                logging.info(f"[ReqID: {request_id}] Attempting to send completion callback...")
                final_output_folder_path = final_output_base_path / indd_file_path.stem
                
                if api_client.send_completion_callback(final_output_folder_path, request_id, indd_file_path.name, config):
                    logging.info(f"[SUMMARY] [ReqID: {request_id}] Process complete for {indd_file_path.name}. Callback successful.")
                    
                    # --- NEW: Cleanup the intermediate output folder now that we are completely finished ---
                    file_system.cleanup_intermediate_folder(indd_file_path.stem, request_id, config)

                else:
                    logging.warning(f"[SUMMARY] [ReqID: {request_id}] Process complete for {indd_file_path.name}, but the final API callback FAILED.")

            else:
                logging.error(f"[ReqID: {request_id}] Resize process failed for '{indd_file_path.name}'. Moving its folder to Errors.")
                file_system.move_file_to_folder(processed_subfolder, error_folder)
                sys.exit(1)
        else:
            logging.error(f"[ReqID: {request_id}] All HTML export attempts failed for '{indd_file_path.name}'.")
            file_system.move_file_to_folder(indd_file_path, error_folder)
            sys.exit(1)

    except Exception as e:
        logging.error(f"[ReqID: {request_id}] A critical, unhandled error occurred: {e}", exc_info=True)
        # Attempt to move the source file to error if it's still in the temp folder
        if indd_file_path.exists():
            file_system.move_file_to_folder(indd_file_path, error_folder)
        # If the file was already moved to processed, move that folder to error
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