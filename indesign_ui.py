# indesign_ui.py
import logging
import shutil
import time
import os
import pyperclip
import re
from pathlib import Path

import file_system 

try:
    import pyautogui
    from pywinauto.application import Application
    from pywinauto import Desktop
except ImportError:
    pass

# --- HELPER FUNCTIONS  ---
def find_and_click_image(image_path, confidence=0.9, retries=5, delay_seconds=5, description="image"):
    """
    Looks for an image on screen and clicks it.
    """
    for attempt in range(retries):
        logging.info(f"Searching for {description}, attempt {attempt + 1} of {retries}...")
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
            if location:
                pyautogui.click(location)
                logging.info(f"Successfully found and clicked {description}.")
                return True
        except Exception as e:
            # PyAutoGUI can raise a specific exception if Pillow is not configured for screenshots
            logging.warning(f"An exception occurred while searching for {description}: {e}")

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

    logging.info("UI Automation: Watching for 'Missing Links' dialog...")
    # This now uses the new default of 5 retries, 5 seconds.
    find_and_click_image(OK_BUTTON, confidence=0.9, description="'Missing Links' OK button")

    logging.info("UI Automation: Watching for 'Missing Fonts' dialog...")
    # This also uses the new default of 5 retries, 5 seconds.
    find_and_click_image(SKIP_FONTS_BUTTON, confidence=0.9, description="'Missing Fonts' Skip button")
    
    logging.info("UI Automation: Initial dialog handling complete.")

def export_html_via_ui(indd_path, config):
    """
    Exports a single InDesign file directly to the final output destination
    specified in config.ini.
    """
    project_root = Path().resolve()
    images_root = project_root / config.get('Paths', 'image_assets_folder')
    
    try:
        final_destination_root = Path(config.get('Paths', 'final_flyers_output_folder'))
    except Exception as e:
        logging.error(f"FATAL: Could not read 'final_flyers_output_folder' from config.ini. Error: {e}")
        return False
        
    EXPORT_IMAGE = str(images_root / config.get('ImageFiles', 'export_button'))
    CANCEL_RECOVER_BUTTON = str(images_root / config.get('ImageFiles', 'cancel_recover_button'))
    initial_launch_wait = config.getint('Settings', 'initial_launch_wait')
    inter_action_wait = config.getint('Settings', 'inter_action_wait')
    process_wait = config.getint('Settings', 'process_wait')
    
    app = None
    try:
        # --- "Clean Slate" logic now targets the FINAL destination ---
        final_output_path = final_destination_root / indd_path.stem
        logging.info(f"Ensuring clean export destination: {final_output_path}")
        if final_output_path.exists():
            logging.warning(f"Final output folder '{final_output_path.name}' already exists. Deleting it to ensure a clean export.")
            try:
                shutil.rmtree(final_output_path)
            except OSError as e:
                logging.error(f"FATAL: Could not delete existing output folder '{final_output_path}'. Error: {e}")
                return False
            
        command_line = f'"{config.get("Paths", "indesign_executable")}" "{indd_path}"'
        app = Application(backend="win32").start(command_line)
        
        time.sleep(initial_launch_wait)
        
        find_and_click_image(CANCEL_RECOVER_BUTTON, confidence=0.9, description="Cancel Recovery button")
        
        time.sleep(inter_action_wait)
        handle_opening_dialogs(app, config)
        
        main_window = app.window(title_re=f".*{indd_path.name}.*").wait('visible', timeout=30)
        main_window.set_focus()
        main_window.type_keys("^e") # Ctrl+E for Export
        
        export_dialog = app.window(title="Export", class_name="#32770").wait('visible', timeout=15)
        time.sleep(2)
        export_dialog.type_keys("{TAB}{DOWN}") # Select HTML format       
        time.sleep(1)
        export_dialog.type_keys("html")
        time.sleep(0.5)
        export_dialog.type_keys("{DOWN}")
        time.sleep(0.5)
        export_dialog.type_keys("{ENTER}")           

        logging.info(f"Pasting final destination path to clipboard: {final_destination_root}")
        pyperclip.copy(str(final_destination_root))
        
        export_dialog.type_keys("{TAB 7}{ENTER}") # Navigate to path input field
        export_dialog.type_keys("^v{ENTER}") # Paste and enter the path
        time.sleep(3)
        logging.info(f"Saving the Export to: {final_destination_root}")
        export_dialog.type_keys("{TAB 10}{ENTER 2}") # Save the export
        try:
            app.window(title="Warning").wait('visible', timeout=5).type_keys("{ENTER}")
            time.sleep(inter_action_wait)
        except Exception: pass
        
        html_options_dialog = None
        start_time = time.time()
        
        logging.info(f"Handling HTML5 export options dialog for '{indd_path.name}'...")
        
        while time.time() - start_time < 30:
            for win in Desktop(backend="uia").windows():
                title = win.window_text().strip()
                # Find the "Export HTML5" options dialog which has a dynamic title
                if title and "InDesign" not in title and "Warning" not in title:
                    html_options_dialog = win
                    break
            if html_options_dialog: break
            time.sleep(0.5)
        
        if html_options_dialog:
            html_options_dialog.set_focus()
            if not find_and_click_image(EXPORT_IMAGE, confidence=0.8, description="Export button"):
                html_options_dialog.type_keys("{TAB 6}{ENTER}")
        else: raise RuntimeError("Export HTML5 Package dialog not found.")
        
        logging.info(f"Handled HTML5 export options dialog for '{indd_path.name}'.")
        
        time.sleep(process_wait)
        
        try:
            app.window(title="Export HTML5 package warning(s)").wait('visible', timeout=20).type_keys("{ENTER}")
        except Exception: pass
        
        time.sleep(process_wait)
        
        logging.info(f"Closing the file explorer window for '{indd_path.stem}' if it opened...")
        
        try:
            # Attempt to close the file explorer window that may open
            Desktop(backend="win32").window(title_re=f"^{indd_path.stem}.*", class_name="CabinetWClass").wait('visible', timeout=15).close()
        except Exception: 
            pass
        
        return True
    
    except Exception as e:
        logging.error(f"An error occurred during the Export as HTML workflow: {e}", exc_info=True)
        if app and app.is_process_running(): app.kill()
        return False

