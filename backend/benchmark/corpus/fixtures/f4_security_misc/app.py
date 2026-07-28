"""Fixture: Hardcoded Credential, Insecure Config, Weak Crypto, Race Condition."""
import hashlib
import tempfile
import os

import requests

password = "hunter2supersecret"                  # TP hardcoded_credential
api_key = "sk-live-abc123def456ghi"              # TP hardcoded_credential
db_pass = os.environ["DB_PASS"]                  # decoy: from env


def weak(pw):
    return hashlib.md5(pw.encode()).hexdigest()      # TP weak_crypto


def strong(pw):
    return hashlib.sha256(pw.encode()).hexdigest()   # decoy: sha256


def tmp():
    return tempfile.mktemp()                         # TP race_condition


def tmp_safe():
    return tempfile.mkstemp()                        # decoy: mkstemp


def fetch(url):
    return requests.get(url, verify=False)           # TP insecure_config


def fetch_safe(url):
    return requests.get(url, verify=True)            # decoy
