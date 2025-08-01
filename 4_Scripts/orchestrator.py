# -*- coding: utf-8 -*-
"""
@file orchestrator.py
@description Project Indigo: Python Orchestrator Script.
This version introduces a robust retry mechanism and a two-tiered logging system
for enterprise-grade resilience and diagnostics.

@version 9.0.0 (Retry Logic & Detailed Logging)
"""

import logging
import shutil
import time
from pathlib import Path
from datetime import datetime
import os
import pyperclip

# --- UI AUTOMATION (RPA) SETUP ---
try:
    import pyautogui
    from pywinauto.application import Application
    from pywinauto import Desktop
except ImportError:
    print("ERROR: pywinauto is not installed. Please run 'pip install pywinauto' in your terminal.")
    exit()


# ======================================================================================
# --- CONFIGURATION ---
# ======================================================================================

# --- PROJECT PATHS (DYNAMIC) ---
SCRIPTS_FOLDER = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_FOLDER.parent
INPUT_FOLDER = PROJECT_ROOT / "1_Input_Files"
OUTPUT_FOLDER = PROJECT_ROOT / "2_Output_HTML"
PROCESSED_FOLDER = PROJECT_ROOT / "3_Processed_Files"
ERROR_FOLDER = PROJECT_ROOT / "5_Error_Files"
LOG_FOLDER = PROJECT_ROOT / "6_Logs"
# --- NEW in v9.0: Dedicated folder for detailed, per-file logs ---
DETAILED_LOG_FOLDER = PROJECT_ROOT / "7_Detailed_Logs"
EXPORT_IMAGE = str(PROJECT_ROOT / "8_Images" / "export_button.png")
SKIP_FONTS_BUTTON = str(PROJECT_ROOT / "8_Images" / "skip_fonts_button.png")
CANCEL_RECOVER_BUTTON = str(PROJECT_ROOT / "8_Images" / "cancel_recover_button.png")
NO_BUTTON = str(PROJECT_ROOT / "8_Images" / "no_button.png")
OK_BUTTON = str(PROJECT_ROOT / "8_Images" / "ok_button.png")
USER_SCRIPTS_FOLDER = str(PROJECT_ROOT / "8_Images" / "user_scripts_folder.png")
RESIZE_ALL_SCRIPT = str(PROJECT_ROOT / "8_Images" / "resize_all_script.png")
SIGNAL_FILE = str(PROJECT_ROOT / "resize_complete.txt")

# --- INDESIGN PATH ---
INDESIGN_EXECUTABLE_PATH = Path("C:/Program Files/Adobe/Adobe InDesign 2025/InDesign.exe")
INDESIGN_VERSION_FOLDER = "Version 20.0"

# --- TIMING & RETRY CONFIGURATION ---
PROCESS_TIMEOUT = 30 * 60 
INITIAL_LAUNCH_WAIT = 40
INTER_ACTION_WAIT = 5 
PROCESS_WAIT = 15
# --- NEW in v9.0: Retry settings ---
MAX_RETRIES = 3 # Total number of attempts for a single file
RETRY_DELAY_SECONDS = 10 # Seconds to wait between failed attempts

# ======================================================================================
# --- SCRIPT LOGIC ---
# ======================================================================================

def setup_global_logging():
    """Sets up the main, high-level log file."""
    LOG_FOLDER.mkdir(exist_ok=True)
    # --- NEW in v9.0: Create the detailed logs folder ---
    DETAILED_LOG_FOLDER.mkdir(exist_ok=True)
    
    log_filename = f"{datetime.now().strftime('%Y-%m-%d')}_indigo.log"
    log_filepath = LOG_FOLDER / log_filename
    
    # Configure the root logger
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] - %(message)s", handlers=[logging.FileHandler(log_filepath), logging.StreamHandler()])

