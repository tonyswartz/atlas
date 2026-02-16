## 2024-05-22 - [Optimizing Pure Python Vector Operations]
**Learning:** The codebase performs vector operations (cosine similarity) in pure Python because `numpy` is not available. Calculating vector magnitudes inside loops for constant vectors (like query embeddings) causes significant overhead (O(N*d) vs O(N)).
**Action:** When working with vector search in this repo, always pre-calculate magnitudes for constant vectors outside the loop. If possible, consider advocating for `numpy` dependency for heavy vector math, but for now, optimize the pure Python implementation.
