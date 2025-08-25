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
    launches the orchestrator subprocess for each job tuple (path, requestId).
    """
    project_root = Path().resolve()
    orchestrator_script_path = project_root / 'orchestrator.py'

    logging.info("Worker thread started. Waiting for jobs...")

    while True:
        # The queue now contains a tuple: (path_to_file, request_id)
        job_item = job_queue.get()
        if job_item is None: break

        file_to_process, request_id = job_item

        # ---  Update status before processing ---
        with status_lock:
            status_info["status"] = "processing"
            status_info["current_file"] = str(file_to_process.name)
            status_info["current_request_id"] = request_id # Add request ID to status
        
        logging.info(f"[WORKER] - Picked up job for: {file_to_process.name} with Request ID: {request_id}")
        
        try:
            # --- Pass the requestId as a second argument to the orchestrator ---
            process = subprocess.run(
                [sys.executable, str(orchestrator_script_path), str(file_to_process), request_id],
                capture_output=True,
                text=True,
                check=True
            )
            logging.info(f"[WORKER] - Subprocess for '{file_to_process.name}' (ID: {request_id}) completed successfully.")

        except subprocess.CalledProcessError as e:
            logging.error(f"[WORKER] - Subprocess for '{file_to_process.name}' (ID: {request_id}) FAILED.")
            logging.error(f"[WORKER] - Output:\n{e.stderr}")
        
        except Exception as e:
            logging.error(f"[WORKER] - A critical error occurred while running subprocess for ID {request_id}: {e}", exc_info=True)

        finally:
            # ---  Update status after processing is complete ---
            with status_lock:
                status_info["status"] = "idle"
                status_info["current_file"] = None
                status_info["current_request_id"] = None # Clear request ID
            
            job_queue.task_done()
            
# --- THE FLASK API (THE "PRODUCER") ---
app = Flask(__name__)

@app.route('/run-indigo-process', methods=['POST']) # Renamed endpoint for clarity
def run_indigo_process():
    """
    API endpoint that accepts a specific filename and requestId,
    claims the file, and adds it to the processing queue.
    """
    project_root = Path().resolve()
    input_folder = project_root / config.get('Paths', 'input_folder')
    temp_processing_folder = project_root / "temp_processing"
    temp_processing_folder.mkdir(exist_ok=True)

    # 1. Get and validate the JSON payload from the request
    data = request.get_json()
    if not data or 'requestId' not in data or 'filename' not in data:
        return jsonify({"status": "error", "message": "Invalid request body. 'requestId' and 'filename' are required."}), 400
    
    request_id = data['requestId']
    # Sanitize filename to prevent directory traversal attacks
    filename = Path(data['filename']).name
    
    logging.info(f"[API] - Received job request for file: '{filename}' with Request ID: {request_id}")

    # 2. Check if the requested file actually exists in the input folder
    source_file_path = input_folder / filename
    if not source_file_path.is_file():
        logging.warning(f"[API] - Requested file not found: {source_file_path}")
        return jsonify({"requestId": request_id, "status": "error", "message": "File not found in input directory."}), 404

    # 3. Claim the file by moving it to the temporary processing directory
    try:
        dest_path = temp_processing_folder / filename
        shutil.move(str(source_file_path), str(dest_path))
        logging.info(f"[API] - Claimed file '{filename}' and moved to temp folder.")
    except Exception as e:
        logging.error(f"[API] - Could not claim file '{filename}': {e}")
        return jsonify({"requestId": request_id, "status": "error", "message": "Failed to move file for processing."}), 500
    
    # 4. Add the job (as a tuple) to the queue
    job_item = (dest_path, request_id)
    job_queue.put(job_item)
    logging.info(f"[API] - Queued job for: {filename} with Request ID: {request_id}")

    # 5. Return an immediate success response
    return jsonify({
        "requestId": request_id,
        "filename": filename,
        "status": "queued"
    }), 200

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