def export_jpeg_via_ui(indd_path, config):
    """
    Reuse the running InDesign session (from HTML export) to export JPEG.
    Destination: <final_flyers_output_folder>/<doc_stem>/JPEG
    Sets Image Quality = Low and Resolution = 300 ppi in the Export JPEG dialog.
    """
    import re
    project_root = Path().resolve()
    images_root = project_root / config.get('Paths', 'image_assets_folder')
    
    
    NO_BUTTON = str(images_root / config.get('ImageFiles', 'no_button'))
    
    # Build final/<doc_stem> (save JPEG next to index.html — NO subfolder)
    try:
        doc_stem = Path(indd_path).stem if not isinstance(indd_path, Path) else indd_path.stem
        doc_output_dir = Path(config.get('Paths', 'final_flyers_output_folder')) / doc_stem
        jpeg_output_dir = doc_output_dir  # keep downstream variable name to minimize edits
    except Exception as e:
        logging.error(f"FATAL: Could not build destination path from config.ini: {e}")
        return False
    
    inter_action_wait  = config.getint('Settings', 'inter_action_wait')
    process_wait       = config.getint('Settings', 'process_wait')

    # Ensure the doc folder exists; DO NOT delete anything (index.html lives here)
    try:
        jpeg_output_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"JPEG will be saved next to index.html in: {jpeg_output_dir}")
    except OSError as e:
        logging.error(f"FATAL: Could not ensure output folder '{jpeg_output_dir}'. Error: {e}")
        return False

    # Attach to existing InDesign
    try:
        app = Application(backend="win32").connect(title_re=".*InDesign.*")
    except Exception:
        logging.error("Could not attach to a running InDesign instance. Is HTML export keeping it open?", exc_info=True)
        return False

    doc_title_regex = f".*{re.escape(Path(indd_path).name)}.*"
    doc_win = None

    try:
        # Close Explorer window that HTML export may have opened
        try:
            Desktop(backend="win32").window(
                title_re=f"^{re.escape(doc_stem)}.*", class_name="CabinetWClass"
            ).wait('visible', timeout=5).close()
            time.sleep(0.5)
        except Exception:
            pass

        # Focus the document (fallback to app shell)
        try:
            doc_win = app.window(title_re=doc_title_regex).wait('visible', timeout=30)
        except Exception:
            doc_win = app.window(title_re=".*Adobe InDesign.*").wait('visible', timeout=30)

        doc_win.set_focus()
        time.sleep(0.2)

        # Open Export dialog
        doc_win.type_keys("^e")
        export_dlg = app.window(title="Export", class_name="#32770").wait('visible', timeout=15)
        export_dlg.set_focus()

        # Select JPEG format (same pattern as your HTML selection style)
        export_dlg.type_keys("{TAB}J")

        # Navigate to target path and paste it
        logging.info(f"Pasting JPEG destination path to clipboard: {jpeg_output_dir}")
        pyperclip.copy(str(jpeg_output_dir))
        export_dlg.type_keys("{TAB 7}{ENTER}")
        export_dlg.type_keys("^v{ENTER}")
        
        time.sleep(inter_action_wait)

        # Confirm Save
        export_dlg.type_keys("{TAB 10}{ENTER}")

        # Overwrite/warnings if any
        try:
            warn = app.window(title_re=".*(Warning|Replace|Confirm Save As).*")
            if warn.exists(timeout=5):
                warn.type_keys("{ENTER}")
        except Exception:
            pass
        
        time.sleep(inter_action_wait)
        
        # ---- Export JPEG / JPEG Options dialog: YOUR NAVIGATION ----
        resolution_value = 300  # ppi
        try:
            jpeg_opts = app.window(title_re=".*(Export JPEG).*").wait('visible', timeout=10)
            
            jpeg_opts.set_focus()
            
            time.sleep(0.2)

            # Copy resolution (clipboard must be string)
            pyperclip.copy(str(resolution_value))

            # Image Quality -> Low
            jpeg_opts.type_keys("{TAB 4}{DOWN 1}")

            # Resolution (ppi) -> paste 300
            # (often two tabs from Quality; keep your rhythm)
            jpeg_opts.type_keys("{TAB 2}^a^v")

            # Confirm export
            jpeg_opts.type_keys("{ENTER}")
        except Exception:
            logging.info("JPEG Options dialog not detected; proceeding with defaults.")

        # Allow files to land
        time.sleep(inter_action_wait)

        return True

    except Exception as e:
        logging.error(f"An error occurred during the JPEG export UI workflow: {e}", exc_info=True)
        # Best-effort: release lock on failure too
        try:
            if doc_win:
                doc_win.set_focus()
                doc_win.type_keys("^w")
        except Exception:
            pass
        return False