def clear_indesign_cache():
    """Finds and deletes InDesign's cache and recovery folders for a fresh start."""
    logging.info("Clearing InDesign cache and recovery directories...")
    paths_to_check = [
        Path(os.path.expanduser('~')) / "AppData/Local/Adobe/InDesign",
        Path(os.path.expanduser('~')) / "AppData/Roaming/Adobe/InDesign"
    ]
    
    for path in paths_to_check:
        if path.exists():
            for item in path.iterdir():
                if item.is_dir() and item.name.lower().startswith("version"):
                    try:
                        shutil.rmtree(item)
                        logging.info(f"Successfully deleted cache folder: {item}")
                    except OSError as e:
                        logging.warning(f"Could not delete cache folder {item}: {e}. It might be in use.")
        else:
            logging.info(f"Cache path not found, skipping: {path}")

def cleanup_lock_files():
    """
    Scans the input folder and deletes any lingering InDesign lock files (.idlk).
    This is a housekeeping function to run at the end of the process.
    """
    logging.info("--- Starting final cleanup of InDesign lock files (.idlk) ---")
    try:
        # Use glob to efficiently find all files ending with the .idlk extension.
        lock_files = list(INPUT_FOLDER.glob("*.idlk"))
        
        if not lock_files:
            logging.info("No InDesign lock files found to clean up.")
            return

        logging.info(f"Found {len(lock_files)} lock file(s) to delete.")
        
        for lock_file in lock_files:
            try:
                # The unlink() method deletes the file.
                lock_file.unlink()
                logging.info(f"Successfully deleted lock file: {lock_file.name}")
            except OSError as e:
                # This handles cases where the file might be write-protected or in use.
                logging.warning(f"Could not delete lock file '{lock_file.name}': {e}")
                
        logging.info("--- Lock file cleanup complete ---")
        
    except Exception as e:
        # Catch any other unexpected errors during the cleanup process.
        logging.error(f"An unexpected error occurred during lock file cleanup: {e}", exc_info=True)

# --- The core automation functions (handle_opening_dialogs, export_html_via_ui) are unchanged ---
# They will now be called within the new retry loop.

