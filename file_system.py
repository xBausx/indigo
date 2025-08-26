# file_system.py
import logging, re
import shutil
import os
import time
from pathlib import Path


def sanitize_indd_filename(indd_path: Path) -> Path:
    """
    Fixes whitespace issues like 'NAME .indd' -> 'NAME.indd'.
    Trims leading/trailing whitespace and removes whitespace right before the extension.
    Returns the (possibly renamed) Path.
    """
    p = Path(indd_path)
    name = p.name

    # Remove whitespace immediately before extension and trim ends
    cleaned = re.sub(r"\s+(\.indd)$", r"\1", name, flags=re.IGNORECASE).strip()

    if cleaned == name:
        return p  # nothing to do

    # Ensure we don't collide with an existing file
    ext = p.suffix  # preserve original case of extension
    stem = Path(cleaned).stem
    candidate = p.with_name(cleaned)
    i = 1
    while candidate.exists():
        candidate = p.with_name(f"{stem}_{i}{ext}")
        i += 1

    try:
        p.rename(candidate)
        logging.info(f"Sanitized filename: '{name}' -> '{candidate.name}'")
        return candidate
    except Exception as e:
        logging.warning(f"Could not sanitize filename '{name}' -> '{candidate.name}': {e}. Proceeding with original.")
        return p

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
                        logging.warning(f"Could not delete cache folder {item}: {e}")
        else:
            logging.info(f"Cache path not found, skipping: {path}")

def cleanup_lock_files(input_folder_path):
    """Scans the input folder and deletes any lingering InDesign lock files (.idlk)."""
    logging.info("--- Starting final cleanup of InDesign lock files (.idlk) ---")
    try:
        lock_files = list(Path(input_folder_path).glob("*.idlk"))
        if not lock_files:
            logging.info("No InDesign lock files found to clean up.")
            return
        for lock_file in lock_files:
            lock_file.unlink()
            logging.info(f"Deleted lock file: {lock_file.name}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during lock file cleanup: {e}", exc_info=True)

def setup_processed_subfolder(indd_path, processed_root_path_str):
    """
    Creates a subfolder within the processed directory named after the InDesign file.
    Returns the Path object to the new subfolder.
    """
    indd_file = Path(indd_path)
    processed_root_path = Path(processed_root_path_str)
    new_folder = processed_root_path / indd_file.stem
    new_folder.mkdir(parents=True, exist_ok=True)
    return new_folder

def move_file_to_folder(source_path, dest_folder_path):
    """Moves a source file into a destination folder."""
    try:
        source = Path(source_path)
        dest_folder = Path(dest_folder_path)
        shutil.move(str(source), str(dest_folder / source.name))
        logging.info(f"Successfully moved '{source.name}' to '{dest_folder}'.")
    except Exception as e:
        logging.error(f"Could not move file '{source.name}': {e}", exc_info=True)

def verify_resize_output(indd_file_stem, config):
    """
    Verifies that the resize script produced the correct output artifacts in the
    final output destination defined in the config.
    Returns True if valid, False otherwise.
    """
    # This function now constructs the final output path itself by reading from config.
    # This ensures it is always looking in the correct, authoritative location.
    try:
        final_output_base_path = Path(config.get('Paths', 'final_flyers_output_folder'))
        output_subfolder_path = final_output_base_path / indd_file_stem
    except Exception as e:
        logging.error(f"Could not construct final output path from config.ini: {e}")
        return False

    logging.info(f"Verifying artifacts in FINAL output folder: '{output_subfolder_path}'...")
    
    folder_path = Path(output_subfolder_path)

    # Check 1: Does the main output folder itself exist?
    if not folder_path.is_dir():
        logging.error(f"Validation failed: Final output folder '{folder_path.name}' does not exist at '{folder_path}'.")
        return False

    # Check 2: Does it contain the 'publication-web-resources' subfolder?
    resources_subfolder = folder_path / "publication-web-resources"
    if not resources_subfolder.is_dir():
        logging.error(f"Validation failed: The 'publication-web-resources' subfolder is missing in '{folder_path}'.")
        return False

    # Check 3: Does the main folder contain at least one .html file?
    # The merged JSX script creates <docName>.html, so this check remains valid.
    if not any(folder_path.glob("*.html")):
        logging.error(f"Validation failed: No .html file was found in the main output folder '{folder_path}'.")
        return False
        
    logging.info("Artifact validation successful. All expected files and folders are present in the final destination.")
    return True

def recover_orphaned_files(temp_folder_path, input_folder_path):
    """
    Checks for any files stranded in the temp folder from a previous crash
    and moves them back to the input folder to be re-queued.
    """
    logging.info("--- Checking for orphaned files from previous runs... ---")
    temp_folder = Path(temp_folder_path)
    input_folder = Path(input_folder_path)
    
    if not temp_folder.exists():
        return # Nothing to do

    orphaned_files = list(temp_folder.glob("*.indd"))
    
    if not orphaned_files:
        logging.info("No orphaned files found. Startup is clean.")
        return
        
    logging.warning(f"Found {len(orphaned_files)} orphaned file(s) in the temp folder. Moving them back to Input for reprocessing.")
    
    for orphan in orphaned_files:
        try:
            shutil.move(str(orphan), str(input_folder / orphan.name))
        except Exception as e:
            logging.error(f"Could not recover orphaned file '{orphan.name}': {e}")