def run_resize_on_folder(target_folder_path, config):
    """
    Reuses the current InDesign session (document still open) and runs the resize script.
    Waits for the visual completion signal, verifies output, then CLOSES InDesign so
    downstream file moves are safe.
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
    
    inter_action_wait = config.getint('Settings', 'inter_action_wait')
    process_timeout = config.getint('Settings', 'process_timeout')
    
    logging.info(f"--- Starting Resize Process for folder: {target_folder_path} ---")
    
    source_script_path = scripts_folder / "resizeall.js" 
    dest_script_path = None
    app = None
    
    try:
        # This is your proven, working UI automation logic.
        appdata_path = Path(os.getenv('APPDATA'))
        dest_script_folder = appdata_path / "Adobe" / "InDesign" / indesign_version_folder / "en_US" / "Scripts" / "Scripts Panel"
        dest_script_folder.mkdir(parents=True, exist_ok=True)
        dest_script_path = dest_script_folder / source_script_path.name
        shutil.copy2(source_script_path, dest_script_path)
        
        try:
            app = Application(backend="win32").connect(path=indesign_executable)
        except Exception:
            # Fallback to first visible InDesign window handle if path-attach fails
            wins = Desktop(backend="win32").windows(title_re=".*InDesign.*")
            if not wins:
                logging.error("Could not attach to a running InDesign instance for resize.")
                return False
            app = Application(backend="win32").connect(handle=wins[0].handle)


        # Prefer the actual .indd name from the target folder; fall back to generic titles
        try:
            indd_file = next(Path(target_folder_path).glob("*.indd"))
            doc_title_regex = f".*{re.escape(indd_file.name)}.*"
        except StopIteration:
            doc_title_regex = None

        candidates = [doc_title_regex, r".*Adobe InDesign.*", r".*InDesign.*"]

        main_window = None
        for pat in [p for p in candidates if p]:
            try:
                win = app.window(title_re=pat)
                if win.exists(timeout=5):
                    try:
                        win.restore()   # if minimized
                    except Exception:
                        pass
                    win.set_focus()
                    main_window = win
                    break
            except Exception:
                continue

        if main_window is None:
            # Last resort: whatever InDesign's top window is right now
            main_window = app.top_window()
            try:
                main_window.restore()
            except Exception:
                pass
            main_window.set_focus()

        # Open Scripts panel
        main_window.type_keys("^%{F11}")
        time.sleep(inter_action_wait)
        
        time.sleep(inter_action_wait)


        # This now uses the new default.
        user_folder_found = find_and_click_image(USER_SCRIPTS_FOLDER, confidence=0.9, description="'User' folder")
        if user_folder_found:
            location = pyautogui.locateCenterOnScreen(USER_SCRIPTS_FOLDER, confidence=0.9)
            if location: pyautogui.doubleClick(location)
            time.sleep(2)
            # This now uses the new default.
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
            # NOTE: This call intentionally uses retries=1.
            # The while loop itself is the retry mechanism, polling every 5 seconds.
            # This prevents a single check from blocking for 25 seconds.
            if find_and_click_image(SIGNAL_OK_BUTTON, confidence=0.9, retries=1, description="completion signal OK button"):
                signal_found = True
                break
            time.sleep(5)

        if not signal_found:
            raise RuntimeError("Timeout waiting for the visual completion signal alert.")
        
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

