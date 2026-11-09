# Observed Chrome page identities and CSP companions

## MCP page identity

Three independent Python controls run the existing Chrome contract with a
controlled MCP provider and verify its page selector. The provider lists page
37 or 904, then requires that observed `pageId` on navigation, snapshot, and
the deliberately invalid navigation control. No default page identity is assumed.
Missing, malformed, foreign, or ambiguous initial page listings are rejected.

The intact implementation passes. A disposable mutation hardcodes page ID 1;
the exact same tests fail at the provider boundary for both observed identities.
`browser-identity-controls/` retains test/source hashes, native outcomes, logs,
and the small mutation patch. These controls qualify invocation arguments;
actual Chrome MCP behavior remains covered by hosted integration execution.

## CSP companion classification

Four native Node controls use the exact console diagnostic observed from Chrome
157's hosted inline-script fault. Its console location URL is empty. A positive
classification requires the exact diagnostic and script hash plus independent
same-document `script-src-elem`, inline, enforcement-event evidence. The same
diagnostic at the document URL is also accepted. Other messages, hashes, console
locations, documents, directives, blocked resources, and report-only events stay
unexpected.

The intact classifier passes all controls. Disposable mutations that remove the
independent event requirement or replace exact message matching with a prefix
each make the unchanged controls fail. `csp-companion-controls/` retains the
native Node results, source/test hashes, and mutation patches. No Playwright
assertion or shared implementation was weakened to produce these red results.

Replay Python controls with a selected source tree:

```sh
TEST_SUBJECT_ROOT=/absolute/path/to/subject python3 -m unittest discover \
  -s tests/integration -p test_chrome_identity.py -v
```

Replay the dependency-free classifier controls in the candidate checkout:

```sh
node --test --test-reporter=tap tests/browser/expected-errors.test.mjs
```
