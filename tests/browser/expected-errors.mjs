import { createHash } from 'node:crypto';

/** Exact known Chromium diagnostic plus its independent native CSP event. */
export function cspCompanionAllowed(issue, violations, documentURL, scriptText) {
    const hash = createHash('sha256').update(scriptText, 'utf8').digest('base64');
    const expected = `Executing inline script violates the following Content Security Policy directive 'script-src 'self''. Either the 'unsafe-inline' keyword, a hash ('sha256-${hash}'), or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.`;
    return issue.kind === 'console'
        && issue.message === expected
        && (issue.url === '' || issue.url === documentURL)
        && violations.some((row) => row.kind === 'csp'
            && row.document === documentURL
            && row.message === 'script-src-elem'
            && row.blocked === 'inline'
            && row.disposition === 'enforce');
}
