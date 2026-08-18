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


def _growing_clone_command(dest, total_mb, chunk_mb=1, delay=0.05):
    """A fake `git clone`: creates dest and grows a file inside it.

    Used instead of a real clone so the watchdog is tested against observable
    growth without a network dependency in the suite.
    """
    script = textwrap.dedent(
        f"""
        import os, time
        os.makedirs({str(dest)!r}, exist_ok=True)
        with open(os.path.join({str(dest)!r}, "big.bin"), "wb") as fh:
            for _ in range({total_mb} // {chunk_mb}):
                fh.write(b"x" * ({chunk_mb} * 1024 * 1024))
                fh.flush()
                os.fsync(fh.fileno())
                time.sleep({delay})
        """
    )
    return [sys.executable, "-c", script]


def test_watchdog_kills_a_clone_that_exceeds_the_cap(tmp_path):
    dest = tmp_path / "huge"

    with pytest.raises(disk_guard.RepoTooLargeError) as excinfo:
        disk_guard.clone_with_limit(
            "https://example.invalid/huge.git",
            str(dest),
            max_mb=2,
            poll_seconds=0.05,
            command=_growing_clone_command(dest, total_mb=40),
        )

    assert excinfo.value.limit_mb == 2
    # The partial clone must not be left behind eating disk.
    assert not dest.exists()


def test_a_small_clone_completes_untouched(tmp_path):
    """The guard must not be passing by killing everything."""
    dest = tmp_path / "small"

    disk_guard.clone_with_limit(
        "https://example.invalid/small.git",
        str(dest),
        max_mb=64,
        poll_seconds=0.05,
        command=_growing_clone_command(dest, total_mb=2),
    )

    assert dest.exists()
    assert (dest / "big.bin").exists()


def test_a_failing_clone_raises_called_process_error(tmp_path):
    dest = tmp_path / "broken"

    with pytest.raises(subprocess.CalledProcessError):
        disk_guard.clone_with_limit(
            "https://example.invalid/broken.git",
            str(dest),
            max_mb=64,
            poll_seconds=0.05,
            command=[sys.executable, "-c", "raise SystemExit(128)"],
        )


def test_post_clone_check_catches_a_repo_that_slipped_past_polling(tmp_path):
    """A clone can finish between two polls; the size check must still fire."""
    dest = tmp_path / "fast"
    script = textwrap.dedent(
        f"""
        import os
        os.makedirs({str(dest)!r}, exist_ok=True)
        with open(os.path.join({str(dest)!r}, "big.bin"), "wb") as fh:
            fh.write(b"x" * (4 * 1024 * 1024))
        """
    )

    with pytest.raises(disk_guard.RepoTooLargeError):
        disk_guard.clone_with_limit(
            "https://example.invalid/fast.git",
            str(dest),
            max_mb=1,
            poll_seconds=30,  # guarantees no poll fires before the process ends
            command=[sys.executable, "-c", script],
        )

    assert not dest.exists()


def test_max_repo_mb_reads_env_at_call_time(monkeypatch):
    monkeypatch.setenv("MAX_REPO_MB", "42")
    assert disk_guard.max_repo_mb() == 42
    monkeypatch.delenv("MAX_REPO_MB")
    assert disk_guard.max_repo_mb() == disk_guard.DEFAULT_MAX_REPO_MB


def test_clone_refuses_a_url_that_parses_as_a_git_option(tmp_path):
    """`git clone --upload-pack=<cmd>` executes <cmd>; a dash-leading URL must not reach git."""
    with pytest.raises(ValueError):
        disk_guard.clone_with_limit(
            "--upload-pack=touch owned",
            str(tmp_path / "dest"),
            max_mb=64,
        )


def test_force_rmtree_retries_a_transient_sharing_violation(tmp_path, monkeypatch):
    """A just-killed process releases its handles a moment after it dies.

    Windows raises PermissionError [WinError 32] in that window, which no
    chmod can fix -- force_rmtree has to wait it out rather than propagate.
    """
    victim = tmp_path / "locked"
    victim.mkdir()
    (victim / "held.bin").write_text("data")

    real_rmtree = disk_guard.shutil.rmtree
    calls = []

    def _flaky(path, **kwargs):
        calls.append(path)
        if len(calls) < 3:
            raise PermissionError(32, "The process cannot access the file")
        return real_rmtree(path, **kwargs)

    monkeypatch.setattr(disk_guard.shutil, "rmtree", _flaky)

    disk_guard.force_rmtree(victim, attempts=5, delay=0.01)

    assert len(calls) == 3
    assert not victim.exists()


def test_force_rmtree_gives_up_on_a_permanently_locked_path(tmp_path, monkeypatch):
    """The retry is bounded -- a genuinely locked directory must still raise."""
    def _always_locked(path, **kwargs):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(disk_guard.shutil, "rmtree", _always_locked)

    with pytest.raises(PermissionError):
        disk_guard.force_rmtree(tmp_path, attempts=3, delay=0.01)
