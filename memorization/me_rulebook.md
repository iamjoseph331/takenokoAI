## Memory Management Principles

1. Prioritize storing information useful for future decisions over raw completeness.
2. Tag all memories with: source family, timestamp, and relevance tags.
3. Short-term memory expires after the current session/game unless promoted to long-term.
4. Forgetting is as important as remembering — purge low-relevance short-term memories periodically.

## Memory Types

### Short-term
- Current game state, recent messages, working context.
- Auto-expires at session end.
- Max capacity: configurable per session.

### Long-term
- Cross-session lessons, strategies that worked, known patterns.
- Persisted to disk.
- Requires explicit promotion from short-term or direct store request.

### Logs
- Every thought, message, and action archived for auditing.
- Write-only during session; searchable for debugging.

## Handling Store Requests

1. Validate that the content has required metadata (tags, memory_type).
2. If `memory_type` is not specified, default to `short_term`.
3. Assign a unique `memory_id` and return it to the requester.
4. Log the store operation.

## Handling Search Requests

1. Search across the specified memory type (or all types if none specified).
2. Return results ranked by relevance to the query.
3. Cap results at the requested limit.
4. Include `memory_id` in each result for follow-up recall.

## Handling Recall Requests

1. Look up by `memory_id`.
2. Return the full memory record, or indicate not found.

## Log Archival

Me is the keeper of logs. When other families request log data, search the structured log records. Me does not duplicate the file-based logging in `interface/logging.py` — it provides semantic search over logged events.
