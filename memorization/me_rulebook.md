## Storage Protocol

When a store request arrives:

1. Assign a unique `memory_id` (format: `mem_<8-digit counter>`).
2. Categorize by `memory_type`: `short_term`, `long_term`, or `log`.
3. Index by provided tags for retrieval.
4. Confirm storage with the memory_id back to the requester.

### Memory types

- **short_term**: Recent context, game state, current conversation. Volatile — may be evicted when capacity is reached.
- **long_term**: Lessons learned, strategies, persistent knowledge. Retained across sessions if possible.
- **log**: Raw activity logs. Write-heavy, read on demand.

## Search Protocol

When a search request arrives:

1. Match against tags, memory_type, and content (keyword match for now; semantic search in future).
2. Return results sorted by relevance (tag match count, then recency).
3. Respect the `limit` parameter.
4. If no results found, return an empty list — do not fabricate memories.

## Recall Protocol

When a recall request arrives:

1. Look up by exact `memory_id`.
2. Return the full memory record, or `None` if not found.

## Passive Logging

Me should store every message that flows through the bus as a `log`-type memory. This enables the agent to review its own history.

Stage 1: Not yet implemented — depends on bus subscriber integration.
