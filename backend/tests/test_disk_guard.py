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


def _seed(clone_cache, prior_cache, key, clone_bytes, mtime):
    """Create a clone dir + matching prior file for `key`, with a set mtime."""
    repo = clone_cache / key
    (repo / ".git").mkdir(parents=True)
    (repo / "payload.bin").write_bytes(b"z" * clone_bytes)

    prior = prior_cache / f"{key}.json"
    prior.write_text('{"sha": "abc", "files": []}')
    os.utime(prior, (mtime, mtime))
    return repo, prior


@pytest.fixture()
def caches(tmp_path):
    clone_cache = tmp_path / "clones"
    prior_cache = tmp_path / "priors"
    clone_cache.mkdir()
    prior_cache.mkdir()
    return clone_cache, prior_cache


# Deliberately 1,000,000 and not 1 MiB. Each seeded entry also carries a
# 27-byte prior JSON, so three entries of exactly 1 MiB overshoot a 2 MiB cap
# by less than the per-entry overhead — leaving no arrangement where exactly
# one repo can be evicted. A round-decimal payload keeps the caps meaningful:
# ~903 KB of trigger margin and ~97 KB of headroom under the survivors.
CHUNK_BYTES = 1_000_000


def test_under_cap_evicts_nothing(caches):
    clone_cache, prior_cache = caches
    _seed(clone_cache, prior_cache, "aaa", 1000, mtime=1000)

    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=1
    )

    assert evicted == []
    assert (clone_cache / "aaa").exists()


def test_evicts_least_recently_scanned_first(caches):
    clone_cache, prior_cache = caches
    _seed(clone_cache, prior_cache, "old", CHUNK_BYTES, mtime=1000)
    _seed(clone_cache, prior_cache, "mid", CHUNK_BYTES, mtime=2000)
    _seed(clone_cache, prior_cache, "new", CHUNK_BYTES, mtime=3000)

    # Cap of 2 MB against ~3 MB held: exactly one repo must go, the oldest.
    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=2
    )

    assert evicted == ["old"]
    assert not (clone_cache / "old").exists()
    assert (clone_cache / "mid").exists()
    assert (clone_cache / "new").exists()


def test_eviction_removes_clone_and_prior_together(caches):
    clone_cache, prior_cache = caches
    _seed(clone_cache, prior_cache, "old", CHUNK_BYTES, mtime=1000)
    _seed(clone_cache, prior_cache, "new", CHUNK_BYTES, mtime=3000)

    disk_guard.evict_caches(str(clone_cache), str(prior_cache), max_mb=1)

    # An orphaned prior would make a later scan diff against a clone that is
    # gone; the pair must disappear atomically.
    assert not (clone_cache / "old").exists()
    assert not (prior_cache / "old.json").exists()


def test_keep_protects_the_repo_about_to_be_scanned(caches):
    clone_cache, prior_cache = caches
    _seed(clone_cache, prior_cache, "old", CHUNK_BYTES, mtime=1000)
    _seed(clone_cache, prior_cache, "new", CHUNK_BYTES, mtime=3000)

    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=1, keep="old"
    )

    # "old" is the LRU but is the scan target, so "new" goes instead.
    assert evicted == ["new"]
    assert (clone_cache / "old").exists()


def test_clone_without_a_prior_is_still_evictable(caches):
    """A scan that crashed before save_prior leaves a clone with no prior."""
    clone_cache, prior_cache = caches
    orphan = clone_cache / "orphan"
    (orphan / ".git").mkdir(parents=True)
    (orphan / "payload.bin").write_bytes(b"z" * (2 * 1024 * 1024))

    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=1
    )

    assert evicted == ["orphan"]
    assert not orphan.exists()


def test_missing_cache_directories_are_not_an_error(tmp_path):
    assert disk_guard.evict_caches(
        str(tmp_path / "nope"), str(tmp_path / "also-nope")
    ) == []


def test_max_cache_mb_reads_env_at_call_time(monkeypatch):
    monkeypatch.setenv("MAX_CACHE_MB", "77")
    assert disk_guard.max_cache_mb() == 77
    monkeypatch.delenv("MAX_CACHE_MB")
    assert disk_guard.max_cache_mb() == disk_guard.DEFAULT_MAX_CACHE_MB
