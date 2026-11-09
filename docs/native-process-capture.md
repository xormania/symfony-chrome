# Native process capture

Development tooling and the CI suite runner share `bin/processlib.py` for bounded
native output collection. The suite runner keeps its merged `native.log` format.
Captured development commands retain stdout and stderr separately, so diagnostic
stderr cannot corrupt a JSON stdout response.

One aggregate 8 MiB budget applies to both streams. The helper drains into bounded
files and only constructs returned Python bytes/text after a complete capture.
Overflow or timeout raises `NativeCaptureError` even with `check=False`, before a
caller can parse incomplete output as a result. A completed native nonzero result
retains normal `CompletedProcess` and `check=True` behavior.

Captured development commands default to a 180-second deadline. In a suite, their
deadline is capped by the remaining suite budget, reserving the existing
20-second process-group cleanup window. An exhausted budget starts no new native
command. The deadline also covers descendants retaining output pipes after their
parent exits. Noncaptured streaming execution keeps its existing behavior.

`native-capture.json` records the native exit, timeout/truncation flags, configured
budgets, retained byte counts, observed-byte lower bound and log lifecycle. It does
not add command arguments or payloads to public evidence.

Generic `devlib.execute(capture_output=True)` streams remain under the selected
workspace's private state, with public status metadata only. They are explicitly
marked `private_ephemeral` / `purged_with_workspace`. This preserves Mate's private
compiled-container export boundary. Existing caller-owned safe outputs retain
their existing locations. Mate and Mago invocation capture uses the same engine;
enriched Mago preserves partial native streams when capture fails.

Independent native controls and a doubled-budget red proof are retained under
`docs/evidence/native-capture-controls/`. These exercise native Python peers and
the actual `devlib.execute` capture seam without a Docker daemon. Full browser,
Mate/Mago and Serena integration is verified separately in hosted CI.
