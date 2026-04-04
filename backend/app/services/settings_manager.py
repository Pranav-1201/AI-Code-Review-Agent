# ==========================================================
# File: settings_manager.py
# Purpose: Manage application settings with JSON persistence
# ==========================================================

import json
import os
from typing import Dict, Any

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "settings.json"
)

DEFAULT_SETTINGS = {
    "analysis": {
        "scan_depth": "deep",
        "analysis_level": "thorough",
        "max_files": 2000,
        "ignored_patterns": [
            "node_modules", ".git", "__pycache__",
            "dist", "build", ".venv", "venv"
        ],
        "min_file_lines": 1,
        "max_file_size_kb": 200,
    },
    "security": {
        "detect_eval": True,
        "detect_exec": True,
        "detect_subprocess": True,
        "detect_sql_injection": True,
        "detect_hardcoded_credentials": True,
        "detect_weak_crypto": True,
        "detect_wildcard_imports": True,
        "detect_unsafe_deserialization": True,
        "detect_command_injection": True,
        "detect_ssl_disabled": True,
    },
    "ai": {
        "model": "microsoft/codebert-base",
        "generate_suggestions": True,
        "generate_explanations": True,
        "generate_improved_code": True,
        "max_suggestions_per_file": 5,
    },
    "performance": {
        "parallel_analysis": False,
        "cache_results": False,
        "timeout_seconds": 300,
    },
    "ui": {
        "theme": "dark",
        "chart_animations": True,
        "show_line_numbers": True,
        "default_code_tab": "original",
    },
    "export": {
        "default_format": "json",
        "include_source_code": True,
        "include_improved_code": True,
        "include_patches": True,
    }
}


def _resolve_path():
    """Resolve absolute path for settings file."""
    return os.path.normpath(SETTINGS_FILE)


def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file, falling back to defaults."""
    path = _resolve_path()

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            # Merge with defaults (so new keys are always present)
            merged = _deep_merge(DEFAULT_SETTINGS, saved)
            return merged
        except Exception as e:
            print(f"Failed to load settings: {e}")

    return dict(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Save settings to JSON file. Returns the saved settings."""
    path = _resolve_path()

    # Merge with defaults to ensure all keys exist
    merged = _deep_merge(DEFAULT_SETTINGS, settings)

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to save settings: {e}")

    return merged


def reset_settings() -> Dict[str, Any]:
    """Reset settings to defaults."""
    return save_settings(DEFAULT_SETTINGS)


def _deep_merge(defaults: Dict, overrides: Dict) -> Dict:
    """Deep merge overrides into defaults."""
    result = dict(defaults)

    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result
