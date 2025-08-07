# indesign_ui.py
import logging
import shutil
import time
import os
import pyperclip
from pathlib import Path

import file_system 

try:
    import pyautogui
    from pywinauto.application import Application
    from pywinauto import Desktop
except ImportError:
    pass

# --- HELPER FUNCTIONS  ---
def find_and_click_image(image_path, confidence=0.9, retries=2, delay_seconds=10, description="image"):
    for attempt in range(retries):
        logging.info(f"Searching for {description}, attempt {attempt + 1} of {retries}...")
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
            if location:
                pyautogui.click(location)
                logging.info(f"Successfully found and clicked {description}.")
                return True
        except Exception:
            pass
        if attempt < retries - 1:
            logging.info(f"{description.capitalize()} not found. Retrying in {delay_seconds} seconds...")
            time.sleep(delay_seconds)
    logging.warning(f"Could not find {description} after {retries} attempts.")
    return False

# --- CORE UI FUNCTIONS ---
def handle_opening_dialogs(app, config):
    # This is your proven, working function. It is unchanged.
    project_root = Path().resolve()
    images_root = project_root / config.get('Paths', 'image_assets_folder')
    OK_BUTTON = str(images_root / config.get('ImageFiles', 'ok_button'))
    SKIP_FONTS_BUTTON = str(images_root / config.get('ImageFiles', 'skip_fonts_button'))
    num_retries = 2
    retry_delay_seconds = 10
    logging.info("UI Automation: Watching for 'Missing Links' dialog...")
    for attempt in range(num_retries):
        logging.info(f"Searching for 'OK' button, attempt {attempt + 1} of {num_retries}...")
        try:
            button_location = pyautogui.locateCenterOnScreen(OK_BUTTON, confidence=0.9)
            if button_location:
                pyautogui.click(button_location)
                logging.info("UI Automation: Handled 'Missing Links' dialog successfully.")
                break
        except Exception:
            if attempt < num_retries - 1:
                logging.info(f"Button not found. Retrying in {retry_delay_seconds} seconds...")
                time.sleep(retry_delay_seconds)
            else:
                logging.info("UI Automation: 'Missing Links' dialog did not appear after all attempts.")
    logging.info("UI Automation: Watching for 'Missing Fonts' dialog...")
    for attempt in range(num_retries):
        logging.info(f"Searching for 'Skip' button, attempt {attempt + 1} of {num_retries}...")
        try:
            button_location = pyautogui.locateCenterOnScreen(SKIP_FONTS_BUTTON, confidence=0.9)
            if button_location:
                pyautogui.click(button_location)
                logging.info("UI Automation: Handled 'Missing Fonts' dialog successfully.")
                break
        except Exception:
            if attempt < num_retries - 1:
                logging.info(f"Button not found. Retrying in {retry_delay_seconds} seconds...")
                time.sleep(retry_delay_seconds)
            else:
                logging.info("UI Automation: 'Missing Fonts' dialog did not appear after all attempts.")
    logging.info("UI Automation: Initial dialog handling complete.")

