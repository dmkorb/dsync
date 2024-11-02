import subprocess
import logging


def get_mount_point(uuid):
    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", uuid], capture_output=True, text=True
        )
        if result.returncode == 0:
            import plistlib

            plist = plistlib.loads(result.stdout.encode("utf-8"))
            return plist.get("MountPoint")
    except Exception as e:
        logging.error(f"Error getting mount point: {e}")
    return None


def is_ssd_connected(uuid):
    return get_mount_point(uuid) is not None
