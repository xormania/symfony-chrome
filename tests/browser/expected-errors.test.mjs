import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { cspCompanionAllowed } from './expected-errors.mjs';

const documentURL = 'http://127.0.0.1:8000/_ci/browser';
const scriptText = 'window.contractForbidden = true';
// Native Chrome 157 output from the hosted browser fault control. This literal
// is independent of the classifier's message construction.
const message = "Executing inline script violates the following Content Security Policy directive 'script-src 'self''. Either the 'unsafe-inline' keyword, a hash ('sha256-nJkmG+zggsUzCIx8lteOr3Z7UIAGgT5GCc9Jaff6WyE='), or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.";
const issue = { kind: 'console', message, url: '' };
const violation = { kind: 'csp', document: documentURL, message: 'script-src-elem', blocked: 'inline', disposition: 'enforce' };
const allowed = (candidate = issue, events = [violation], source = scriptText) =>
    cspCompanionAllowed(candidate, events, documentURL, source);

test('recorded CSP companion permits empty native console location only with its enforced event', () => {
    assert.equal(createHash('sha256').update(scriptText).digest('base64'), 'nJkmG+zggsUzCIx8lteOr3Z7UIAGgT5GCc9Jaff6WyE=');
    assert.equal(allowed(), true);
    assert.equal(allowed({ ...issue, url: documentURL }), true);
});

test('lookalike console messages and another script hash remain unexpected', () => {
    for (const changed of [message + ' unrelated', 'unrelated contract csp: Content Security Policy script-src',
        message.replace('nJkmG+zggsUzCIx8lteOr3Z7UIAGgT5GCc9Jaff6WyE=', 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=')]) {
        assert.equal(allowed({ ...issue, message: changed }), false, changed);
    }
    assert.equal(allowed(issue, [violation], scriptText + ';'), false);
    assert.equal(allowed({ ...issue, kind: 'page' }), false);
});

test('an exact CSP message at another console location remains unexpected', () => {
    for (const url of ['https://unrelated.invalid/', documentURL + '?other-document', undefined]) {
        assert.equal(allowed({ ...issue, url }), false, String(url));
    }
});

test('independent violation evidence must match document directive effect and enforcement', () => {
    assert.equal(allowed(issue, []), false);
    const mutations = [
        { kind: 'console' }, { document: documentURL + '?other-document' },
        { message: 'default-src' }, { message: 'script-src' },
        { blocked: 'https://unrelated.invalid/script.js' }, { disposition: 'report' },
        { disposition: undefined },
    ];
    for (const mutation of mutations) {
        assert.equal(allowed(issue, [{ ...violation, ...mutation }]), false, JSON.stringify(mutation));
    }
});
