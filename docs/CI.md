# Continuous integration

The workflow runs on pull requests, pushes to `master`, and manual dispatch.
There are no scheduled runs or duplicate feature-branch push runs.

| Job | Required suites |
| --- | --- |
| fast | fast |
| package | package |
| integration | support, environment, browser, tooling |
| Symfony Chrome acceptance | Every required job and its exact native evidence. |

The integration job validates the supported released parent, builds the pinned
development toolchain once with the Actions layer cache, then exercises the real
application/container. Fast and package tests execute independently of that build.

Each producer uploads `artifacts/` on success or failure, under a name containing
the job, workflow run and attempt. Retention is 14 days. The acceptance job runs
after failures too; it downloads this attempt's artifacts and validates:

- All required job conclusions succeeded.
- The job/suite mapping covers the current required profile exactly once.
- Plans name the actual tested commit and current workflow run/attempt.
- Every selected suite/check executed with passing native assertions.
- Native and normalized results agree, and retained artifact hashes match.

A successful build, upload or empty job is insufficient. Missing evidence,
unexpected skips, cancelled jobs and stale results fail acceptance.

Use **rerun all jobs** when rerunning a workflow: acceptance intentionally requires
a coherent producer attempt, rather than silently importing another attempt's
results. Original attempts remain available for diagnosis.

The stable status is `Symfony Chrome acceptance`. Repository settings must name
that status before it enforces merges. Workflow source alone does not activate a
ruleset; verify settings separately after the first successful hosted run. The
work does not add an owner review requirement at every revision.

See [TESTING.md](TESTING.md) for local commands, result interpretation, fixture
maintenance and the exact scope of each current acceptance claim.
