import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
import fnmatch
from watchdog.events import FileSystemEventHandler
from ..core.utils import calculate_file_hash, log_sync_action

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
        # First update with global conflict resolution settings
        self.conflict_settings.update(self.config.get('conflict_resolution', {}))
        # Then update with sync pair specific conflict resolution settings if they exist
        self.conflict_settings.update(self.config.get('sync_pair_config', {}).get('conflict_resolution', {}))

    def on_created(self, event):
        if event.is_directory or self.is_syncing:
            return
        self.sync_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory or self.is_syncing:
            return
        self.sync_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory or self.is_syncing:
            return
        # Handle the deletion of the old file
        self.handle_delete(event.src_path)
        # Handle the creation of the new file if it's still in the watched directory
        if event.dest_path.startswith(self.source_dir):
            self.sync_file(event.dest_path)

    def on_deleted(self, event):
        if event.is_directory or self.is_syncing:
            return
        self.handle_delete(event.src_path)

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
        logging.info(f"Trash location: {os.path.join(trash_dir, trash_name)}")
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

    def cleanup_empty_dirs(self, directory):
        """
        Recursively remove empty directories starting from the given directory.
        """
        if not os.path.exists(directory):
            return

        # Don't delete the root destination directory
        if directory == self.destination_dir:
            return

        try:
            # Check if directory is empty
            if not os.listdir(directory):
                os.rmdir(directory)
                logging.info(f"Removed empty directory: {os.path.relpath(directory, self.destination_dir)}")
                # Recursively check parent directory
                self.cleanup_empty_dirs(os.path.dirname(directory))
        except OSError:
            # Handle any permissions or other OS errors
            pass

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
                        log_sync_action("Would create new version", src_path, new_dest_path)
                    else:
                        os.makedirs(os.path.dirname(new_dest_path), exist_ok=True)
                        shutil.copy2(src_path, new_dest_path)
                        log_sync_action("Created new version", src_path, new_dest_path)
                elif self.conflict_settings['modified_files'] == 'keep_newest':
                    if os.path.getmtime(src_path) > os.path.getmtime(dest_path):
                        if not self.dry_run:
                            shutil.copy2(src_path, dest_path)
                            log_sync_action("Updated (newer)", src_path, dest_path)
                else:  # 'overwrite'
                    if not self.dry_run:
                        shutil.copy2(src_path, dest_path)
                        log_sync_action("Updated", src_path, dest_path)
                    else:
                        log_sync_action("Would sync", src_path, dest_path)
            else:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                    log_sync_action("Synced", src_path, dest_path)
        finally:
            self.is_syncing = False

    def handle_delete(self, src_path):
        try:
            self.is_syncing = True
            rel_path = os.path.relpath(src_path, self.source_dir)
            dest_path = os.path.join(self.destination_dir, rel_path)

            if not os.path.exists(dest_path):
                return

            if self.dry_run:
                log_sync_action("Would handle deletion", src_path, dest_path)
                return

            if self.conflict_settings['deleted_files'] == 'trash':
                # Move to trash
                trash_path = self.get_trash_path(os.path.basename(dest_path))
                os.makedirs(os.path.dirname(trash_path), exist_ok=True)
                shutil.move(dest_path, trash_path)
                log_sync_action("Moved to trash", dest_path, trash_path)
            elif self.conflict_settings['deleted_files'] == 'delete':
                # Delete permanently
                os.remove(dest_path)
                log_sync_action("Deleted", dest_path, details="permanent deletion")
            # If 'keep', do nothing

            # Clean up empty directories if configured
            if self.config.get('cleanup_empty_dirs', True):
                    self.cleanup_empty_dirs(os.path.dirname(dest_path))
        finally:
            self.is_syncing = False
