# Pinned upstream checker schema qualification

Source: xorder `b8efe93f5b57587c1c48f4a579b9d38de37ff871`,
`scripts/xorder/downstream.py` and `scripts/release_groups.py`.

The ordinary online `check` path exited 2 with a freshness-date error. Its
`load_policy` captures `now` before acquisition; `fetch_snapshot` creates a
later receipt, then `load_policy` rejects `fetched > now`. The raw result is
`upstream-online-red.json`.

The project wrapper uses the upstream supported two-command route:

```sh
python3 -B /path/to/pinned/xorder/scripts/xorder/downstream.py fetch --output policy.json
python3 -B /path/to/pinned/xorder/scripts/xorder/downstream.py check --lock xorder-support.lock.json --image php-base=SELECTED_PARENT --policy-file policy.json
```

Schema qualification used `--actual upstream-observation-fixture.json` rather
than Docker: that fixture records independently queried registry metadata and
is not a claim about a selected or running Docker workload. The raw successful
response is `upstream-snapshot-green.json`; it confirms the expected `ok` and
`observed` fields. The normal project wrapper uses `--image`, so the upstream
checker itself inspects the actual engine's RepoDigests and platform.

The policy snapshot is freshly fetched for an ordinary invocation. An explicitly
supplied snapshot remains subject to upstream freshness and integrity validation.
