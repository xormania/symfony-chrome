# Symfony–Chrome integration: background, active examples, and research

**Date:** 2026-11-07, America/New_York  
**Owner:** xor  
**Status:** Source-backed research and proposed experiments; no integrated package or benchmark was executed for this report.  
**Companion:** [Scope and specification](Symfony-Chrome-Scope-Specification-2026-11-07.md)

## 1. What this research establishes

There are usable upstream foundations for a reusable Symfony–Chrome package:

- Chrome DevTools MCP supplies agent-facing browser control and diagnostics.
- Symfony supplies MCP integration, Profiler access, reusable bundles, and browser-asset integration.
- Chrome browser APIs can support application features through a browser SDK.
- WebMCP and Chrome's third-party developer tools provide separate ways to expose application actions and development observations.
- Existing browser drivers and maintained examples can support the first integration without a new browser protocol implementation.

**Inference:** the valuable work is the Symfony integration: lifecycle handling, operation contracts, request/component correlation, useful diagnostics, and reproducible installation. No single inspected example establishes the whole proposed product.

Evidence labels used below:

| Label | Meaning |
| --- | --- |
| **Verified source** | Documentation, code, release metadata, or a file was retrieved and inspected. |
| **Page retrieved** | The public page's content was retrieved; this does not establish execution of its browser APIs. |
| **Recovered history** | Earlier conversation evidence; distinguishes owner goals from assistant proposals. |
| **Inference / proposal** | A design judgment or experiment derived from the evidence. |
| **Not established** | A runtime result, compatibility claim, or missing artifact still needs verification. |

No new package was installed, no browser model was downloaded, no demo form was submitted, and no performance or UX-conformance result was generated. The recipes below are reproduction instructions for implementation work, not completed experiments.

## 2. Recovered background and current scope

### May and June 2026

The earlier discussions were recovered in this conversation. Dates here use broad periods because the source timestamps straddle midnight in New York.

| Period | Owner direction recovered | Historical proposals, not current implementation facts |
| --- | --- | --- |
| May 8–9 | Explore Chrome DevTools with Symfony Mate and application evidence; development and production interests were both present. | Separate Chrome DevTools MCP and Symfony tools, correlate their observations; a Mate extension and evidence contracts. |
| June 1–2 | A Symfony-community package/SDK under MinSpec with no MinSpec dependency; generic Chrome integration and local AI features, including summarizing/proofreading; extensible Symfony 8+ and TypeScript integration. | “Browser AI for Symfony”; JS SDK, Chrome AI/WebMCP integration, Mate/profiler support, and later `@minspec/chrome-ai`, `minspec/chrome-ai-bundle`, and `minspec/ux-chrome-ai`. |
| June 2 | Acceptance of preparing Agently workstream material. | Conversation describes `minspec-chrome-ai-agently-workstreams.zip`, with architecture/package/milestone/testing material. The archive itself was not recovered in this research. |

The proposed `minspec/browser-ai-for-symfony` repository was not established as an accessible implementation. A failed public repository lookup does not prove that private or differently named work does not exist.

**Carry forward:** reusable Symfony integration; browser SDK; Chrome AI and developer-tool capabilities; MCP access; eventual production use. Historical v0 exclusions and old package names are source material, not constraints on the current product.

### October and November continuity

A separate October report considered Rust/Go browser tracing and CUE compatibility checks. Its useful architectural lesson is that an API claim and a passing wrapper test do not establish faithful protocol behavior. It does not select Rust, Go, or CUE for this Symfony package. This is historical context, not a fresh maintenance assessment of those libraries. [H1]

The current UXor quality plan was read at **revision 3**, modified November 6 New York time. It already defines an adoption/repair loop, a dialog profile, explicit requirement IDs, and a limited first slice. In particular, `QP-DIALOG / 0.1-draft.2` includes QD-03 dismissal/focus return, QD-06 Live updates, QD-07 asynchronous outcomes, and QD-12 runtime integration. Reuse the current selected profile instead of inventing a second modal standard. The document's own defaults remain overridable. [H2]

