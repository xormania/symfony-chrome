# Released-parent support wrapper controls

The same seven tests were executed against controlled regressions and the fixed wrapper.

| Control | Expected red result | Raw output |
| --- | --- | --- |
| Remove support-lock/configured-parent identity comparison in a disposable copy | Unrelated repository is accepted; expected rejection is missing | `red.log` |
| Wrapper from commit `027f3b4a6cbaece6726939edb272bc4ad18514db` | Failed fetch leaves a partial persistent checkout | `acquisition-red.log` |
| Wrapper from commit `9796ed6` | Mismatched Dockerfile parent accepted; successful leader leaves a background child running | `binding-cleanup-red.log` |
| Current wrapper | All seven controls pass | `green.log` |

Run the healthy cases with:

```sh
python3 -m unittest discover -s tests/fast -p test_support_contract.py -v
```

For red controls, copy the current test file into a disposable repository root,
keeping its relative path. Supply the named parent version of `tools/testing/support.py`
with `git show`, or remove the named identity comparison in that disposable copy.
Run the identical command. Only children created by the process test are signalled.

These records establish wrapper fault detection. They do not claim a Docker image
was pulled or that the support checker observed an actual Docker workload.
