# Retained state and malformed client cursors

Final history already has a 90-second, 512-caption bound. The server now prunes
revision metadata below its oldest retained final segment after each accepted
final. A floor prevents an old replay from being treated as a new segment after
pruning. The browser caption store similarly retains at most 512 segment states
and keeps a floor for old replays; its latest-final cursor survives eviction.
The separate local recall history keeps its own 90-second/512-item bound.

This assumes the source's documented increasing segment sequence. A malformed
CLIENT_HELLO cursor now closes that client with WebSocket code 1008 instead of
raising from the connection handler. Neither change alters valid wire messages.