**Context access:** H1/H2 links are owner-accessible document references. Their relevant conclusions are included here so an implementation agent does not need private chat access to understand this package. Place the two new documents in the eventual repository when work begins.

## 3. Inspected versions and compatibility findings

| Item | Verified source snapshot | Implication |
| --- | --- | --- |
| Chrome DevTools MCP | Release **1.12.0**, published **2026-10-22**. Release-specific configuration and tool reference inspected. [R01–R03] | Start evaluation from a known release, not an unqualified `latest` configuration. |
| Symfony AI | Release **1.0.0-BETA1**, published **2026-10-26**; MCP Bundle manifest and Mate README inspected at that tag. [R04–R06] | Pre-release candidate is explicit. Passing dependency resolution/installation remains to be demonstrated. |
| Google WebMCP tools/examples | `618625436805737e17a15950c151476a05076dd4`, **2026-11-06**. [R07] | Active upstream work; snapshot the demo and any polyfill used. |
| Google browser-AI examples | `fc5774de33c6e0c33ddf3b779522a10529de8d26`, **2026-11-04**. [R08] | Current source examples exist; repository activity is not a device/API compatibility result. |
| UXor default branch | `6991671805dba5d80c65d1da390f24474f25beff`, latest inspected commit dated **2026-11-05**. Demo declares PHP **>=8.4**, Symfony **8.1.***, Mate and its Symfony extension **^0.14**. [R09] | Sensible first consumer baseline. Refresh the actual development branch/lock before implementation. |
| Chrome PDF Symfony bundle | `0d3d24e84b562b656c5e10fb72d5c4a997be5cdf`, **2026-01-12**, Symfony 8 change. [R10] | Concrete narrow Symfony/Chrome integration; not evidence of a complete diagnostic SDK. |

Dates above are repository/release observations, not support guarantees.

### Changes that matter since the earlier investigation

**Mate transport:** the inspected 1.0.0-BETA1 README describes command-based tools/resources and development-only use. Current extension docs provide profile lookup and per-collector resources, read from stored data. Do not reuse the May-era `mate serve` assumption without checking the actual installed version. The package's MCP interface can use the separate Symfony MCP Bundle. [R06] [R11] [R12]

**Chrome MCP execution:** 1.12.0 records parallel execution improvements for independent calls and different pages. This is a concrete upstream capability to evaluate, not permission to concurrently mutate the same page or proof of an application speedup. [R01]

**Connection-specific capabilities:** the pinned configuration supports attachment to an existing Chrome session, but some extension/PWA tools require a pipe-launched connection. The WebMCP tool category has its own Chrome/feature requirements. A capability manifest must include connection mode. [R02]

**WebMCP evolution:** Chrome's overview describes an origin trial and imperative/declarative APIs. The pinned MCP release's WebMCP category requires Chrome 150+ with the documented WebMCP feature enabled. These are different integration requirements; a browser meeting the origin-trial minimum is not automatically a tested DevTools-MCP combination. Current Google examples use `document.modelContext` and may install a polyfill. [R02] [R13] [R14]

## 4. Upstream capabilities and what to reuse

### Browser control and inspection

Chrome DevTools MCP's release-specific tool reference exposes input/navigation, requests, console/snapshots, traces, and heap diagnostics. Its page-scoped identifiers and request IDs are provider identifiers; the package should retain their origin and validity rather than treating them as permanent application identity. [R03]

**Proposed use:** retain upstream general inspection and add Symfony-aware operations/results. Start with a bounded scenario and narrow evidence. Full heap snapshots, continuous screencasts, and broad audits are diagnostic options when the question requires them, not the default payload.

For direct execution, Puppeteer can connect to an existing browser. Playwright also offers CDP attachment, but its documentation identifies lower fidelity than its own protocol connection and notes launch-argument differences. Therefore “both clients can attach” is insufficient evidence that the existing test suite behaves identically. [R15] [R16]

Chrome PHP supplies a PHP control path, persistent connection examples, screenshots/PDFs, and direct CDP messages. It is a candidate adapter when a PHP-native execution path is useful; selecting it requires the same scenario/evidence experiment. [R17]

### Application-specific developer tools