def export_html_via_ui(indd_path, config):
    """
    Exports a single InDesign file to HTML.
    This version includes the "Clean Slate" logic to delete old output first.
    """
    project_root = Path().resolve()
    images_root = project_root / config.get('Paths', 'image_assets_folder')
    output_folder = project_root / config.get('Paths', 'output_folder')
    EXPORT_IMAGE = str(images_root / config.get('ImageFiles', 'export_button'))
    CANCEL_RECOVER_BUTTON = str(images_root / config.get('ImageFiles', 'cancel_recover_button'))
    initial_launch_wait = config.getint('Settings', 'initial_launch_wait')
    inter_action_wait = config.getint('Settings', 'inter_action_wait')
    process_wait = config.getint('Settings', 'process_wait')
    
    app = None
    try:
        # REQUIREMENT 1: "Clean Slate" logic for the export output.
        final_output_path = output_folder / indd_path.stem
        if final_output_path.exists():
            logging.warning(f"Output folder '{final_output_path.name}' already exists. Deleting it to ensure a clean export.")
            try:
                shutil.rmtree(final_output_path)
            except OSError as e:
                logging.error(f"FATAL: Could not delete existing output folder '{final_output_path}'. Error: {e}")
                return False
        
        # This is your proven, working UI automation logic.
        command_line = f'"{config.get("Paths", "indesign_executable")}" "{indd_path}"'
        app = Application(backend="win32").start(command_line)
        time.sleep(initial_launch_wait)
        find_and_click_image(CANCEL_RECOVER_BUTTON, confidence=0.9, retries=1, description="Cancel Recovery button")
        time.sleep(inter_action_wait)
        handle_opening_dialogs(app, config)
        main_window = app.window(title_re=f".*{indd_path.name}.*").wait('visible', timeout=30)
        main_window.set_focus()
        main_window.type_keys("^e")
        export_dialog = app.window(title="Export", class_name="#32770").wait('visible', timeout=15)
        export_dialog.type_keys("{TAB}h{DOWN 2}{ENTER}")
        pyperclip.copy(str(output_folder))
        export_dialog.type_keys("{TAB 7}{ENTER}")
        export_dialog.type_keys("^v{ENTER}")
        time.sleep(3)
        export_dialog.type_keys("{TAB 10}{ENTER 2}")
        try:
            app.window(title="Warning").wait('visible', timeout=5).type_keys("{ENTER}")
            time.sleep(inter_action_wait)
        except Exception: pass
        html_options_dialog = None
        start_time = time.time()
        while time.time() - start_time < 30:
            for win in Desktop(backend="uia").windows():
                title = win.window_text().strip()
                if title and "InDesign" not in title and "Warning" not in title:
                    html_options_dialog = win
                    break
            if html_options_dialog: break
            time.sleep(0.5)
            
        time.sleep(15)
        
        if html_options_dialog:
            html_options_dialog.set_focus()
            if not find_and_click_image(EXPORT_IMAGE, confidence=0.8, description="Export button"):
                html_options_dialog.type_keys("{TAB 6}{ENTER}")
        else: raise RuntimeError("Export HTML5 Package dialog not found.")
        time.sleep(process_wait)
        try:
            app.window(title="Export HTML5 package warning(s)").wait('visible', timeout=20).type_keys("{ENTER}")
        except Exception: pass
        
        time.sleep(process_wait)
        
        try:
            Desktop(backend="win32").window(title_re=f"^{indd_path.stem}.*", class_name="CabinetWClass").wait('visible', timeout=15).close()
        except Exception: 
            pass
        
        app.kill()
        
        time.sleep(3)
        
        return True
    
    except Exception as e:
        logging.error(f"An error occurred during the InDesign UI workflow: {e}", exc_info=True)
        if app and app.is_process_running(): app.kill()
        return False

