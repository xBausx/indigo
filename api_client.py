# api_client.py
import logging
from pathlib import Path

# We will need to add the 'requests' library to our requirements.txt
try:
    import requests
except ImportError:
    # This will be handled by the main orchestrator's check
    pass

def send_completion_callback(output_folder_path, config):
    """
    Sends a POST request to the configured callback URL with the path of the
    successfully processed output folder.
    """
    try:
        # Read the callback URL from the config file
        callback_url = config.get('Callback', 'url')
    except Exception as e:
        logging.error(f"Could not read callback URL from config.ini. Error: {e}")
        return False

    logging.info(f"Preparing to send completion callback to: {callback_url}")

    # Create the JSON payload. We send the absolute path to the output folder.
    # The '.as_posix()' method ensures forward slashes, which is a common
    # convention for paths in JSON payloads.
    payload = {
        "status": "success",
        "message": "InDesign processing and resize complete.",
        "outputFolderPath": Path(output_folder_path).resolve().as_posix()
    }

    try:
        # Make the POST request with a reasonable timeout.
        response = requests.post(callback_url, json=payload, timeout=30)

        # Check the response from the server.
        # A successful call will typically have a status code in the 200s.
        if 200 <= response.status_code < 300:
            logging.info(f"Callback sent successfully. Server responded with status {response.status_code}.")
            logging.info(f"Server response: {response.text}")
            return True
        else:
            # If the server responds with an error code (4xx or 5xx)
            logging.error(f"Callback failed. Server responded with an error.")
            logging.error(f"Status Code: {response.status_code}")
            logging.error(f"Response Body: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        # This catches network errors (e.g., the server is down, DNS failed).
        logging.error(f"A network error occurred while sending the callback: {e}", exc_info=True)
        return False
    except Exception as e:
        # Catch any other unexpected errors.
        logging.error(f"An unexpected error occurred in the API client: {e}", exc_info=True)
        return False