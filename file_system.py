# file_system.py
import logging
import shutil
import os
from pathlib import Path

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
    new_folder.mkdir(exist_ok=True)
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

def verify_resize_output(output_subfolder_path):
    """
    Verifies that the resize script produced the correct output artifacts.
    Returns True if valid, False otherwise.
    """
    logging.info(f"Verifying artifacts in output folder: '{output_subfolder_path}'...")
    
    # Convert to a Path object for easier handling
    folder_path = Path(output_subfolder_path)

    # Check 1: Does the main output folder itself exist?
    if not folder_path.is_dir():
        logging.error(f"Validation failed: Output folder '{folder_path.name}' does not exist.")
        return False

    # Check 2: Does it contain the 'publication-web-resources' subfolder?
    resources_subfolder = folder_path / "publication-web-resources"
    if not resources_subfolder.is_dir():
        logging.error(f"Validation failed: The 'publication-web-resources' subfolder is missing.")
        return False

    # Check 3: Does the main folder contain at least one .html file?
    # We use a generator expression for efficiency - it stops as soon as one is found.
    if not any(folder_path.glob("*.html")):
        logging.error(f"Validation failed: No .html file was found in the main output folder.")
        return False
        
    logging.info("Artifact validation successful. All expected files and folders are present.")
    return True
