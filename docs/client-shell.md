# Leonard: client shell integration

Serve with `python -m http.server 8000 --directory client`, then open
`http://<server-host>:8000`. WebSocket defaults to the page hostname on port 8765
(wss for HTTPS). Override with `?server=ws%3A%2F%2Fhost%3A8765`.

The shell loads Don's merged ES module `CaptionStore`, then creates a
`window.LiveRecall.createStore` adapter before starting `app.js`. The same module bootstrap imports Dylan's `createHistory` from `history.js`.
Damian's connection manager is a plain script on `window.LiveRecall`:

- `createConnection(options)`: the exact API in Damian's PR #7.

`createShell(options)` also accepts explicit adapters if another export convention
is chosen. Don's store and Damian's connection manager are on `main`. Dylan's browser
history comes from PR #18, which must merge before this PR. A visible Offline
explanation replaces a silent partial connection if dependencies are missing;
Leonard's shell does not duplicate team caption, history or transport logic.
A headless Chromium two-tab smoke with the deterministic source checked live
updates, late join, offline/reconnect, recovered rows and all recall buttons.
The team still needs to record and review the required demo video.

The render map, live rows, and recall rows each retain at most 300 entries.
Every message still reaches the semantic store/history immediately; only painting
is coalesced into one requestAnimationFrame. The store/history owners must bound
their own data. The shell uses textContent for source text, preserves scroll
position while following is paused, and provides a Return to live button.

Manual integrated checks: two tabs; revision replacement; 15/30/60 recall;
late join; source text containing HTML; disconnect/reconnect recovery; scroll up
during bursts; 300-row limit; mobile view; keyboard focus; storage disabled.

The browser's offline state suspends the WebSocket connection instead of only
changing its badge. New socket messages are ignored while offline; locally
stored captions remain available for recall. Going online reconnects with the
last finalized cursor. Explicitly closed and superseded sockets cannot deliver
late messages or overwrite the connection status.
