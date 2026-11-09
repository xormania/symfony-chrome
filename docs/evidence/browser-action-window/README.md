# Observe the action after the initial icon finishes

Hosted run `42565965682` confirmed the bootstrap fix: owned Chrome, borrowed
Chrome, correlation and all five tooling contracts passed. Six browser cases
passed. The client-only interaction case correctly rejected an unexpected
`/_ci/icon.svg` request in its measurement window; Chrome had scheduled this
initial document resource after the document load event.

The case now registers an exact icon response waiter before navigation, verifies
its HTTP 200 status and completed response, then starts counting requests before
the real click. The existing `requests === []` assertion still covers every
request in the action window. No URL is filtered from that observation and no
timer, retry, error allowance or additional Playwright case is introduced.

The native failure output and original artifact/check identities are retained
alongside this note. ANSI formatting is removed from the log for readability.
Actual selected Chrome execution remains required in hosted CI.
