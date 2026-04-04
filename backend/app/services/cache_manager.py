import os
import json
import hashlib
from typing import Optional, Dict, Any, List

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")


class CacheManager:
    """
    Manages robust caching of file analysis results.
    The cache key is a hash of the file's text content AND its dependencies
    (imports) to ensure that changes in dependencies invalidate the cache if needed.
    """

    def __init__(self):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR, exist_ok=True)

    def _generate_key(self, content: str, imports: List[str] = None) -> str:
        imports_str = ",".join(sorted(imports)) if imports else ""
        raw_key = f"{content}___IMPORTS___{imports_str}"
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()

    def get(self, content: str, imports: List[str] = None) -> Optional[Dict[str, Any]]:
        key = self._generate_key(content, imports)
        cache_path = os.path.join(CACHE_DIR, f"{key}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def set(self, content: str, imports: List[str], result: Dict[str, Any]):
        key = self._generate_key(content, imports)
        cache_path = os.path.join(CACHE_DIR, f"{key}.json")
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception:
            pass
