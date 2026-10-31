# Contributions — team agreement pending

| Member | Responsibilities | Experiments / report section | Agreed share |
|---|---|---|---|
| Don | Protocol, revision state, server wiring, live caption semantics | T1/T2; architecture and protocol | Pending team agreement |
| Dylan | Bounded final history, local recall, incremental recovery | T4; recovery and history | Pending team agreement |
| Damian | Semantic mailbox, client writers, reconnect transport | T3; delivery and backpressure | Pending team agreement |
| Leonard | Runtime settings, bounded overflow policy, browser shell, Ubuntu test support | T5 and before/after; experimental method and analysis | Pending team agreement |

Responsibilities describe the team plan and must be checked against merged PRs.
Don's browser store and Damian's connection manager are merged. Dylan's
browser history is in PR #18; Leonard's shell PR #13 imports it and should
merge after #18. Leonard's server measurements combine peer components for testing. PR #19 proposes a
cross-component retention fix for Don and Dylan to review; that contribution
does not transfer ownership of their components. Final percentages require
actual team agreement; no equal split is assumed. Add student IDs and confirm completed contributions
before submission. The demo video remains Dylan's planned support responsibility.
