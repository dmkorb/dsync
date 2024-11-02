import os
import shutil
import time
import subprocess
import argparse
import sys
import hashlib
import logging
from datetime import datetime
from pathlib import Path
import yaml
import fnmatch
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Set up logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sync.log"),
        logging.StreamHandler()
    ]
)

def calculate_file_hash(filepath):
    """
    Calculate MD5 hash of a file.
    """
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)  # Read in 64kb chunks
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

class SyncHandler(FileSystemEventHandler):
    def __init__(self, source_dir, destination_dir, exclude_patterns=None, config=None, dry_run=False):
        self.source_dir = os.path.abspath(source_dir)
        self.destination_dir = os.path.abspath(destination_dir)
        self.exclude_patterns = exclude_patterns or []
        self.config = config or {}
        self.dry_run = dry_run
        self.is_syncing = False
        
        # Get conflict resolution settings with defaults
        self.conflict_settings = {
            'deleted_files': 'trash',
            'modified_files': 'keep_both',
            'trash_dir': '.trash',
            'duplicate_format': '{original_name}_{timestamp}{ext}'
        }
        self.conflict_settings.update(self.config.get('conflict_resolution', {}))

    def should_exclude(self, path):
        """
        Check if a file should be excluded based on patterns and settings.
        """
        relative_path = os.path.relpath(path, self.source_dir)
        
        # Check if should skip hidden files
        if self.config.get('skip_hidden', True) and any(part.startswith('.') for part in Path(relative_path).parts):
            return True

        # Check exclude patterns
        return any(fnmatch.fnmatch(relative_path, pattern) for pattern in self.exclude_patterns)

    def files_are_identical(self, file1, file2):
        """
        Compare two files using their hashes.
        """
        try:
            return calculate_file_hash(file1) == calculate_file_hash(file2)
        except OSError:
            return False


    def get_trash_path(self, filename):
        trash_dir = os.path.join(self.destination_dir, self.conflict_settings['trash_dir'])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name, ext = os.path.splitext(filename)
        trash_name = f"{base_name}_{timestamp}{ext}"
        return os.path.join(trash_dir, trash_name)

    def get_duplicate_path(self, dest_path):
        base_path, ext = os.path.splitext(dest_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_name = os.path.basename(base_path)
        
        # Use the configured duplicate format
        new_name = self.conflict_settings['duplicate_format'].format(
            original_name=original_name,
            timestamp=timestamp,
            ext=ext
        )
        return os.path.join(os.path.dirname(dest_path), new_name)

    def handle_delete(self, src_path):
        try:
            self.is_syncing = True
            rel_path = os.path.relpath(src_path, self.source_dir)
            dest_path = os.path.join(self.destination_dir, rel_path)

            if not os.path.exists(dest_path):
                return

            if self.dry_run:
                logging.info(f"Would handle deletion of: {rel_path}")
                return

            if self.conflict_settings['deleted_files'] == 'trash':
                # Move to trash
                trash_path = self.get_trash_path(os.path.basename(dest_path))
                os.makedirs(os.path.dirname(trash_path), exist_ok=True)
                shutil.move(dest_path, trash_path)
                logging.info(f"Moved to trash: {rel_path}")
            elif self.conflict_settings['deleted_files'] == 'delete':
                # Delete permanently
                os.remove(dest_path)
                logging.info(f"Deleted: {rel_path}")
            # If 'keep', do nothing

            # Clean up empty directories if configured
            if self.config.get('cleanup_empty_dirs', True):
                self.cleanup_empty_dirs(os.path.dirname(dest_path))
        finally:
            self.is_syncing = False

    def sync_file(self, src_path):
        try:
            self.is_syncing = True
            rel_path = os.path.relpath(src_path, self.source_dir)
            dest_path = os.path.join(self.destination_dir, rel_path)

            # Skip excluded files
            if self.should_exclude(src_path):
                return

            if os.path.exists(dest_path):
                if self.files_are_identical(src_path, dest_path):
                    return

                if self.conflict_settings['modified_files'] == 'keep_both':
                    # Create a new copy with timestamp
                    new_dest_path = self.get_duplicate_path(dest_path)
                    if self.dry_run:
                        logging.info(f"Would create new version: {os.path.basename(new_dest_path)}")
                    else:
                        os.makedirs(os.path.dirname(new_dest_path), exist_ok=True)
                        shutil.copy2(src_path, new_dest_path)
                        logging.info(f"Created new version: {os.path.relpath(new_dest_path, self.destination_dir)}")
                elif self.conflict_settings['modified_files'] == 'keep_newest':
                    if os.path.getmtime(src_path) > os.path.getmtime(dest_path):
                        if not self.dry_run:
                            shutil.copy2(src_path, dest_path)
                            logging.info(f"Updated (newer): {rel_path}")
                else:  # 'overwrite'
                    if not self.dry_run:
                        shutil.copy2(src_path, dest_path)
                        logging.info(f"Updated: {rel_path}")
            else:
                if self.dry_run:
                    logging.info(f"Would sync: {rel_path}")
                else:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                    logging.info(f"Synced: {rel_path}")
        finally:
            self.is_syncing = False

def load_config(config_path):
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Set up logging level from config
        log_level = config.get('settings', {}).get('log_level', 'INFO')
        logging.getLogger().setLevel(getattr(logging, log_level))
            
        return config
    except Exception as e:
        logging.error(f"Error loading config file {config_path}: {e}")
        sys.exit(1)

def perform_initial_sync(source_dir, destination_dir, exclude_patterns=None, config=None, dry_run=False):
    logging.info(f"Starting initial sync from {source_dir} to {destination_dir}")
    handler = SyncHandler(source_dir, destination_dir, exclude_patterns, config, dry_run)
    
    if not os.path.exists(destination_dir):
        if not dry_run:
            os.makedirs(destination_dir, exist_ok=True)
        logging.info(f"Created destination directory: {destination_dir}")

    # Sync files from source to destination
    source_files = set()
    for root, dirs, files in os.walk(source_dir):
        if config.get('skip_hidden', True):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            src_file = os.path.join(root, file)
            if handler.should_exclude(src_file):
                continue
            handler.sync_file(src_file)
            source_files.add(os.path.relpath(src_file, source_dir))

    # Handle files that exist in destination but not in source
    for root, dirs, files in os.walk(destination_dir):
        for file in files:
            dest_file = os.path.join(root, file)
            rel_path = os.path.relpath(dest_file, destination_dir)
            
            if handler.should_exclude(dest_file):
                continue
                
            if rel_path not in source_files:
                src_path = os.path.join(source_dir, rel_path)
                handler.handle_delete(src_path)

    logging.info("Initial sync completed")


def get_mount_point(uuid):
    try:
        result = subprocess.run(['diskutil', 'info', '-plist', uuid], capture_output=True, text=True)
        if result.returncode == 0:
            import plistlib
            plist = plistlib.loads(result.stdout.encode('utf-8'))
            return plist.get('MountPoint')
    except Exception as e:
        logging.error(f"Error getting mount point: {e}")
    return None

def is_ssd_connected(uuid):
    return get_mount_point(uuid) is not None

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
                        
                        # Perform initial sync
                        perform_initial_sync(
                            source_dir, 
                            destination_dir, 
                            exclude_patterns=exclude_patterns,
                            config=settings,
                            dry_run=args.dry_run
                        )

                        # Set up continuous monitoring
                        event_handler = SyncHandler(
                            source_dir, 
                            destination_dir, 
                            exclude_patterns=exclude_patterns,
                            config=settings,
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