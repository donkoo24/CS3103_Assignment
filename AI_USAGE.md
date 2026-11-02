# AI usage

Leonard: I used OpenAI Codex to help implement runtime configuration and bounded
overload handling, the browser shell, public-test scripts and experiment/report
preparation. I also used it to inspect teammates' open PRs, identify integration
dependencies, adapt the browser shell to Don's store and Dylan's history
module, draft tests, execute checks on the Ubuntu VM, and prepare a separate
bounded-state integration fix across team modules. This was substantial code
assistance. I remain responsible for reviewing and understanding
my contribution before merging and for explaining it during the viva.

A useful suggestion was to bound the browser's pending render map as well as its
visible rows, while processing caption updates immediately and scheduling one
paint per animation frame. The shell test exercises a 1,000-message burst and a
300-row bound. This checks rendering behavior, not network performance.

One suggestion that needed correction was the large experiment framework: hidden
profiles, a 16-setting sweep, repeated comparison matrices, source bundles and
custom runtime installation. I used AI to compare that work with the assignment
PDF and reduce it to T1–T5 and one controlled T3 comparison. The team's additional
latency/freshness thresholds were also incorrectly emphasized as requirements;
the report now distinguishes them from the PDF's completeness grading caps.
The extra probe-interval knob and an unproven multi-setting default change were
removed. Measurements are retained only for the settings actually tested.

PR #19 merged into `main`; Don and Dylan still need to review its effect on
their state, history and browser store modules before final submission.

The existing notes record Damian's Claude Code assistance for mailbox and Hub
work, including corrected generated bugs. Each member must review their own usage
record; this document does not infer unrecorded usage for teammates. Pending
merge of this integration PR, the demo video and the contribution
agreement are not claimed complete. AI assistance does not replace team
review or individual understanding.

I used Codex to investigate why the browser could show Offline while captions
continued arriving. It helped add offline socket shutdown and guards against
late events from closed or replaced sockets, with tests for offline/online
recovery and resuming from the last finalized caption.
