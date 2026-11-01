# Team Contributions

| Member | Main responsibilities | Experiments/report sections | Agreed contribution % |
|---|---|---|---:|
| Don [Student ID] | Project setup and coordination; protocol parsing and encode-once (`protocol.py`); revision state (`state.py`); server wiring (`solution_server.py`); browser caption store (`client/store.js`) | T1 and T2; report: architecture, protocol and revision semantics | 25 |
| Dylan [Student ID] | Bounded final history, resume/late-join handshake and HISTORY cache (`history.py`); browser recall history (`client/history.js`) | T4, H5 and H6; report: bounded history and recovery; demo video | 25 |
| Damian [Student ID] | Hub and per-client writer tasks (`hub.py`); semantic mailbox (`mailbox.py`); ping-based lag detection and slow-reader overload policy; browser connection and reconnect (`client/connection.js`) | T3, H2 and H7; report: delivery and backpressure; final report assembly | 25 |
| Leonard [Student ID] | Runtime configuration and overflow policy (`config.py`, `policy.py`); startup scaling; FIFO baseline; browser shell and UI (`client/app.js`); Ubuntu test tooling (`scripts/stress.sh`) | T5 and the FIFO vs semantic before/after comparison; report: experiments and results; packaging | 25 |

Total contribution should be 100%.

Shared and integration work: every feature was merged through a reviewed pull request, with CI running unit tests, `submission_check.py` and a T1 smoke test. Leonard's bounded-state fix (`feat/state-bounds`) touched Don's revision state, Dylan's history and Don's browser store; ownership of those components stays with their authors. Git history is supporting evidence, not a substitute for this statement.
