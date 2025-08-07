# main.py
import logging
import configparser
import threading
import time
from queue import Queue
from pathlib import Path
import subprocess
import sys
import shutil
import file_system

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("FATAL ERROR: The 'Flask' library is not installed.")
    sys.exit(1)

# --- GLOBAL OBJECTS ---
job_queue = Queue()
folder_scan_lock = threading.Lock()
config = configparser.ConfigParser()

# ---  Shared Status Object and Lock ---
# This dictionary will be shared between the API thread and the worker thread.
status_info = {
    "status": "idle",
    "current_file": None
}
# A lock to ensure thread-safe updates to the status_info dictionary.
status_lock = threading.Lock()


# --- THE WORKER THREAD (THE "CONSUMER") ---
def worker_thread():
    """
    This function runs in the background. It watches the job_queue and
    launches the orchestrator subprocess for each file.
    """
    project_root = Path().resolve()
    orchestrator_script_path = project_root / 'orchestrator.py'

    logging.info("Worker thread started. Waiting for jobs...")

    while True:
        file_to_process = job_queue.get()
        if file_to_process is None: break

        # ---  Update status before processing ---
        with status_lock:
            status_info["status"] = "processing"
            status_info["current_file"] = str(file_to_process)
        
        logging.info(f"[WORKER] - Picked up job: {file_to_process.name}")
        
        try:
            process = subprocess.run(
                [sys.executable, str(orchestrator_script_path), str(file_to_process)],
                capture_output=True,
                text=True,
                check=True
            )
            logging.info(f"[WORKER] - Subprocess for '{file_to_process.name}' completed successfully.")

        except subprocess.CalledProcessError as e:
            logging.error(f"[WORKER] - Subprocess for '{file_to_process.name}' FAILED.")
            logging.error(f"[WORKER] - Output:\n{e.stderr}")
        
        except Exception as e:
            logging.error(f"[WORKER] - A critical error occurred while running subprocess: {e}", exc_info=True)

        finally:
            # ---  Update status after processing is complete ---
            with status_lock:
                status_info["status"] = "idle"
                status_info["current_file"] = None
            
            job_queue.task_done()

# --- THE FLASK API (THE "PRODUCER") ---
app = Flask(__name__)

@app.route('/run-process', methods=['POST'])
def run_process():
    """
    API endpoint to scan for files, claim them, and add them to the queue.
    """
    project_root = Path().resolve()
    input_folder = project_root / config.get('Paths', 'input_folder')
    temp_processing_folder = project_root / "temp_processing"
    temp_processing_folder.mkdir(exist_ok=True)

    if not folder_scan_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "A process is already scanning the input folder."}), 429

    try:
        logging.info("[API] - /run-process endpoint called.")
        indd_files = list(input_folder.glob("*.indd"))
        if not indd_files:
            return jsonify({"status": "success", "message": "No new files found to process.", "files_queued": 0})

        claimed_files = []
        for indd_file in indd_files:
            try:
                dest_path = temp_processing_folder / indd_file.name
                shutil.move(str(indd_file), str(dest_path))
                claimed_files.append(dest_path)
            except Exception as e:
                logging.error(f"[API] - Could not claim file '{indd_file.name}': {e}")
        
        for claimed_file in claimed_files:
            job_queue.put(claimed_file)
            logging.info(f"[API] - Queued job for: {claimed_file.name}")

        return jsonify({
            "status": "success",
            "message": f"Successfully queued {len(claimed_files)} files for processing.",
            "files_queued": len(claimed_files)
        })
    finally:
        folder_scan_lock.release()

# --- The Status Endpoint ---
@app.route('/status', methods=['GET'])
def get_status():
    """
    API endpoint to check the current status of the service.
    """
    # Use the lock to safely read the shared status object
    with status_lock:
        # Make a copy to ensure the data is consistent
        current_status = status_info.copy()
    
    # Add the current queue size to the response (qsize is thread-safe)
    current_status['jobs_waiting_in_queue'] = job_queue.qsize()
    
    return jsonify(current_status)

# --- APPLICATION ENTRY POINT ---
if __name__ == '__main__':
    # We need this handler for daily log rotation
    import logging.handlers

    project_root = Path().resolve()
    config.read(project_root / 'config.ini')

    # --- Professional, Rotated Logging Setup ---
    log_folder = project_root / config.get('Paths', 'log_folder')
    log_folder.mkdir(exist_ok=True)
    
    # The base name for our log file. The date will be added automatically.
    log_file_path = log_folder / "main_listener.log"

    # 1. Create the handler that rotates files daily at midnight.
    # It will keep the last 30 log files as backups.
    handler = logging.handlers.TimedRotatingFileHandler(
        log_file_path, 
        when='midnight', 
        interval=1, 
        backupCount=30
    )
    
    # 2. Create a formatter using your exact, proven format string.
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(threadName)s] - %(message)s")
    handler.setFormatter(formatter)

    # 3. Get the root logger, set its level, and add our new handler.
    # This replaces the old basicConfig call.
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    # 4. Also add a handler to continue printing logs to the console.
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # --- Self-Healing Startup Recovery ---
    input_folder = project_root / config.get('Paths', 'input_folder')
    temp_processing_folder = project_root / "temp_processing"
    file_system.recover_orphaned_files(temp_processing_folder, input_folder)
    
    # --- CLean up the temp folder ---
    file_system.cleanup_empty_temp_folder(temp_processing_folder)

    # Start the background worker thread
    worker = threading.Thread(target=worker_thread, name="WorkerThread")
    worker.daemon = True
    worker.start()

    # Start the Flask web server
    logging.info("Starting Flask API server. Listening on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000)