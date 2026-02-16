"""
Tool: Hybrid Memory Search
Purpose: Combined BM25 (keyword) + Vector (semantic) search for optimal retrieval

This implements Moltbot's hybrid search approach:
- BM25 for exact token matching (good for specific terms)
- Vector search for semantic similarity (good for meaning)
- Combined scoring: 0.7 * bm25 + 0.3 * cosine (configurable)

Usage:
    python tools/memory/hybrid_search.py --query "GPT image generation"
    python tools/memory/hybrid_search.py --query "what tools" --limit 10
    python tools/memory/hybrid_search.py --query "meeting" --bm25-weight 0.5
    python tools/memory/hybrid_search.py --query "learned" --semantic-only
    python tools/memory/hybrid_search.py --query "API key" --keyword-only

Dependencies:
    - openai (for embeddings)
    - rank_bm25 (optional, falls back to simple TF-IDF)
    - sqlite3 (stdlib)

Env Vars:
    - OPENAI_API_KEY (required for semantic search)

Output:
    JSON with ranked results combining both search methods
"""

import os
import sys
import json
import argparse
import re
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
try:
    from semantic_search import semantic_search, cosine_similarity
    from embed_memory import generate_embedding, bytes_to_embedding
    from memory_db import get_connection, search_entries
except ImportError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    sys.exit(1)


def tokenize(text: str) -> List[str]:
    """Simple tokenizer for BM25."""
    # Lowercase, remove punctuation, split on whitespace
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = text.split()
    # Remove very short tokens
    return [t for t in tokens if len(t) > 1]