def run_resize_on_folder(target_folder_path, config):
    """
    Launches a clean InDesign instance and runs the resize script.
    This version uses a resilient VISUAL check for the completion signal
    and calls the updated artifact verification method.
    """
    project_root = Path().resolve()
    scripts_folder = project_root / config.get('Paths', 'scripts_folder')
    indesign_executable = config.get('Paths', 'indesign_executable')
    indesign_version_folder = config.get('Paths', 'indesign_version_folder')
    images_root = project_root / config.get('Paths', 'image_assets_folder')
    
    CANCEL_RECOVER_BUTTON = str(images_root / config.get('ImageFiles', 'cancel_recover_button'))
    NO_BUTTON = str(images_root / config.get('ImageFiles', 'no_button'))
    USER_SCRIPTS_FOLDER = str(images_root / config.get('ImageFiles', 'user_scripts_folder'))
    RESIZE_ALL_SCRIPT = str(images_root / config.get('ImageFiles', 'resize_all_script'))
    SIGNAL_OK_BUTTON = str(images_root / config.get('ImageFiles', 'signal_ok_button'))
    
    initial_launch_wait = config.getint('Settings', 'initial_launch_wait')
    inter_action_wait = config.getint('Settings', 'inter_action_wait')
    process_timeout = config.getint('Settings', 'process_timeout')
    
    logging.info(f"--- Starting Resize Process for folder: {target_folder_path} ---")
    
    source_script_path = scripts_folder / "resizeall.jsx" # <-- Note the .jsx extension
    dest_script_path = None
    app = None
    
    try:
        # This is your proven, working UI automation logic.
        appdata_path = Path(os.getenv('APPDATA'))
        dest_script_folder = appdata_path / "Adobe" / "InDesign" / indesign_version_folder / "en_US" / "Scripts" / "Scripts Panel"
        dest_script_folder.mkdir(parents=True, exist_ok=True)
        dest_script_path = dest_script_folder / source_script_path.name
        shutil.copy2(source_script_path, dest_script_path)
        app = Application(backend="win32").start(indesign_executable)
        app.wait_cpu_usage_lower(threshold=5, timeout=60)
        time.sleep(initial_launch_wait)
        
        cancel_clicked = find_and_click_image(CANCEL_RECOVER_BUTTON, confidence=0.9, retries=2, delay_seconds=10, description="'Cancel' button")
        if not cancel_clicked:
            no_clicked = find_and_click_image(NO_BUTTON, confidence=0.9, retries=2, delay_seconds=10, description="'No' button")
            if not no_clicked:
                try:
                    app.window(title_re=".*Adobe InDesign.*").wait('visible', timeout=10).set_focus().type_keys("{ENTER}")
                except Exception:
                    logging.info("No recovery dialog detected programmatically.")
        logging.info("Recovery dialog handling complete.")
        time.sleep(inter_action_wait)
        main_window = app.window(title_re=".*Adobe InDesign.*").wait('visible', timeout=30)
        main_window.set_focus()
        main_window.type_keys("^%{F11}")
        time.sleep(inter_action_wait)
        
        resize_found_directly = find_and_click_image(RESIZE_ALL_SCRIPT, confidence=0.9, description="'resizeall' script (direct search)")
        if resize_found_directly:
            location = pyautogui.locateCenterOnScreen(RESIZE_ALL_SCRIPT, confidence=0.9)
            if location: pyautogui.doubleClick(location)
        else:
            user_folder_found = find_and_click_image(USER_SCRIPTS_FOLDER, confidence=0.9, description="'User' folder")
            if user_folder_found:
                location = pyautogui.locateCenterOnScreen(USER_SCRIPTS_FOLDER, confidence=0.9)
                if location: pyautogui.doubleClick(location)
                time.sleep(2)
                final_resize_found = find_and_click_image(RESIZE_ALL_SCRIPT, confidence=0.9, description="'resizeall' script (after expanding User)")
                if final_resize_found:
                    location = pyautogui.locateCenterOnScreen(RESIZE_ALL_SCRIPT, confidence=0.9)
                    if location: pyautogui.doubleClick(location)
                else:
                    raise RuntimeError("Could not find 'resizeall' script after expanding 'User' folder.")
            else:
                raise RuntimeError("Could not find 'User' folder in the Scripts Panel.")

        choose_folder_dialog = app.window(title="Choose Folder").wait('visible', timeout=20)
        choose_folder_dialog.set_focus()
        input_folder_for_resize = str(target_folder_path.resolve())
        choose_folder_dialog.type_keys("{TAB}")
        pyperclip.copy(input_folder_for_resize)
        choose_folder_dialog.type_keys("^v{ENTER}")

        logging.info("Resize script is now running. Waiting for visual completion signal...")
        
        start_time = time.time()
        signal_found = False
        while time.time() - start_time < process_timeout:
            if find_and_click_image(SIGNAL_OK_BUTTON, confidence=0.9, retries=1, description="completion signal OK button"):
                signal_found = True
                break
            time.sleep(5)

        if not signal_found:
            raise RuntimeError("Timeout waiting for the visual completion signal alert.")
        
        # --- MODIFIED: Artifact Validation ---
        # We now call the updated verification function, passing the document stem and config.
        # It will construct the final path itself, ensuring it checks the correct destination.
        indd_stem = target_folder_path.name
        is_valid = file_system.verify_resize_output(indd_stem, config)
        
        if is_valid:
            logging.info(f"--- Resize Process and Verification Successful for folder: {target_folder_path.name} ---")
            return True
        else:
            raise RuntimeError(f"Artifact validation failed for folder: {target_folder_path.name}")

    except Exception as e:
        logging.error(f"An error occurred during the resize phase: {e}", exc_info=True)
        return False
    finally:
        if app and app.is_process_running():
            app.kill()
        if dest_script_path and dest_script_path.exists():
            try: dest_script_path.unlink()
            except OSError as e: logging.warning(f"Could not delete script: {e}")
            
                    
            