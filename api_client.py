# api_client.py
import logging
from pathlib import Path

# We will need to add the 'requests' library to our requirements.txt
try:
    import requests
except ImportError:
    # This will be handled by the main orchestrator's check
    pass

def send_completion_callback(output_folder_path, request_id, filename, config):
    """
    Sends a POST request to the configured callback URL, including the
    requestId and original filename for end-to-end job tracking.
    """
    try:
        # Read the callback URL from the config file
        callback_url = config.get('Callback', 'url')
    except Exception as e:
        logging.error(f"[ReqID: {request_id}] Could not read callback URL from config.ini. Error: {e}")
        return False

    logging.info(f"[ReqID: {request_id}] Preparing to send completion callback to: {callback_url}")

    # --- The payload now also includes the original filename ---
    payload = {
        "requestId": request_id,
        "fileName": filename,
        "status": "success",
        "message": "InDesign processing and resize complete.",
        "outputFolderPath": Path(output_folder_path).resolve().as_posix()
    }

    try:
        # Make the POST request with a reasonable timeout.
        response = requests.post(callback_url, json=payload, timeout=30)

        # Check the response from the server.
        if 200 <= response.status_code < 300:
            logging.info(f"[ReqID: {request_id}] Callback sent successfully. Server responded with status {response.status_code}.")
            logging.info(f"[ReqID: {request_id}] Server response: {response.text}")
            return True
        else:
            # If the server responds with an error code (4xx or 5xx)
            logging.error(f"[ReqID: {request_id}] Callback failed. Server responded with an error.")
            logging.error(f"[ReqID: {request_id}] Status Code: {response.status_code}")
            logging.error(f"[ReqID: {request_id}] Response Body: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        # This catches network errors (e.g., the server is down, DNS failed).
        logging.error(f"[ReqID: {request_id}] A network error occurred while sending the callback: {e}", exc_info=True)
        return False
    except Exception as e:
        # Catch any other unexpected errors.
        logging.error(f"[ReqID: {request_id}] An unexpected error occurred in the API client: {e}", exc_info=True)
        return False

