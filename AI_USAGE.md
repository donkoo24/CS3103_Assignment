# AI usage

Leonard: I used OpenAI Codex to help implement runtime configuration and bounded
overload handling, the browser shell, public-test scripts and experiment/report
preparation. I also used it to inspect teammates' open PRs, identify integration
dependencies, adapt the browser shell to Don's merged ES module store, draft
tests and execute checks on the Ubuntu VM. This included
substantial code assistance. I remain responsible for reviewing and understanding
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

The existing notes record Damian's Claude Code assistance for mailbox and Hub
work, including corrected generated bugs. Each member must review their own usage
record; this document does not infer unrecorded usage for teammates. Pending
browser integration, the demo video and the contribution agreement are not claimed
complete. AI assistance does not replace team review or individual understanding.
