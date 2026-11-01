# Report on `liverecall/history.py`

## Purpose

`liverecall/history.py` implements the server-side finalized-caption history
used for late joins and reconnect recovery. It stores only accepted final
captions, selects the relevant recovery window, and serializes the result as a
compact `HISTORY` protocol message. The implementation is bounded so that
history memory does not grow with the length of a session.

## Main implementation

The `FinalHistory` class uses two sorted indexes. The time-ordered index allows
the start of a requested time window to be found with binary search. The
segment-ordered index preserves segment order when captions arrive with
non-monotonic timestamps and supports comparison with a client's last known
segment and revision. A dictionary keyed by segment prevents duplicate finals
from being stored.

When a caption is added, provisional captions are ignored, and a segment that
already has a final caption is not inserted again. New entries update the
newest source timestamp and are immediately pruned. The default limits are 90
seconds of retention and 512 captions. Entries outside the timestamp window or
above the item limit are removed from both indexes together.

## Recovery behavior

`history_for()` supports two request types:

- A new client can request a recent window, capped at 60 seconds. Invalid,
  negative, zero, or non-finite values are normalized safely.
- A reconnecting client supplies its last finalized segment and revision. The
  request uses the complete 60-second recovery window, regardless of a smaller
  requested late-join window, and excludes captions at or before the supplied
  cursor. A newer revision of the same segment is still returned.

Selected captions are returned oldest-first. If test or integration callers
insert captions whose timestamps do not match segment order, the result is
sorted by segment and revision before it is sent. `history_msg()` creates a
valid compact `HISTORY` message, including a valid empty message when there are
no matching captions.

## Message-cache optimization

`_HistoryMessageCache` is a bounded least-recently-used cache for encoded
`HISTORY` responses. Requests are keyed by normalized last segment, last
revision, and window size. The cache holds at most 64 entries and 8 MiB of
UTF-8 encoded messages. Access refreshes recency; inserting a new message
evicts the least-recently-used entries as needed, and an individual oversized
message is not cached. The cache is cleared whenever the underlying history
changes, preventing stale recovery responses while allowing repeated reconnect
requests to reuse identical encoded output.

## Integration with the server

`solution_server.py` adds accepted final captions to the global `FinalHistory`
instance. It then exposes the oldest retained segment so the global revision
state can discard metadata that has fallen outside the same retention bound.
During `CLIENT_HELLO`, the server builds the cached history message and passes
it as the first message when registering the client. This keeps the recovery
snapshot ahead of live updates and avoids a gap between selecting history and
starting delivery.

## Verification

The tests in `tests/test_history.py` cover final-only storage, duplicate
handling, chronological and segment ordering, time and count pruning, late
join windows, reconnect cursors, revision recovery, JSON serialization, cache
reuse, LRU eviction, and oversized-message handling. The related retention
integration tests in `tests/test_submission_bounds.py` verify that revision
state follows the oldest retained history entry.

The focused verification completed successfully:

```text
18 passed in 0.03s
```

The module also passed Python bytecode compilation with `compileall`.

## Limitations and trade-offs

The indexes are maintained with Python lists, so insertion and removal shift
list elements and are linear in the number of retained captions. This is
acceptable for the configured 512-item bound and keeps window lookup simple.
The cache improves repeated response construction at the cost of bounded extra
memory. Recovery remains intentionally limited to the retained 90-second
history and the 60-second request window; captions older than those limits
cannot be reconstructed by this module.