Chrome's experimental third-party tool interface discovers functions supplied by the inspected page through `devtoolstooldiscovery`. Tools include schemas and execution functions; the MCP release exposes discovery and invocation operations. [R18] [R03]

**Proposed use:** expose bounded component-state observations from a Symfony development asset. Verify rediscovery after navigation and cleanup after component removal. A stable package observation schema should not depend on scraping an Inspector panel's presentation.

Symfony UX Inspector is a relevant experimental reference for Stimulus, Live Component, and Turbo inspection. Its documentation describes optional connection to the Stimulus application, state/relationship views, and activity. It also explains that Stimulus connect/disconnect callbacks are not DOM events. No public stable MCP export API was established in the inspected Inspector documentation. [R19]

### Symfony services, packages, and browser assets

Symfony's MCP Bundle can host tools/resources and connect to external servers. Its cookbook and tagged MCP toolbox example demonstrate registration and consuming a stdio server; the latter includes an LLM agent, which is unnecessary for deterministic tool invocation. [R12] [R20] [R21]

The reusable-bundle guidance covers explicit service definitions, configuration, extension, and packaging. The UX-bundle guide describes shipping controllers/JS through Composer and supporting AssetMapper. This supports a normal Symfony installation experience while retaining a separate TypeScript source SDK. [R22] [R23]

Profiler provides an exact request-token lookup. A browser's response `X-Debug-Token` can identify the corresponding profile; its collectors then provide server evidence. This joins a response to recorded server work, not to every later browser paint or asynchronous job. [R24]

### Browser AI and WebMCP

Chrome's API catalog includes Prompt, Summarizer, writing/proofreading, translation, and language detection at different availability stages. API presence, device eligibility, requested options/languages, model readiness, and user activation are distinct checks. Early-access membership does not itself establish that a particular browser/device can execute an API. [R25] [R26]

The Summarizer documentation supplies a practical first adapter: availability detection, initialization/download progress, creation, and summarization. Use the same options for detection and execution. Its result is model output, not an authoritative application decision. [R27]

WebMCP exposes application actions from a page through JavaScript or annotated forms. Native support and a JS polyfill are distinct tested implementations. It can improve semantic agent interaction, while keyboard, pointer, focus, and accessibility behavior still need independent checks. [R13]

## 5. Active examples and reuse assessment

“Active” below means an available maintained source/release or a retrieved demonstration, with the observation stated. It does not imply every example has been executed or is production-ready.

