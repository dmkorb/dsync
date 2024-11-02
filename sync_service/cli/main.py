import os
import time
import argparse
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from tqdm import tqdm
from watchdog.observers import Observer

from ..core.handler import SyncHandler
from ..config.config_loader import load_config
from ..storage.disk_utils import get_mount_point, is_ssd_connected

# Set up logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sync.log"),
        logging.StreamHandler()
    ]
)

def perform_initial_sync(source_dir, destination_dir, exclude_patterns=None, config=None, dry_run=False):
    logging.info(f"Starting initial sync from {source_dir} to {destination_dir}")
    handler = SyncHandler(source_dir, destination_dir, exclude_patterns, config, dry_run)
    
    if not os.path.exists(destination_dir):
        if not dry_run:
            os.makedirs(destination_dir, exist_ok=True)
        logging.info(f"Created destination directory: {destination_dir}")

    # First pass: Collect all files and their metadata
    files_to_sync = []
    source_files = set()
    
    with tqdm(desc="Scanning files", unit="files") as scan_pbar:
        for root, dirs, files in os.walk(source_dir):
            if config.get('skip_hidden', True):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                src_file = os.path.join(root, file)
                if not handler.should_exclude(src_file):
                    files_to_sync.append(src_file)
                    source_files.add(os.path.relpath(src_file, source_dir))
                    scan_pbar.update(1)

    # Define a worker function for parallel processing
    def sync_worker(src_file):
        try:
            handler.sync_file(src_file)
            return True
        except Exception as e:
            logging.error(f"Error syncing {src_file}: {e}")
            return False

    # Use ThreadPoolExecutor for I/O-bound operations
    max_workers = min(32, (multiprocessing.cpu_count() * 2))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        with tqdm(total=len(files_to_sync), desc="Initial sync", unit="files") as pbar:
            # Submit all tasks
            future_to_file = {
                executor.submit(sync_worker, src_file): src_file 
                for src_file in files_to_sync
            }
            
            # Process completed tasks
            for future in as_completed(future_to_file):
                src_file = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error processing {src_file}: {e}")
                pbar.update(1)

    # Optimize destination file checking
    dest_files_to_check = []
    with tqdm(desc="Scanning destination", unit="files") as scan_pbar:
        for root, dirs, files in os.walk(destination_dir):
            for file in files:
                dest_file = os.path.join(root, file)
                if not handler.should_exclude(dest_file):
                    rel_path = os.path.relpath(dest_file, destination_dir)
                    if rel_path not in source_files:
                        dest_files_to_check.append((dest_file, rel_path))
                    scan_pbar.update(1)

    if dest_files_to_check:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            with tqdm(total=len(dest_files_to_check), desc="Cleaning destination", unit="files") as pbar:
                def delete_worker(file_info):
                    dest_file, rel_path = file_info
                    src_path = os.path.join(source_dir, rel_path)
                    handler.handle_delete(src_path)
                    return True

                # Submit all delete tasks
                future_to_file = {
                    executor.submit(delete_worker, file_info): file_info[0]
                    for file_info in dest_files_to_check
                }
                
                # Process completed tasks
                for future in as_completed(future_to_file):
                    pbar.update(1)

    logging.info("Initial sync completed")


def main():
    parser = argparse.ArgumentParser(description="Sync files to specific SSDs")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Perform a dry run without actual file operations")
    parser.add_argument("--config", default="sync_config.yaml",
                       help="Path to config file (default: sync_config.yaml)")
    args = parser.parse_args()

    config = load_config(args.config)
    settings = config.get('settings', {})

    
    logging.info(f"{'Dry run mode' if args.dry_run else 'Normal mode'}")

    observers = []
    try:
        while True:
            for ssd_uuid, ssd_config in config['ssd_configs'].items():
                mount_point = get_mount_point(ssd_uuid)
                if mount_point:
                    logging.info(f"SSD with UUID '{ssd_uuid}' connected at {mount_point}")
                    
                    for sync_pair in ssd_config['sync_pairs']:
                        source_dir = os.path.expanduser(sync_pair['source'])
                        destination_dir = os.path.join(mount_point, sync_pair['destination'])
                        exclude_patterns = sync_pair.get('exclude', [])
                        
                        # Create a copy of settings and update it with sync pair specific settings
                        sync_pair_settings = settings.copy()
                        sync_pair_settings['sync_pair_config'] = sync_pair
                        
                        # Perform initial sync with updated settings
                        perform_initial_sync(
                            source_dir, 
                            destination_dir, 
                            exclude_patterns=exclude_patterns,
                            config=sync_pair_settings,
                            dry_run=args.dry_run
                        )

                        # Set up continuous monitoring with updated settings
                        event_handler = SyncHandler(
                            source_dir, 
                            destination_dir, 
                            exclude_patterns=exclude_patterns,
                            config=sync_pair_settings,
                            dry_run=args.dry_run
                        )
                        logging.info(f"Watching {source_dir} for changes")
                        observer = Observer()
                        observer.schedule(event_handler, source_dir, recursive=True)
                        logging.info(f"Observer scheduled for {source_dir}")
                        observer.start()
                        observers.append((observer, ssd_uuid))
                        logging.info(f"Observer started for {source_dir}")
                        
                        logging.info(f"Watching {source_dir} for changes")

            if not observers:
                logging.info("Waiting for configured SSDs to be connected...")
                time.sleep(5)
            else:
                try:
                    while any(is_ssd_connected(uuid) for _, uuid in observers):
                        time.sleep(1)
                except KeyboardInterrupt:
                    raise
                finally:
                    for observer, _ in observers:
                        observer.stop()
                        observer.join()
                    observers.clear()
                logging.info("All SSDs disconnected or sync stopped")

    except Exception as e:
        logging.error(f"Error in main loop: {e}")

    except KeyboardInterrupt:
        logging.info("\nSync interrupted by user. Cleaning up...")
    finally:
        for observer, _ in observers:
            observer.stop()
            observer.join()
        logging.info("Sync stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