def bm25_search(
    query: str,
    entries: Optional[List[Dict]] = None,
    limit: int = 20,
    entry_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform BM25 keyword search using SQLite FTS5.

    Args:
        query: Search query
        entries: Deprecated/Ignored (kept for compatibility)
        limit: Maximum results
        entry_type: Optional type filter

    Returns:
        List of entries with BM25 scores
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Tokenize query to construct FTS MATCH expression
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # Use OR to match standard BM25 behavior (any term matches)
    fts_query = " OR ".join(query_tokens)

    # Use bm25() function from FTS5
    # Note: SQLite bm25() returns negative values where lower (more negative) is better.
    # We select rank to sort by it.
    sql = '''
        SELECT m.id, m.type, m.content, m.source, m.importance, m.tags, m.created_at, bm25(memory_entries_fts) as rank
        FROM memory_entries_fts
        JOIN memory_entries m ON memory_entries_fts.rowid = m.id
        WHERE memory_entries_fts MATCH ?
        AND m.is_active = 1
    '''
    params = [fts_query]

    if entry_type:
        sql += ' AND m.type = ?'
        params.append(entry_type)

    sql += ' ORDER BY rank LIMIT ?'
    params.append(limit)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        # Fallback if FTS table doesn't exist (shouldn't happen with migration)
        print(f"Warning: FTS search failed ({e}), returning empty result", file=sys.stderr)
        return []

    conn.close()

    if not rows:
        return []

    # Normalize scores to 0-1 range for compatibility
    # SQLite BM25 returns negative values. We flip them to positive.
    scores = [-row['rank'] for row in rows]
    max_score = max(scores) if scores else 1.0

    results = []
    for row, score in zip(rows, scores):
        # Normalize relative to the best match in this set
        norm_score = score / max_score if max_score > 0 else 0

        entry = dict(row)
        entry['bm25_score'] = round(norm_score, 4)
        entry['bm25_raw'] = round(score, 4)
        del entry['rank']

        # Parse tags if string
        if isinstance(entry.get('tags'), str):
             try:
                 entry['tags'] = json.loads(entry['tags'])
             except:
                 pass

        results.append(entry)

    return results


def hybrid_search(
    query: str,
    entry_type: Optional[str] = None,
    limit: int = 10,
    bm25_weight: float = 0.7,
    semantic_weight: float = 0.3,
    min_score: float = 0.1,
    semantic_only: bool = False,
    keyword_only: bool = False
) -> Dict[str, Any]:
    """
    Perform hybrid BM25 + semantic search.

    Args:
        query: Search query
        entry_type: Optional type filter
        limit: Maximum results
        bm25_weight: Weight for BM25 scores (default 0.7)
        semantic_weight: Weight for semantic scores (default 0.3)
        min_score: Minimum combined score
        semantic_only: Only use semantic search
        keyword_only: Only use keyword search

    Returns:
        dict with combined results
    """
    results = {
        "success": True,
        "query": query,
        "method": "hybrid",
        "weights": {"bm25": bm25_weight, "semantic": semantic_weight},
        "results": []
    }

    # Keyword-only search
    if keyword_only:
        results["method"] = "keyword_only"
        bm25_results = bm25_search(query, limit=limit, entry_type=entry_type)
        results["results"] = [{
            "id": r["id"],
            "type": r["type"],
            "content": r["content"],
            "score": r["bm25_score"],
            "bm25_score": r["bm25_score"],
            "semantic_score": None
        } for r in bm25_results]
        return results

    # Semantic-only search
    if semantic_only:
        results["method"] = "semantic_only"
        sem_results = semantic_search(query, entry_type=entry_type, limit=limit, threshold=0.3)
        if sem_results.get("success"):
            results["results"] = [{
                "id": r["id"],
                "type": r["type"],
                "content": r["content"],
                "score": r["similarity"],
                "bm25_score": None,
                "semantic_score": r["similarity"]
            } for r in sem_results.get("results", [])]
        return results

    # Full hybrid search
    # Step 1: BM25 search (get more candidates than needed)
    bm25_results = bm25_search(query, limit=limit * 3, entry_type=entry_type)
    bm25_scores = {r["id"]: r["bm25_score"] for r in bm25_results}

    # Map IDs to entry data for retrieval later
    entry_map = {r["id"]: r for r in bm25_results}

    # Step 2: Semantic search on candidates
    sem_results = semantic_search(query, entry_type=entry_type, limit=limit * 3, threshold=0.2)
    semantic_scores = {}
    if sem_results.get("success"):
        for r in sem_results.get("results", []):
            semantic_scores[r["id"]] = r["similarity"]
            entry_map[r["id"]] = r

    # Step 3: Combine scores
    all_ids = set(bm25_scores.keys()) | set(semantic_scores.keys())
    combined = []

    for entry_id in all_ids:
        bm25 = bm25_scores.get(entry_id, 0)
        semantic = semantic_scores.get(entry_id, 0)

        # Combined score
        combined_score = (bm25_weight * bm25) + (semantic_weight * semantic)

        if combined_score >= min_score:
            # Find the entry data
            entry_data = entry_map.get(entry_id)
            if entry_data:
                combined.append({
                    "id": entry_id,
                    "type": entry_data["type"],
                    "content": entry_data["content"],
                    "score": round(combined_score, 4),
                    "bm25_score": round(bm25, 4) if bm25 > 0 else None,
                    "semantic_score": round(semantic, 4) if semantic > 0 else None,
                    "importance": entry_data.get("importance")
                })

    # Sort by combined score
    combined.sort(key=lambda x: x["score"], reverse=True)

    results["results"] = combined[:limit]
    results["total_candidates"] = len(all_ids)
    results["above_threshold"] = len(combined)

    return results


def main():
    parser = argparse.ArgumentParser(description='Hybrid Memory Search (BM25 + Semantic)')
    parser.add_argument('--query', required=True, help='Search query')
    parser.add_argument('--type', help='Filter by memory type')
    parser.add_argument('--limit', type=int, default=10, help='Maximum results')
    parser.add_argument('--bm25-weight', type=float, default=0.7,
                       help='Weight for BM25 keyword scores (0-1)')
    parser.add_argument('--semantic-weight', type=float, default=0.3,
                       help='Weight for semantic scores (0-1)')
    parser.add_argument('--min-score', type=float, default=0.1,
                       help='Minimum combined score threshold')
    parser.add_argument('--semantic-only', action='store_true',
                       help='Only use semantic/vector search')
    parser.add_argument('--keyword-only', action='store_true',
                       help='Only use keyword/BM25 search')

    args = parser.parse_args()

    # Normalize weights
    total_weight = args.bm25_weight + args.semantic_weight
    bm25_w = args.bm25_weight / total_weight
    sem_w = args.semantic_weight / total_weight

    result = hybrid_search(
        query=args.query,
        entry_type=args.type,
        limit=args.limit,
        bm25_weight=bm25_w,
        semantic_weight=sem_w,
        min_score=args.min_score,
        semantic_only=args.semantic_only,
        keyword_only=args.keyword_only
    )

    if result.get('success'):
        count = len(result.get('results', []))
        print(f"OK Found {count} results using {result.get('method', 'hybrid')} search")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
