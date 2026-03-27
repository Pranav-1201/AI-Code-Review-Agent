# ==========================================================
# File: duplicate_detector.py
# Purpose: Detect duplicate and similar code blocks
# ==========================================================

import hashlib
from typing import List, Dict
from collections import defaultdict


def _normalize_line(line: str) -> str:
    """
    Normalize a line of code for comparison:
    - strip whitespace
    - lowercase
    - remove comments
    """
    line = line.strip()

    # Remove Python comments
    if "#" in line:
        line = line[:line.index("#")].strip()

    return line.lower()


def _hash_block(lines: List[str]) -> str:
    """Hash a block of normalized lines."""
    content = "\n".join(lines)
    return hashlib.md5(content.encode()).hexdigest()


def detect_duplicates(files: List[Dict], min_block_size: int = 6) -> List[Dict]:
    """
    Detect duplicate code across repository files.

    Two-pass approach:
    1. Exact file match (MD5 of entire file)
    2. Block-level similarity (sliding window of normalized lines)

    Parameters
    ----------
    files : List[Dict]
        File data with "content" and "file_name" keys.
    min_block_size : int
        Minimum number of consecutive lines to consider a block.

    Returns
    -------
    List[Dict]
        List of duplicate pairs with file names and similarity.
    """

    duplicates = []
    seen_pairs = set()

    # --------------------------------------------------
    # Pass 1: Exact file-level duplicates
    # --------------------------------------------------

    file_hashes = {}

    for file in files:
        code = file.get("content", "")
        fname = file.get("file_name", "")

        h = hashlib.md5(code.encode()).hexdigest()

        if h in file_hashes:
            pair_key = tuple(sorted([file_hashes[h], fname]))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                duplicates.append({
                    "file1": file_hashes[h],
                    "file2": fname,
                    "similarity": 100,
                    "type": "exact"
                })
        else:
            file_hashes[h] = fname

    # --------------------------------------------------
    # Pass 2: Block-level similarity
    # --------------------------------------------------

    # Build block index: hash -> list of (file_name, line_number)
    block_index: Dict[str, List[tuple]] = defaultdict(list)

    for file in files:
        code = file.get("content", "")
        fname = file.get("file_name", "")

        lines = code.splitlines()
        normalized = [_normalize_line(l) for l in lines]

        # Filter out empty/trivial lines for block matching
        significant = [(i, l) for i, l in enumerate(normalized) if l and len(l) > 3]

        if len(significant) < min_block_size:
            continue

        # Sliding window over significant lines
        for start_idx in range(len(significant) - min_block_size + 1):
            block_lines = [significant[start_idx + j][1] for j in range(min_block_size)]
            block_hash = _hash_block(block_lines)
            block_index[block_hash].append((fname, significant[start_idx][0]))

    # Find files sharing blocks
    file_shared_blocks: Dict[tuple, int] = defaultdict(int)
    file_total_blocks: Dict[str, int] = defaultdict(int)

    for file in files:
        code = file.get("content", "")
        fname = file.get("file_name", "")
        lines = code.splitlines()
        normalized = [_normalize_line(l) for l in lines]
        significant = [(i, l) for i, l in enumerate(normalized) if l and len(l) > 3]

        if len(significant) >= min_block_size:
            file_total_blocks[fname] = len(significant) - min_block_size + 1

    for block_hash, locations in block_index.items():

        # Get unique files in this block
        file_names = list(set(loc[0] for loc in locations))

        if len(file_names) < 2:
            continue

        # Count shared blocks between each pair
        for i in range(len(file_names)):
            for j in range(i + 1, len(file_names)):
                pair = tuple(sorted([file_names[i], file_names[j]]))
                file_shared_blocks[pair] += 1

    # Convert to similarity percentage
    for (f1, f2), shared_count in file_shared_blocks.items():

        # Skip if already found as exact match
        pair_key = tuple(sorted([f1, f2]))
        if pair_key in seen_pairs:
            continue

        total1 = file_total_blocks.get(f1, 1)
        total2 = file_total_blocks.get(f2, 1)

        # Similarity based on the smaller file
        min_total = min(total1, total2)
        if min_total == 0:
            continue

        similarity = round(min(shared_count / min_total * 100, 100))

        # Only report significant similarity (> 30%)
        if similarity >= 30:
            seen_pairs.add(pair_key)
            duplicates.append({
                "file1": f1,
                "file2": f2,
                "similarity": similarity,
                "type": "block"
            })

    # Sort by similarity descending
    duplicates.sort(key=lambda d: d.get("similarity", 0), reverse=True)

    return duplicates