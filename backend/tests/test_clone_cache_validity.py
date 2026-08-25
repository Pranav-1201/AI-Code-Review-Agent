"""
A cached clone is trusted only if git itself will accept it.

Observed live on 2026-08-26: scanning https://github.com/pallets/flask failed
with

    Command '['git', '-C', '...\\7e3d4d99...', '-c',
    'http.postBuffer=524288000', 'fetch', 'origin']'
    returned non-zero exit status 128

surfaced to the user as a raw CalledProcessError repr. The cached clone
directory existed and contained a `.git` directory, so the re-scan branch in
main._run_scan_pipeline took the incremental path — but that `.git` held only
objects/, refs/, logs/, index and FETCH_HEAD. HEAD and config were gone: the
residue of an eviction (disk_guard.force_rmtree) that deleted part of the tree
and then stopped. git rejects such a directory outright.

Three of the twelve cached clones on that machine were in this state, and the
failure is PERMANENT for the affected repo — nothing ever clears the broken
directory, so every subsequent scan of it takes the same branch and dies the
same way.

The gate was `os.path.isdir(repo_dir/".git")`, which is a question about the
filesystem, not about git. These tests ask git.
"""

import os
import subprocess

import main


def _git(repo, *args):
    # Never touch global git config (Defect G): identity via `git -c`.
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t.local",
         "-c", "user.name=test", *args],
        check=True, capture_output=True,
    )


def _real_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v1")
    return root


def test_a_real_clone_is_usable(tmp_path):
    repo = _real_repo(tmp_path / "good")
    assert main._usable_cached_clone(str(repo)) is True


def test_a_missing_directory_is_not_usable(tmp_path):
    assert main._usable_cached_clone(str(tmp_path / "nope")) is False


def test_a_directory_without_dot_git_is_not_usable(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert main._usable_cached_clone(str(plain)) is False


def test_half_deleted_dot_git_is_not_usable(tmp_path):
    """The exact residue observed: objects/refs/logs/index, no HEAD, no config.

    This is the case the old isdir() gate accepted and `git fetch` then
    rejected with exit 128.
    """
    repo = _real_repo(tmp_path / "victim")

    # Reproduce the interrupted eviction: remove the worktree and the two
    # files git needs to recognise a repository, leaving the rest behind.
    os.remove(repo / "a.py")
    os.remove(repo / ".git" / "HEAD")
    os.remove(repo / ".git" / "config")

    # Precondition: the OLD gate would have accepted this directory.
    assert os.path.isdir(os.path.join(str(repo), ".git"))

    # And git really does reject it — this is what produced exit 128 live.
    probe = subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin"],
        capture_output=True,
    )
    assert probe.returncode == 128

    assert main._usable_cached_clone(str(repo)) is False
