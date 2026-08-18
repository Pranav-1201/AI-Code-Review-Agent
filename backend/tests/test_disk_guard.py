"""
Disk-bounding guards (Phase E — ops hardening).

Two failure modes are under test here, both of which the service was open to
before this module existed: caches that grow until the volume is full, and a
single hostile or huge repository that exhausts the disk mid-clone. The 300s
clone timeout was never a size limit — a fast link moves many gigabytes well
inside it.
"""

import os
import stat
import subprocess
import sys
import textwrap

import pytest

from backend.app import disk_guard


def test_force_rmtree_removes_read_only_files(tmp_path):
    """git marks pack indexes read-only; plain rmtree raises WinError 5."""
    victim = tmp_path / "repo"
    victim.mkdir()
    locked = victim / "packed.idx"
    locked.write_text("data")
    os.chmod(locked, stat.S_IREAD)

    disk_guard.force_rmtree(victim)

    assert not victim.exists()


def test_dir_size_bytes_sums_nested_files(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 100)
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "b").write_bytes(b"y" * 250)

    assert disk_guard.dir_size_bytes(tmp_path) == 350


def test_dir_size_bytes_missing_path_is_zero(tmp_path):
    assert disk_guard.dir_size_bytes(tmp_path / "nope") == 0