def run_resize_phase():
    """
    After all HTML exports are done, this function runs the batch resize script.
    It copies the script to the user's panel, runs it via UI automation,
    and then cleans up after itself.
    """
    logging.info("==========================================================")
    logging.info("--- Starting Final Resize Phase ---")
    
    source_script_path = SCRIPTS_FOLDER / "resizeall.js"
    if not source_script_path.exists():
        logging.error(f"FATAL: Cannot start resize phase. The script '{source_script_path.name}' was not found in the '4_Scripts' folder.")
        return

    try:
        appdata_path = Path(os.getenv('APPDATA'))
        dest_script_folder = appdata_path / "Adobe" / "InDesign" / INDESIGN_VERSION_FOLDER / "en_US" / "Scripts" / "Scripts Panel"
        dest_script_folder.mkdir(parents=True, exist_ok=True)
        dest_script_path = dest_script_folder / source_script_path.name
    except Exception as e:
        logging.error(f"FATAL: Could not construct the destination path for the InDesign Scripts Panel. Error: {e}", exc_info=True)
        return

    app = None
    try:
        logging.info(f"Copying '{source_script_path.name}' to '{dest_script_folder}'...")
        shutil.copy2(source_script_path, dest_script_path)
        
        logging.info("Launching a fresh instance of InDesign for the resize phase...")
        app = Application(backend="win32").start(str(INDESIGN_EXECUTABLE_PATH))
        app.wait_cpu_usage_lower(threshold=5, timeout=60)
        
        
        logging.info("UI Automation: Watching for 'Document Recovery' dialog...")
        
        time.sleep(INITIAL_LAUNCH_WAIT)
        
        try:
            button_location = pyautogui.locateCenterOnScreen(CANCEL_RECOVER_BUTTON, confidence=0.9)
            if button_location:
                logging.info("'Cancel' button on recovery dialog found. Clicking to ensure a clean state.")
                pyautogui.click(button_location)
        except Exception:
            logging.info("UI Automation: 'Cancel' button did not appear. Will look for 'No' Button.")
            
            try:
                button_location = pyautogui.locateCenterOnScreen(NO_BUTTON, confidence=0.9)
                if button_location:
                    logging.info("'No' button on recovery dialog found. Clicking to ensure a clean state.")
                    pyautogui.click(button_location)
            except Exception:
                logging.info("UI Automation: 'No' button on recovery dialog not found. Will click ENTER and continue normally.")
                app_window = app.window(title_re=".*Adobe InDesign.*")
                app_window.wait('visible', timeout=30).set_focus()
                app_window.type_keys("{ENTER}")

        time.sleep(INTER_ACTION_WAIT)
        
        main_app_window = app.window(title_re=".*Adobe InDesign.*")
        main_app_window.wait('visible', timeout=30).set_focus()
        
        logging.info("UI Automation: Opening Scripts Panel...")
        main_app_window.type_keys("^%{F11}")
        time.sleep(3)
        
        time.sleep(PROCESS_WAIT)
        
        # --- Use the 'uia' backend to find modern floating panels. ---
        logging.info("Searching for Scripts panel using the UIA backend...")
        
        try:
            
            # Check if resizeall script is already in the Scripts Panel
            isVisible = False
            
            try:
                logging.info("Check if 'resizeall' script is already in the Scripts Panel...")
                resize_all_script_location = pyautogui.locateCenterOnScreen(RESIZE_ALL_SCRIPT, confidence=0.9)
                
                isVisible = True
                
                logging.info("resizeall script found in Scripts Panel. Skipping Step 1.")
            
            except Exception:
                logging.info("Resize script not found in Scripts Panel. Proceeding to find 'User' folder...")
            
            if not isVisible:
                
                logging.info("UI Automation: Step 1 - Visually finding 'User' folder...")
                
                user_folder_location = pyautogui.locateCenterOnScreen(USER_SCRIPTS_FOLDER, confidence=0.9)
                if not user_folder_location:
                    raise pyautogui.ImageNotFoundException("Could not find the 'User' folder image.")
                
                pyautogui.doubleClick(user_folder_location)
                logging.info("'User' folder found and double-clicked.")
                
                time.sleep(3)
                
        finally:
                logging.info("UI Automation: Step 2 - Programmatically finding 'resizeall' script...")
                resize_all_script_location = pyautogui.locateCenterOnScreen(RESIZE_ALL_SCRIPT, confidence=0.9)
                
                if not resize_all_script_location:
                    raise pyautogui.ImageNotFoundException("Could not find the 'resizeall' folder image.")
                
                pyautogui.doubleClick(resize_all_script_location)
            
                logging.info("Successfully selected resizeall script.")

        logging.info("UI Automation: Waiting for 'Choose Folder' dialog...")
        # Be specific with the title for reliability
        choose_folder_dialog = app.window(title="Choose Folder").wait('visible', timeout=20)
        choose_folder_dialog.set_focus()
        
        input_folder_for_resize = str(PROCESSED_FOLDER)
        logging.info(f"UI Automation: Directly setting path to '{input_folder_for_resize}'...")

        # --- Interact with the controls directly instead of sending keys ---
        
        # 1. Find the text input field (its control type is 'Edit') and set its text directly.
        # This is the most reliable method and avoids focus issues.
        
        choose_folder_dialog.type_keys("{TAB}")  # Navigate to the text input field
        pyperclip.copy(str(input_folder_for_resize))
        choose_folder_dialog.type_keys("^v")
        choose_folder_dialog.type_keys("{ENTER}")  # Press Enter to confirm the path

    except Exception as e:
        logging.error(f"An error occurred during the resize phase: {e}", exc_info=True)
    
    finally:
        
        start_time = time.time()
        while time.time() - start_time < PROCESS_TIMEOUT:
            if os.path.exists(SIGNAL_FILE):
                with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
                    completion_message = f.read()
                logging.info("Completion signal received from InDesign script.")
                logging.info("Message: %s", completion_message)
                
                try:
                    os.remove(SIGNAL_FILE)
                    logging.info(f"Deleted signal file: {SIGNAL_FILE}")
                except OSError as e:
                    logging.warning(f"Could not delete signal file: {e}")
        
                break
            
            time.sleep(1)
        else:
            logging.error("Timeout waiting for completion signal.")

        logging.info("--- Resize Phase Completed Successfully ---")
        
        if dest_script_path.exists():
            logging.info(f"Cleaning up by deleting '{dest_script_path.name}' from Scripts Panel.")
            try:
                dest_script_path.unlink()
            except OSError as e:
                logging.warning(f"Could not delete script from Scripts Panel: {e}")
        
        return app
    
        logging.info("==========================================================")
        
