"""Fixture: Unsafe Deserialization. TPs + safe decoys."""
import pickle
import yaml
import json


def load_pickle(blob):
    return pickle.loads(blob)          # TP unsafe_deserialization


def load_pickle_file(fp):
    return pickle.load(fp)             # TP unsafe_deserialization


def load_yaml(text):
    return yaml.load(text)             # TP unsafe_deserialization (no SafeLoader)


def load_yaml_safe(text):
    return yaml.safe_load(text)        # decoy: safe_load


def load_json(text):
    return json.loads(text)            # decoy: json
