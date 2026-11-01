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

For the H3/H8 follow-up, I used Codex to inspect the saved client traces and
Hub code, draft the recovery changes and regression tests, and run the Ubuntu
experiments. I rejected applying a small frame window to every client and
changing TCP_NODELAY globally after the diagnostic runs got worse. The final
results include the remaining freshness limits and missing finals rather than
claiming the instructor's hidden tests passed.

I also used Codex to investigate the last missing finals and test further
changes. Several changes to reader pacing and source completion did not help
consistently, so I left them out. I kept a small bounded final-flush change
after H3 reached 100% in all three repeats. H8 still missed some finals, and
I retained those results and the worst run in the write-up.