def handle_opening_dialogs(app):
    """Handles the initial 'Missing Links' and 'Missing Fonts' dialogs."""
    
    logging.info("UI Automation: Watching for 'Missing Links' dialog...")
    try:
        # We will search the entire screen for the OK button image.
        # The timeout makes this a resilient wait, only pausing as long as needed, up to 25 seconds.
        logging.info("Searching for the 'OK' button via image recognition...")
        
        button_location = pyautogui.locateCenterOnScreen(
            OK_BUTTON, 
            confidence=0.9
        )
        
        # If the locate function returns a location, the button was found.
        if button_location:
            logging.info("'OK' button on 'Missing Links' dialog found. Clicking it...")
            pyautogui.click(button_location)
            logging.info("UI Automation: Handled 'Missing Links' dialog.")
        # No 'else' is needed because the timeout will raise an exception if not found.

    except pyautogui.ImageNotFoundException:
        # This is the expected and normal outcome if the document has no missing links.
        logging.info("UI Automation: 'Missing Links' dialog and/or its OK button did not appear within the timeout. Continuing.")
    except Exception as e:
        # Catch any other unexpected errors during this check.
        logging.warning(f"An unexpected error occurred while checking for the 'Missing Links' dialog: {e}")

    time.sleep(PROCESS_WAIT)
    
    logging.info("UI Automation: Handling 'Missing Fonts' dialog...")
    try:
        # First, find the dialog window itself.
        fonts_dialog = app.window(title="Missing Fonts", class_name="#32770")
        fonts_dialog.wait('visible', timeout=25)
        fonts_dialog.set_focus()

        # Attempt to find and click the button using the provided image.
        logging.info("Attempting to click 'Skip' button via image recognition...")
        
        # Use a confidence level to ensure we don't click the wrong thing.
        button_location = pyautogui.locateCenterOnScreen(SKIP_FONTS_BUTTON, confidence=0.9)

        # If the image was found on screen...
        if button_location:
            pyautogui.click(button_location)
            logging.info("'Skip' button clicked successfully via image recognition.")
        # If the image was NOT found...
        else:
            logging.warning("Image recognition failed for 'Skip' button. Falling back to keystroke method.")
            # This is the original keystroke sequence as a backup. A single {ENTER} is usually sufficient.
            fonts_dialog.type_keys("{TAB 2}{ENTER}")
            logging.info("Sent fallback keystrokes to handle dialog.")

        logging.info("UI Automation: Handled 'Missing Fonts' dialog.")

    except Exception:
        # This is not an error, it just means the dialog did not appear.
        logging.info("UI Automation: 'Missing Fonts' dialog did not appear.")
    
    logging.info("UI Automation: Initial dialog handling complete.")
