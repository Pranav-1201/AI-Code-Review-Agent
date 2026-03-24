# ==========================================================
# File: config.py
# Purpose: Load environment configuration variables
# ==========================================================

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ----------------------------------------------------------
# HuggingFace Configuration
# ----------------------------------------------------------

HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

# Optional: warn if token not found
if HF_TOKEN is None:
    print(
        "[Config] Warning: HUGGINGFACE_TOKEN not found. "
        "Public models will still load but rate limits may apply."
    )