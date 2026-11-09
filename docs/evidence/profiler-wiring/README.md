# Profiler fixture wiring: native red/green evidence

The first hosted browser/tooling run failed during fixture `cache:clear`, before
any provider check. Symfony 8.1.11 exposes the named `profiler` service but does
not supply the class autowiring alias used by the test-only controller.

`proof.json` records a focused native PHP/Symfony reproduction. The same
`qualify.php` script loads an existing installed dependency tree, registers the
supplied disposable application's App classes, boots its actual kernel and
handles a marker request through the real controller/router. It does not mock
DI or manufacture the controller response.

- Parent controller: compilation fails with the exact hosted missing-service
  error (exit 255).
- Fixed controller: `#[Autowire(service: 'profiler')]` supplies the named service;
  the real kernel returns 200, the exact marker and a profiler response token
  (exit 0).

Controller content hashes bind the two subjects. Logs replace absolute workspace
and dependency paths with named placeholders; the response token is synthetic
fixture evidence. This proves the constructor-wiring fix, not browser, MCP,
Docker or listening-network behavior.

To repeat with an installed compatible dependency tree, prepare two disposable
copies of the locked integration fixture containing the test-only services,
routes and controller. Use the parent controller (before explicit service
injection) in one and the fixed controller in the other, with the hashes recorded
here. Run the identical script for each copy:

```sh
php qualify.php /absolute/disposable/app /absolute/installed/vendor/autoload.php
```

The script redirects only the App class map to the supplied application. Its
configuration/cache belong to that disposable copy. The dependency tree is
read-only input. Ordinary required browser/tooling suites continue to compile
this fixture on each run, so removing the explicit service injection causes
those existing integration checks to fail again.
