"""Offline NTFS recovery regressions: never modify dirty filesystems."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch
import unittest


HELPER = Path(__file__).resolve().parents[1] / "atualizador/callas-automount.py"
spec = importlib.util.spec_from_file_location("callas_automount_rescue", HELPER)
automount = importlib.util.module_from_spec(spec)
spec.loader.exec_module(automount)

ENTRY = {
    "source": "/dev/sda1", "target": "/mnt/hd-500", "fstype": "ntfs3",
    "options": "nosuid,nodev,uid=1000,gid=1000,umask=0077,nofail",
}


def result(code=0, out="", err=""):
    return SimpleNamespace(returncode=code, stdout=out, stderr=err)


class ReadOnlyNTFSRescueTests(unittest.TestCase):
    def run_case(self, *, dirty=True, existing=False, filesystem="ntfs"):
        seen = []

        def command(args, *more, **kwargs):
            seen.append(args)
            if args[0] == "journalctl":
                log = "ntfs3(sda1): volume is dirty and force flag is not set" if dirty else ""
                return result(out=log)
            if args[0] == "blkid":
                return result(out=filesystem + "\n")
            if args[0] == "findmnt":
                return result(0 if existing else 1, "ro,nosuid,nodev\n" if existing else "")
            if args[0] == "/usr/bin/timeout":
                return result()
            raise AssertionError("Unexpected command: " + str(args))

        with (patch.object(automount.os, "geteuid", return_value=0),
              patch.object(automount, "inventory", return_value={"filesystems": [dict(ENTRY)]}),
              patch.object(automount, "available_target", return_value=True),
              patch.object(automount.Path, "is_block_device", return_value=True),
              patch.object(automount.Path, "is_file", return_value=True),
              patch.object(automount.subprocess, "run", side_effect=command)):
            automount.rescue_dirty_ntfs()
        return seen

    def test_dirty_ntfs_only_uses_readonly_fuse_driver(self):
        # Emulate the post-mount verification on a read-only FUSE mount.
        calls = []

        def run(args, *more, **kwargs):
            calls.append(args)
            if args[0] == "journalctl":
                return result(out="ntfs3(sda1): volume is dirty and force flag is not set")
            if args[0] == "blkid":
                return result(out="ntfs\n")
            if args[0] == "findmnt":
                n = sum(item[0] == "findmnt" for item in calls)
                return result(1 if n == 1 else 0, "" if n == 1 else "ro,nosuid,nodev\n")
            if args[0] == "/usr/bin/timeout":
                return result()
            raise AssertionError(args)

        with (patch.object(automount.os, "geteuid", return_value=0),
              patch.object(automount, "inventory", return_value={"filesystems": [dict(ENTRY)]}),
              patch.object(automount, "available_target", return_value=True),
              patch.object(automount.Path, "is_block_device", return_value=True),
              patch.object(automount.Path, "is_file", return_value=True),
              patch.object(automount.subprocess, "run", side_effect=run)):
            automount.rescue_dirty_ntfs()
        attempts = [args for args in calls if args[0] == "/usr/bin/timeout"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0][2:5], ["/usr/bin/ntfs-3g", "-o",
                                             "ro,nosuid,nodev,noexec,umask=0077,uid=1000,gid=1000"])
        self.assertEqual(attempts[0][-2:], ["/dev/sda1", "/mnt/hd-500"])
        self.assertNotIn("force", " ".join(attempts[0]))
        self.assertNotIn("ntfsfix", " ".join(str(c) for c in calls))
        self.assertNotIn("fsck", " ".join(str(c) for c in calls))

    def test_clean_log_does_not_trigger_rescue(self):
        calls = self.run_case(dirty=False)
        self.assertFalse(any(args[0] == "/usr/bin/timeout" for args in calls))

    def test_non_ntfs_signature_does_not_trigger_rescue(self):
        calls = self.run_case(filesystem="ext4")
        self.assertFalse(any(args[0] == "/usr/bin/timeout" for args in calls))

    def test_mounted_target_is_not_touched(self):
        calls = self.run_case(existing=True)
        self.assertFalse(any(args[0] == "/usr/bin/timeout" for args in calls))

    def test_requires_root(self):
        with patch.object(automount.os, "geteuid", return_value=1000):
            with self.assertRaises(ValueError):
                automount.rescue_dirty_ntfs()


if __name__ == "__main__":
    unittest.main()
