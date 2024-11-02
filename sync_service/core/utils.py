import os
import hashlib
import logging


def calculate_file_hash(filepath):
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        buf = f.read(65536)  # Read in 64kb chunks
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()


def log_sync_action(action, src_path, dest_path=None, details=None):
    """Helper function to consistently log sync actions with full paths"""
    msg = f"{action}: {os.path.abspath(src_path)}"
    if dest_path:
        msg += f" -> {os.path.abspath(dest_path)}"
    if details:
        msg += f" ({details})"
    logging.info(msg)


def log_conflict_resolution(resolution, src_path, dest_path, action_taken):
    """Helper function to log conflict resolutions"""
    msg = (
        f"Conflict detected between:\n"
        f"  Source:      {os.path.abspath(src_path)}\n"
        f"  Destination: {os.path.abspath(dest_path)}\n"
        f"Resolution '{resolution}' applied: {action_taken}"
    )
    logging.info(msg)
