# Package test runtime

`./bin/dev test --suite package` executes the same package script locally and in
CI. With PHP 8.4 and Composer available, it uses those native tools and records
their results. CI prepares the native runtime explicitly.

When PHP or Composer is missing, the package script uses Docker. It first runs
the existing xorder support preflight against the selected digest-pinned PHP
parent. It then exports the current package-test inputs into a read-only view,
excluding Git metadata, ignored/private state, dependencies and local environment
files. The same script runs inside the image with that view mounted read-only
and evidence mounted writable. Temporary installations and
Composer home live in writable disposable container state. This path needs no
Serena/Rust image build or host PHP installation.

If `DEV_IMAGE` names an already available prepared development image, its actual
filesystem layers must extend the validated parent. Without an explicit DEV_IMAGE selection, the released
parent is used directly. An explicitly selected unavailable image fails clearly. The selected and actual image identities are retained
in `package-runtime.json`. An internal `--native-only` marker prevents recursive
fallback when a selected image lacks a required executable.

The support preflight's records are nested package runtime evidence. They do not
create a second runner attempt or change the package suite's selected checks.
The Docker fallback has mocked invocation and failure controls; actual execution
must be identified separately from those controls in verification reports.

Intentional `--bootstrap-locks` maintenance requires a native PHP/Composer
runtime because it writes reviewed dependency locks back into the checkout.
Ordinary acceptance always installs the existing locks.

Before PHPUnit executes, native `--list-tests-xml` discovery seals class,
method/dataset, and source-file identities and requires the bundle/kernel
contract. Its JUnit result must contain exactly that inventory with passing
assertions. A same-count unrelated passing test cannot replace the contract.