| Example | What was checked | Reusable lesson / limit |
| --- | --- | --- |
| **Chrome DevTools MCP 1.12.0** — [release](https://github.com/ChromeDevTools/chrome-devtools-mcp/releases/tag/chrome-devtools-mcp-v1.12.0) | Release metadata, configuration, and tool reference. | Upstream browser diagnostics/control. Package-specific speed and session interoperability remain untested. |
| **Le Petit Bistro** — [live demo](https://googlechromelabs.github.io/webmcp-tools/demos/french-bistro/) · [pinned README](https://github.com/GoogleChromeLabs/webmcp-tools/blob/618625436805737e17a15950c151476a05076dd4/demos/french-bistro/README.md) | Source instructions and public form content retrieved; no submission. | Declarative forms, validation, and a cross-document variant. Imports polyfills; success is not automatically native WebMCP evidence. |
| **WebMCP Evals** — [pinned source](https://github.com/GoogleChromeLabs/webmcp-tools/tree/618625436805737e17a15950c151476a05076dd4/webmcp-evals) | README and documented commands inspected. | Deterministic `smoke` mode runs expected calls without an LLM; model-driven modes answer a different question. Not a substitute for user-input UX tests. |
| **Summarization playground** — [live demo](https://chrome.dev/web-ai-demos/summarization-api-playground/) · [pinned implementation](https://github.com/GoogleChromeLabs/web-ai-demos/blob/fc5774de33c6e0c33ddf3b779522a10529de8d26/summarization-api-playground/src/main.ts) | Public UI and TypeScript inspected; no model inference. | Options-aware readiness, user activation, progress, session destruction, text output. Adapter still needs navigation/error cleanup and stale-result checks. |
| **Google browser-AI collection** — [pinned catalog](https://github.com/GoogleChromeLabs/web-ai-demos/tree/fc5774de33c6e0c33ddf3b779522a10529de8d26) | README and repository activity inspected. | Includes Prompt and weather examples. The catalog also includes other client-side model stacks; do not label all examples Chrome built-in AI. |
| **Symfony MCP cookbook and toolbox example** — [cookbook](https://ai.symfony.com/cookbook/build-an-mcp-server) · [tagged code](https://github.com/symfony/ai/blob/v1.0.0-BETA1/examples/toolbox/mcp.php) | Documentation and PHP source inspected. | Existing PHP MCP integration; no reason to invent its transport or discovery layer. |
| **Symfony UX Inspector** — [documentation](https://symfony.com/bundles/ux-inspector) | Current documentation inspected. | Closest framework-specific inspection reference; experimental, and not verified as a ready-made package MCP adapter. |
| **Chrome PHP** — [source](https://github.com/chrome-php/chrome) | README control/attachment examples and license inspected. | Direct PHP browser operations and persistent attachment. Container/worker behavior must be tested. |
| **ChromePdfBundle** — [source](https://github.com/sanderdlm/chrome-pdf-bundle) | README and latest default-branch commit inspected. | Existing Symfony services around Chrome PHP. Reuse/reference for rendering; narrower than this project's integration scope. |
| **UXor dialog workflow** — [repository snapshot](https://github.com/xormania/uxor/tree/6991671805dba5d80c65d1da390f24474f25beff) | Demo dependencies and current owner quality-plan profile read. | First consumer and requirement vocabulary. No new workflow execution or CI audit was performed here. |

The WebMCP tools repository identifies itself as an experimental project rather than an officially supported Google product. Its Evals README distinguishes schema-only, live-browser, deterministic smoke, and simulated-conversation modes. Support differs by backend/mode; verify the selected path instead of assuming every listed backend executes every mode. [R07] [R28]

## 6. Reproduction recipes for the implementation agent

These are proposed bounded experiments. Preserve actual results, including failed setup. A public demo URL can change independently of its pinned source; host the pinned example for repeatable comparisons.

### E1 — Existing Chrome session to exact Symfony profile

**Prerequisites:** a running Symfony development fixture that collects profiles, an eligible Chrome installation with remote debugging explicitly enabled, an MCP client, and Node prerequisites for the pinned server.

Example client configuration based on the inspected release:

```json
{
  "mcpServers": {
    "chrome": {
      "command": "npx",
      "args": [
        "--yes",
        "chrome-devtools-mcp@1.12.0",
        "--autoConnect",
        "--categoryExperimentalThirdParty",
        "--no-usage-statistics",
        "--no-performance-crux"
      ]
    }
  }
}
```

The last two flags make this example's external telemetry behavior explicit. They do not establish general isolation. Connection setup may require Chrome's user confirmation. Match the selected channel/profile. [R02]

**Procedure:** list pages; select the fixture; perform one Live validation action; inspect the relevant response headers; use its profile token to retrieve the server profile and one relevant collector. Repeat with two overlapping requests and with Profiler disabled.

**Capture:** browser/page/request identities, action/attempt ID, token, profile lookup result, component focus/state, elapsed collection time, and omissions. Never join to “the latest profile” as a substitute for the response token.

**Pass meaning:** correct request/profile association and useful failure reporting. This experiment does not yet establish a generic scenario runner or a UX improvement.

### E2 — Page-provided development observation

Using the documented third-party discovery event, register one read-only observation function for the fixture component. Return component identity, selected state, and source mapping if actually available.

Discover and call it through `list_3p_developer_tools` / `execute_3p_developer_tool`. Repeat after Turbo navigation, browser history return, Live replacement, and component removal. Record whether stale instances or duplicate tools remain. [R03] [R18]

**Decision consumed:** whether this upstream discovery path suffices for the first browser-side diagnostics adapter. If not, retain the precise gap before designing another bridge.

### E3 — Browser AI in a Symfony UX fixture

Use the pinned summarizer playground as an API reference. Add a package-owned fixture with text input, a user-invoked action, and preview output.

1. Record API presence and option-specific availability.
2. Exercise user activation and model readiness on an eligible device.
3. Retain a real summary result and initialization timings.
4. Start a delayed request, change input, and navigate away; verify obsolete output cannot update the new view.
5. Repeat with the capability unavailable and with development integrations absent.

Use fixture input without sensitive content. Hardware/model eligibility and first-download time are recorded conditions, not guessed from a Chrome version. The source playground's displayed fallback strings are not evidence that the research environment detected either condition. [R26] [R27] [R29]

### E4 — Deterministic WebMCP evaluation

Inspect the pinned `webmcp-evals` instructions and install/build that checkout's evaluation package. From its `webmcp-evals` directory, the documented command family supports a smoke run such as:

```bash
node dist/bin/webmcp-evals.js smoke \
  --url https://googlechromelabs.github.io/webmcp-tools/demos/pizza-maker/ \
  -e examples/pizza-maker/evals.json
```

This uses a repository example rather than an invented package test file. For repeatability, serve the matching checked-out demo locally and replace the URL. Confirm the source's current browser-launch configuration before executing. [R28]

Then author one equivalent case for the Symfony form fixture. Label native versus polyfilled execution, record input/output validation and final visible state, and test the same task through ordinary browser input separately.

**Pass meaning:** concrete declared operations behave as expected in the recorded mode. It does not prove that an LLM will choose the right tool or that the human UX meets its requirements.

### E5 — Runtime/managed-browser boundary

Run a package-owned browser operation against a fixed fixture page with development dependencies absent. Capture a screenshot or artifact; test timeout/cancellation, borrowed versus owned lifecycle, and two isolated job contexts.

The PHP/worker API should return structured state even if the browser fails. A native/headless Chrome execution test does not prove browser AI support in that environment. [R17] [R30]

**Decision consumed:** whether the selected execution adapter can serve a production job without pulling development diagnostics into its runtime dependency graph.

## 7. Lifecycle and diagnostics findings

| Verified upstream behavior | Integration consequence — proposal |
| --- | --- |
| Stimulus may reconnect the same controller instance; connect can run repeatedly. [R31] | Make registration and cleanup idempotent. Test reconnection, not just initial mount. |
| Turbo exposes cache/render/visit events; before-visit does not cover history navigation. [R32] | Verify history/restoration separately and do not assume one event handles all cleanup. |
| Live's render hooks concern re-rendering, not initial mount; its current docs mark exported `ComponentHooks` types as a 3.6 addition. [R33] | Match code/types to UXor's actual installed UX version; do not copy a newer type import into an older dependency set. |
| Profiler tokens identify stored request evidence. [R24] | Preserve exact joins and missing evidence; browser-only interactions need no invented server record. |
| UX Inspector is experimental and has stated observation limits. [R19] | Reuse public mechanisms where possible; validate any source-level reuse instead of depending on undocumented panel internals. |

**Inference:** the first useful contract is about observable behavior and its evidence. Template annotations can supply identity/source context, while runtime instrumentation supplies events and results. Extending Twig remains a possible ergonomic improvement; a compiler customization is not needed to test this hypothesis.

A selected component's success cannot be inferred from its own internal “ready” flag alone. Pair framework observations with independent DOM/focus/input/response checks. Keep model-generated explanations separate from the observed event sequence.

## 8. Performance questions and bounded research

No speed claim was measured. The following experiments should precede latency gates:

| Question | Minimum useful experiment | Result to retain |
| --- | --- | --- |
| Does session reuse help? | Compare cold startup with repeated operations in an existing session. | Startup, setup, operation, and cleanup times separately. |
| Do compact operations shorten agent work? | One manual investigation and an assisted investigation of the same case. | Time/tool calls to a supported diagnosis, evidence completeness, learning-order caveat. |
| Is the interaction metric repeatable? | Thirty repetitions on one designated runner, with raw samples and consistent settings. | Spread, failures, outliers, and whether a gate is defensible. |
| Does tracing perturb the result? | Matched runs with the chosen instrumentation off/on. | Overhead estimate and collection mode in every result. |
| Does browser instrumentation survive reuse? | Repeated Turbo/Live transitions and component removal. | Registrations, listeners/requests observed, stale outputs, and retained resources relevant to the test. |

INP measures interaction responsiveness to the next paint; full asynchronous operation completion is another boundary. Report them separately. A single driver-step timer is not INP, and resource counters alone do not prove absence of memory leaks. [R34]

**Suggested order:** E1 and E2 resolve the development integration; E3 establishes one application-facing API; E4 establishes semantic browser tooling; E5 establishes the managed runtime boundary. Use the scope document's time checkpoints. These are focused questions, not independent research departments.

## 9. Reuse, provenance, and open decisions

The inspected Chrome DevTools MCP, Google WebMCP tools, and Google browser-AI example repositories carry Apache-2.0 licenses. Chrome PHP's inspected license is MIT, and the tagged Symfony MCP Bundle manifest declares MIT. Retain the selected files' notices and inspect any third-party assets/dependencies separately when copying material. This observation does not assign a license to every linked asset or product. [R35]

No complete existing Symfony package covering the entire proposed combination was established by this search. ChromePdfBundle and Symfony's MCP/UX facilities are concrete partial matches. This is a bounded search result, not a claim that no such package exists anywhere.

Open decisions are intentionally small:

- Public package/vendor/repository name.
- The first verified PHP/Symfony/MCP/Chrome/driver tuple.
- Whether existing runner execution plus upstream Chrome MCP is sufficient, or a direct CDP adapter is needed immediately.
- The device used for native browser-AI acceptance.
- The native/polyfill WebMCP support claims to publish.
- The first production operation and its application effect/retry contract.

Do not import the old workstream pack's unavailable details, assume early-access enrollment implies a particular API entitlement, or turn missing information into a permanent restriction. Retrieve/measure the needed fact when its implementation slice consumes it.

## 10. Reference register

All living sources below were inspected during November 7 New York time. Release/commit links preserve the research baseline where available. Numbered references identify factual support; design proposals are labeled in the text.

### Chrome and browser execution

- **R01 — Chrome DevTools MCP 1.12.0 release:** https://github.com/ChromeDevTools/chrome-devtools-mcp/releases/tag/chrome-devtools-mcp-v1.12.0
- **R02 — Pinned configuration:** https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/chrome-devtools-mcp-v1.12.0/docs/configuration.md
- **R03 — Pinned tool reference:** https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/chrome-devtools-mcp-v1.12.0/docs/tool-reference.md
- **R15 — Puppeteer browser management:** https://pptr.dev/guides/browser-management
- **R16 — Playwright CDP attachment:** https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp
- **R17 — Chrome PHP:** https://github.com/chrome-php/chrome
- **R18 — Page-provided developer tools:** https://developer.chrome.com/docs/devtools/agents/use-cases/third-party-tools
- **R30 — Chrome Headless:** https://developer.chrome.com/docs/automation-and-testing/headless
- **R34 — INP:** https://web.dev/articles/inp

### Symfony and UX

- **R04 — Symfony AI 1.0.0-BETA1 release:** https://github.com/symfony/ai/releases/tag/v1.0.0-BETA1
- **R05 — Tagged MCP Bundle dependency manifest:** https://github.com/symfony/ai/blob/v1.0.0-BETA1/src/mcp-bundle/composer.json
- **R06 — Tagged Mate README:** https://github.com/symfony/ai/blob/v1.0.0-BETA1/src/mate/README.md
- **R09 — UXor demo dependencies:** https://github.com/xormania/uxor/blob/6991671805dba5d80c65d1da390f24474f25beff/demo/composer.json
- **R10 — ChromePdfBundle README and January change:** https://github.com/sanderdlm/chrome-pdf-bundle · https://github.com/sanderdlm/chrome-pdf-bundle/commit/0d3d24e84b562b656c5e10fb72d5c4a997be5cdf
- **R11 — Mate extensions and profile resources:** https://symfony.com/doc/current/ai/components/mate/extensions.html
- **R12 — Symfony MCP Bundle:** https://symfony.com/doc/current/ai/bundles/mcp-bundle.html
- **R19 — UX Inspector:** https://symfony.com/bundles/ux-inspector
- **R20 — MCP server cookbook:** https://ai.symfony.com/cookbook/build-an-mcp-server
- **R21 — Tagged MCP toolbox example:** https://github.com/symfony/ai/blob/v1.0.0-BETA1/examples/toolbox/mcp.php
- **R22 — Reusable bundle practices:** https://symfony.com/doc/current/bundles/best_practices.html
- **R23 — UX bundle assets and AssetMapper:** https://symfony.com/doc/current/frontend/create_ux_bundle.html
- **R24 — Profiler:** https://symfony.com/doc/current/profiler.html
- **R31 — Stimulus lifecycle:** https://stimulus.hotwired.dev/reference/lifecycle-callbacks
- **R32 — Turbo events:** https://turbo.hotwired.dev/reference/events
- **R33 — Live Component hooks:** https://symfony.com/bundles/ux-live-component#javascript-component-hooks

### Browser capabilities and examples

- **R07 — WebMCP tools snapshot/activity:** https://github.com/GoogleChromeLabs/webmcp-tools/tree/618625436805737e17a15950c151476a05076dd4 · https://github.com/GoogleChromeLabs/webmcp-tools/commit/618625436805737e17a15950c151476a05076dd4
- **R08 — Browser-AI demos snapshot/activity:** https://github.com/GoogleChromeLabs/web-ai-demos/tree/fc5774de33c6e0c33ddf3b779522a10529de8d26 · https://github.com/GoogleChromeLabs/web-ai-demos/commit/fc5774de33c6e0c33ddf3b779522a10529de8d26
- **R13 — WebMCP overview and trial:** https://developer.chrome.com/docs/ai/webmcp
- **R14 — Bistro source and modes:** https://github.com/GoogleChromeLabs/webmcp-tools/blob/618625436805737e17a15950c151476a05076dd4/demos/french-bistro/README.md
- **R25 — Built-in AI API catalog:** https://developer.chrome.com/docs/ai/built-in-apis
- **R26 — Built-in AI prerequisites:** https://developer.chrome.com/docs/ai/get-started
- **R27 — Summarizer API:** https://developer.chrome.com/docs/ai/summarizer-api
- **R28 — WebMCP Evals:** https://github.com/GoogleChromeLabs/webmcp-tools/blob/618625436805737e17a15950c151476a05076dd4/webmcp-evals/README.md
- **R29 — Summarizer playground implementation:** https://github.com/GoogleChromeLabs/web-ai-demos/blob/fc5774de33c6e0c33ddf3b779522a10529de8d26/summarization-api-playground/src/main.ts
- **R35 — Inspected license sources:** [Chrome MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/chrome-devtools-mcp-v1.12.0/LICENSE), [WebMCP tools](https://github.com/GoogleChromeLabs/webmcp-tools/blob/618625436805737e17a15950c151476a05076dd4/LICENSE), [browser-AI demos](https://github.com/GoogleChromeLabs/web-ai-demos/blob/fc5774de33c6e0c33ddf3b779522a10529de8d26/LICENSE), [Chrome PHP](https://api.github.com/repos/chrome-php/chrome/contents/LICENSE), and the Symfony manifest in R05.

### Owner background documents

- **H1 — Rust/Go browser tracing and contract checking, historical October research:** [rust-go-browser-tracing-contract-checking-2026-10-06.md](https://chatgpt.com/library?file_id=libfile_d2d7f9d11298819197ddebe981c23387&account_id=personal)
- **H2 — Current UXor quality plan, revision 3 inspected:** [UXor-Components-Recipes-Blocks-Quality-Research-Plan-2026-11-06.md](https://chatgpt.com/library?file_id=libfile_050abd6fbef481919ed3f53a06fb735a&account_id=personal)

The May/June history is recovered conversation context, not a publicly verifiable implementation record. The capability goals relevant to this package have been restated in §2; unavailable archive content is not used as authority.

