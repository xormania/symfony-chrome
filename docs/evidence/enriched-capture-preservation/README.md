# Enriched native failure preservation

Two native Python producer controls exercise the real enriched wrapper while mocking only fixture identity and command construction: an actual 9 MiB overflow and an actual SIGUSR1 interruption from the child. The healthy implementation retains bounded partial streams, records native outcomes, and preserves the original cancellation.

The controlled mutant restores the old unconditional finalizer writes. The same tests then fail because native failure output is erased. This is a failure-evidence control, not a claim about executing Symfony or Mago itself. `proof.json` binds source, mutant and retained log hashes. Full fast qualification executed 114 native unittest identities successfully through `bin/dev test` in 8.78 seconds.
