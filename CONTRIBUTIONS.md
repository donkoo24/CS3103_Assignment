# Contributions — team agreement pending

| Member | Responsibilities | Experiments / report section | Agreed share |
|---|---|---|---|
| Don | Protocol, revision state, server wiring, live caption semantics | T1/T2; architecture and protocol | Pending team agreement |
| Dylan | Bounded final history, local recall, incremental recovery | T4; recovery and history | Pending team agreement |
| Damian | Semantic mailbox, client writers, reconnect transport | T3; delivery and backpressure | Pending team agreement |
| Leonard | Runtime settings, bounded overflow policy, browser shell, Ubuntu test support | T5 and before/after; experimental method and analysis | Pending team agreement |

Responsibilities describe the team plan and must be checked against merged PRs.
Don's browser store, Damian's connection manager and Dylan's browser history
are merged. Leonard's shell from PR #13 imports those modules and is included
in this integration PR. Leonard's server measurements combine peer components
for testing. PR #19 merged a cross-component retention fix for Don and Dylan
to review before submission; that contribution
does not transfer ownership of their components. Final percentages require
actual team agreement; no equal split is assumed. Add student IDs and confirm completed contributions
before submission. The demo video remains Dylan's planned support responsibility.
