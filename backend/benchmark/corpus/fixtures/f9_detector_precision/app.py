"""Fixture: detector precision (Phase G).

Every decoy here is a shape the analyzer reported as a vulnerability before
Phase G. They are the real-world patterns behind the measured result that all
five security findings on pallets/flask were false positives
(docs/ANALYZER_ACCURACY_2026-08.md).

The true positives at the bottom are the ones the fixes had to keep. A version
of this fixture that only held decoys would pass by detecting nothing at all.
"""
import subprocess

from flask import Flask

app = Flask(__name__)


def start():
    app.run(debug=True)                                # decoy: Flask, not subprocess


class Job:
    def go(self):
        self.run(1, 2)                                 # decoy: a method named run


def announce(name, count):
    print(f"Failed to delete {name}")                  # decoy: prose, not a query
    print(f"About to update {count} records")          # decoy: prose, not a query
    print("Deleted user: " + name)                     # decoy: prose concatenation


def clone(args):
    subprocess.run(["git", *args])                     # decoy: argv[0] is a program


def commit(message):
    subprocess.run(["git", "commit", "-m", message])   # decoy: dynamic ARGUMENT only


def status():
    cmd = ["git", "status"]
    subprocess.run(cmd)                                # decoy: argv in a variable


def danger(user):
    subprocess.run(["sh", "-c", user])                 # TP command_injection


def lookup(db, uid):
    return db.execute(f"SELECT * FROM users WHERE id = {uid}")   # TP sql_injection