def export_html_via_ui(app, indd_file):
    try:
        logging.info("UI Automation: Starting HTML export process...")
        main_window = app.window(title_re=f".*{indd_file.name}.*")
        main_window.wait('visible', timeout=30).set_focus()

        # Step 1: Send Ctrl+E
        logging.info("Step 1: Sending Ctrl+E...")
        main_window.type_keys("^e")

        export_dialog = app.window(title="Export", class_name="#32770")
        export_dialog.wait('visible', timeout=15)

        # Set file type to HTML
        logging.info("Setting file type to HTML...")
        export_dialog.type_keys("{TAB}")
        export_dialog.type_keys("h")
        export_dialog.type_keys("{DOWN 2}")
        export_dialog.type_keys("{ENTER}")

        # Set output path
        output_filename = OUTPUT_FOLDER
        logging.info(f"Setting output path to: {output_filename}")
        export_dialog.type_keys("{TAB 7}{ENTER}")
        pyperclip.copy(str(output_filename))
        export_dialog.type_keys("^v")
        time.sleep(2)
        export_dialog.type_keys("{ENTER}")
        time.sleep(INTER_ACTION_WAIT)

        # Click Save
        logging.info("Clicking 'Save'...")
        export_dialog.type_keys("{TAB 10}{ENTER}{ENTER}")

        time.sleep(INTER_ACTION_WAIT)
        
        logging.info("Handling 'Export HTML5 Package' dialog...")

        html_options_dialog = None
        start_time = time.time()

        while time.time() - start_time < 30:
            for win in Desktop(backend="uia").windows():
                title = win.window_text().strip()
                if title and "InDesign" not in title and "Warning" not in title:
                    html_options_dialog = win
                    break
            if html_options_dialog:
                break
            time.sleep(0.5)

        if html_options_dialog:
            html_options_dialog.set_focus()
            logging.info(f"Found dialog: '{html_options_dialog.window_text()}'")

            loc = pyautogui.locateCenterOnScreen(EXPORT_IMAGE, confidence=0.9)
            if loc:
                pyautogui.click(loc)
                logging.info("'Export' clicked via image recognition.")
            else:
                logging.warning("Image match failed. Falling back to TAB sequence.")
                html_options_dialog.type_keys("{TAB 6}{ENTER}")
        else:
            logging.error("Export HTML5 Package dialog not found.")

        time.sleep(PROCESS_WAIT)
        
        logging.info("UI Automation: Watching for final 'Export HTML5 package warning(s)' dialog...")
        try:
            # We specifically look for the dialog by its exact title.
            warning_dialog = app.window(title="Export HTML5 package warning(s)", class_name="#32770")
            warning_dialog.wait('visible', timeout=20) # Wait up to 20 seconds for it to appear
            
            logging.info("Found package warning dialog. Setting focus...")
            warning_dialog.set_focus()
            
            # The "Yes" button is the default. A single {ENTER} is the most reliable way to click it.
            logging.info("Activating default 'Yes' button with {ENTER} keystroke.")
            warning_dialog.type_keys("{ENTER}")
            
        except Exception:
            # This is not an error, it just means the file had no missing resources and the dialog didn't appear.
            logging.info("No package warnings appeared, which is normal. Continuing...")

        time.sleep(PROCESS_WAIT) 
        
        logging.info("UI Automation: Watching for post-export File Explorer window...")
        try:
            # The window title should start with the name of the folder, which matches the InDesign file's stem.
            expected_title_stem = indd_file.stem
            
            # We use a regular expression in 'title_re' to find a window that STARTS WITH our stem.
            # This is robust and will work even if Windows truncates the title with "...".
            logging.info(f"Searching for an explorer window that starts with title: '{expected_title_stem}'")
            
            explorer_window = Desktop(backend="win32").window(
                title_re=f"^{expected_title_stem}.*", # Regex for "starts with"
                class_name="CabinetWClass"
            )
            
            explorer_window.wait('visible', timeout=15)
            
            # Log the actual title we found for confirmation, then close it.
            logging.info(f"Found and closing the specific File Explorer window: '{explorer_window.window_text()}'")
            explorer_window.close()

        except Exception:
            # This is not an error, just means the window didn't appear as expected.
            logging.info("No post-export File Explorer window was detected.")
            
        return True

    except Exception as e:
        logging.error(f"UI Automation: An error occurred during the export workflow: {e}", exc_info=True)
        # Re-raise the exception to be caught by the new retry loop
        raise

