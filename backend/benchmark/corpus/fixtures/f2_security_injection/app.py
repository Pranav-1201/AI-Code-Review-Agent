"""Fixture: Command Injection + SQL Injection. TPs + safe decoys."""
import os
import subprocess


def backup(path):
    os.system("tar -czf backup.tgz " + path)      # TP command_injection


def run_shell(cmd):
    subprocess.call(cmd, shell=True)               # TP command_injection


def safe_run():
    subprocess.run(["ls", "-l"])                   # decoy: list args, no shell


def fetch_user(db, uid):
    q = "SELECT * FROM users WHERE id = " + uid    # TP sql_injection (concat)
    return db.execute(q)


def fetch_fmt(db, name):
    return db.execute(f"SELECT * FROM t WHERE n = '{name}'")  # TP sql_injection


def safe_query(db, uid):
    return db.execute("SELECT * FROM users WHERE id = %s", (uid,))  # decoy