def cleanup_empty_temp_folder(temp_folder_path):
    """
    Deletes the temporary processing folder, but only if it is completely empty.
    This is a safe cleanup routine to run on startup after recovery.
    """
    temp_folder = Path(temp_folder_path)
    
    # Check if the folder exists and is a directory
    if temp_folder.is_dir():
        # Check if the folder is empty. any(temp_folder.iterdir()) is an efficient way to do this.
        if not any(temp_folder.iterdir()):
            logging.info("Temporary processing folder is empty. Deleting it for a clean slate.")
            try:
                temp_folder.rmdir() # rmdir only works on empty directories, which is a safety feature.
            except OSError as e:
                logging.warning(f"Could not delete empty temp folder: {e}")
        else:
            # This is an important warning. It means recovery ran but something was left behind.
            logging.warning("Temporary processing folder is NOT empty after recovery. Manual inspection may be required.")
            
def cleanup_intermediate_folder(indd_file_stem, request_id, config):
    """
    Deletes the intermediate output folder created during the initial HTML export.
    This is a cleanup step to run after the final output is verified.
    """
    logging.info(f"[ReqID: {request_id}] Starting cleanup of intermediate output folder...")
    try:
        project_root = Path().resolve()
        # The 'output_folder' from config points to the intermediate directory (e.g., '2_Output_HTML')
        intermediate_output_root = project_root / config.get('Paths', 'output_folder')
        folder_to_delete = intermediate_output_root / indd_file_stem

        if folder_to_delete.is_dir():
            logging.info(f"[ReqID: {request_id}] Deleting temporary folder: {folder_to_delete}")
            shutil.rmtree(folder_to_delete)
            logging.info(f"[ReqID: {request_id}] Successfully cleaned up intermediate folder.")
        else:
            logging.info(f"[ReqID: {request_id}] Intermediate folder not found, skipping cleanup: {folder_to_delete}")

    except Exception as e:
        # We log this as a warning because the primary job succeeded.
        # Cleanup failure should not cause the entire process to be marked as an error.
        logging.warning(f"[ReqID: {request_id}] An error occurred during intermediate folder cleanup: {e}", exc_info=True)

def copy_then_delete_indesign(source_path, dest_folder_path, request_id,
                              verify_copy=True, max_tries=10, delay_seconds=1.0, backoff=1.5):
    """
    Copies the source .indd to dest folder. Then tries to delete the source with retries.
    If the source is locked, we keep retrying a few times; if still locked, we leave it in place.
    Returns True if copy succeeded (delete may be deferred).
    """
    from pathlib import Path
    import shutil, time, logging

    try:
        source = Path(source_path)
        dest_folder = Path(dest_folder_path)
        dest_folder.mkdir(parents=True, exist_ok=True)  # parents=True is important on fresh trees
        dest = dest_folder / source.name

        shutil.copy2(str(source), str(dest))
        logging.info(f"[ReqID: {request_id}] Copied '{source.name}' -> '{dest_folder}'.")

        if verify_copy:
            try:
                src_size = source.stat().st_size
                dst_size = dest.stat().st_size
                if src_size != dst_size:
                    logging.warning(f"[ReqID: {request_id}] Copy size mismatch (src={src_size}, dst={dst_size}).")
            except Exception as e:
                logging.warning(f"[ReqID: {request_id}] Could not verify copy sizes: {e}")

        # Delete with retries (handles lingering file locks)
        sleep_for = float(delay_seconds)
        for attempt in range(1, max_tries + 1):
            try:
                source.unlink()
                logging.info(f"[ReqID: {request_id}] Deleted original: {source}")
                break
            except PermissionError as e:
                if attempt == max_tries:
                    logging.error(f"[ReqID: {request_id}] Still locked after {max_tries} attempts; "
                                f"leaving original in place: {source} ({e})")
                else:
                    logging.warning(f"[ReqID: {request_id}] Delete locked (attempt {attempt}/{max_tries}) for "
                                    f"'{source.name}'; retrying in {sleep_for:.1f}s")
                    time.sleep(sleep_for)
                    sleep_for *= backoff
            except Exception as e:
                logging.warning(f"[ReqID: {request_id}] Could not delete source now: {e}")
                break

        return True

    except Exception as e:
        logging.error(f"[ReqID: {request_id}] Failed to copy '{source_path}' to '{dest_folder_path}': {e}", exc_info=True)
        return False


def ensure_deleted_after_close(path, request_id, retries=10, delay_seconds=1.0):
    """
    After InDesign is closed, try repeatedly to delete the original file.
    Returns True if deleted or not present, False if still present after retries.
    """
    p = Path(path)
    if not p.exists():
        return True

    for i in range(retries):
        try:
            p.unlink()
            logging.info(f"[ReqID: {request_id}] Deleted original after close: {p}")
            return True
        except PermissionError:
            time.sleep(delay_seconds)
        except Exception as e:
            logging.warning(f"[ReqID: {request_id}] Delete retry {i+1}/{retries} failed: {e}")
            time.sleep(delay_seconds)

    if p.exists():
        logging.warning(f"[ReqID: {request_id}] Original still present after retries: {p}")
        return False
    return True


def read_page_count(indd_file_stem, config):
    """
    Returns the page count (int) from <final>/<stem>/__pagecount.txt, or None if missing/invalid.
    """
    try:
        base = Path(config.get('Paths', 'final_flyers_output_folder'))
        f = base / indd_file_stem / "__pagecount.txt"
        if not f.is_file():
            logging.warning(f"Page count file not found: {f}")
            return None
        txt = f.read_text(encoding="utf-8").strip()
        if txt.isdigit():
            return int(txt)
        logging.warning(f"Unexpected content in page count file '{f}': '{txt}'")
        return None
    except Exception as e:
        logging.error(f"Failed reading page count for '{indd_file_stem}': {e}", exc_info=True)
        return None