def main():
    setup_global_logging()
    logging.info("==========================================================")
    logging.info("Indigo Orchestrator run started (Resilient Mode v9.0).")

    indd_files = list(INPUT_FOLDER.glob("*.indd"))
    
    if not indd_files:
        logging.info("No InDesign files found in the input folder. Run complete.")
        return

    for indd_file in indd_files:
        # --- LOGGING v9.0: Set up the dedicated logger for this file ---
        file_log_path = DETAILED_LOG_FOLDER / f"{indd_file.stem}.log"
        file_handler = logging.FileHandler(file_log_path, mode='w') # 'w' to overwrite log for new run
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s"))
        # Add the file-specific handler to the root logger
        logging.getLogger().addHandler(file_handler)
        
        logging.info(f"--- Processing file: {indd_file.name} ---")
        logging.info(f"Detailed log for this file is being written to: {file_log_path}")

        if (OUTPUT_FOLDER / indd_file.stem).exists():
            logging.warning(f"Output for '{indd_file.name}' already exists. Skipping.")
            shutil.move(str(indd_file), str(PROCESSED_FOLDER / indd_file.name))
            # --- LOGGING v9.0: Clean up the file handler ---
            logging.getLogger().removeHandler(file_handler)
            file_handler.close()
            continue

        success = False
        
        for attempt in range(MAX_RETRIES):
            logging.info(f"--- Attempt {attempt + 1} of {MAX_RETRIES} for file: {indd_file.name} ---")
            app = None
            try:
                # Always clear cache before any attempt for maximum stability
                clear_indesign_cache()
                
                command_line = f'"{str(INDESIGN_EXECUTABLE_PATH)}" "{str(indd_file)}"'
                logging.info(f"Launching InDesign with command: {command_line}")
                app = Application(backend="win32").start(command_line)

                time.sleep(INITIAL_LAUNCH_WAIT)
                
                handle_opening_dialogs(app)
                
                time.sleep(INTER_ACTION_WAIT)
                
                if not export_html_via_ui(app, indd_file):
                    # This will be caught by the except block below
                    raise RuntimeError("Export UI workflow returned False.")
                
                # If we get here, the attempt was successful
                logging.info(f"SUCCESS: Attempt {attempt + 1} for '{indd_file.name}' was successful.")
                app.kill()
                time.sleep(INTER_ACTION_WAIT)
                
                shutil.move(str(indd_file), str(PROCESSED_FOLDER / indd_file.name))
                
                success = True
                break # Exit the retry loop

            except Exception as e:
                logging.error(f"FAILURE: Attempt {attempt + 1} for '{indd_file.name}' failed.", exc_info=True)
                if attempt < MAX_RETRIES - 1:
                    logging.info(f"Waiting {RETRY_DELAY_SECONDS} seconds before next attempt...")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    logging.error(f"All {MAX_RETRIES} attempts failed for '{indd_file.name}'. Moving to error folder.")
                    shutil.move(str(indd_file), str(ERROR_FOLDER / indd_file.name))    
        
        success = True
        # --- LOGGING v9.0: Clean up the file handler after all attempts for this file are done ---
        logging.getLogger().removeHandler(file_handler)
        file_handler.close()
        # Log final status to the main global log
        if success:
            logging.info(f"[SUMMARY] Successfully processed {indd_file.name}")
        else:
            logging.info(f"[SUMMARY] Failed to process {indd_file.name} after {MAX_RETRIES} attempts.")
    
    # --- all the final resize phase after all files are processed ---
    app = run_resize_phase()
    
    # Always ensure InDesign is closed after each attempt
    logging.info("Removing InDesign lock files if any...")
    cleanup_lock_files()
    
    time.sleep(2) # Give OS time to release file handles
    
    logging.info("Indigo Orchestrator run finished.")
    logging.info("==========================================================")
    
    logging.info("Closing InDesign application.")
    app.kill()
        

if __name__ == "__main__":
    main()