# Agent conventions for this repository

Created 2026-11-09.

## Git attribution

**No AI attribution.** Commits are attributed to the human contributor who
made them, as author and committer, using their own GitHub identity. Do not
add `Co-Authored-By` lines for AI tools, session links, model identifiers or
any other agent trailer to commit messages. Pull request titles, bodies and
comments likewise carry no AI attribution footer or badge. This applies to
every contributor and every agent working in this repository.

## Working rules

- Develop on the branch assigned to the session; never push to another branch without being asked.
- Pins live in `toolchain.lock.json`; change a pin only together with the Dockerfile line that uses it.
- `fixtures/app/` is checked-in input. Workspaces under `workspaces/` are disposable copies; evidence under `artifacts/` is retained.
- `private/` is gitignored and belongs to a separate private repository. Nothing here reads from it.
- State what was executed and what was not. A written Dockerfile is not a built image.
