# Observed Chrome MCP and CSP contract inputs

`hosted-failures.json` retains selected raw fields from the second hosted run:
Chrome MCP 1.12.0 required `pageId` for navigation/snapshot; its actual initial
listing assigned ID 1. Independent controls deliberately use different IDs to
prevent that observation becoming a hardcoded assumption.

The same run passed six Playwright cases. Its CSP case detected the enforced
violation and blocked the script, but Chrome 157 emitted the companion console
message with an empty location URL. The recorded message, script hash and empty
location ground the corrected classifier. Independent native CSP event/document
matching remains required; this record alone does not waive that check.

The original artifact URL, run and tested source revision are retained. These
are failure observations, distinct from the red/green and mutation controls in
the adjacent evidence directories and from a subsequent passing provider run.
