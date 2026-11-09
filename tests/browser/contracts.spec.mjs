import { test, expect } from './guards.mjs';
import { cspCompanionAllowed } from './expected-errors.mjs';

const forbiddenScript = 'window.contractForbidden = true';

test('real input changes state without creating a request', async ({ page, baseURL }) => {
    // Chrome can request the icon after the document's load event. Finish this
    // known initial resource before observing requests caused by the action.
    const iconResponse = page.waitForResponse((response) => response.url() === new URL('/_ci/icon.svg', baseURL).href);
    await page.goto('/_ci/browser');
    const icon = await iconResponse;
    expect(icon.status()).toBe(200);
    expect(await icon.finished()).toBeNull();
    const requests = [];
    page.on('request', (request) => requests.push(request.url()));
    await page.getByRole('button', { name: 'Local action' }).click();
    await expect(page.locator('#count')).toHaveText('1');
    expect(requests).toEqual([]);
});

test('clean navigation keeps all runtime guards quiet', async ({ page, guard }) => {
    await page.goto('/_ci/browser');
    await expect(page.getByRole('heading')).toHaveText('Symfony Chrome contract');
    expect(guard.issues).toEqual([]);
});

const controls = [
    { kind: 'console', inject: (page) => page.evaluate(() => console.error('contract-console-fault')), matches: (row) => row.kind === 'console' && row.message === 'contract-console-fault' },
    { kind: 'page', inject: (page) => page.evaluate(() => { setTimeout(() => { throw new Error('contract-page-fault'); }, 0); }), matches: (row) => row.kind === 'page' && row.message === 'contract-page-fault' },
    { kind: 'http', inject: (page) => page.evaluate(() => fetch('/_ci/fault')), matches: (row) => row.kind === 'http' && row.status === 503 && row.message.endsWith('/_ci/fault') },
    { kind: 'request', inject: async (page) => { await page.route('**/_ci/aborted', (route) => route.abort()); await page.evaluate(() => fetch('/_ci/aborted').catch(() => {})); }, matches: (row) => row.kind === 'request' && row.message.endsWith('/_ci/aborted') },
    { kind: 'csp', inject: (page) => page.evaluate((source) => { const script = document.createElement('script'); script.textContent = source; document.body.append(script); }, forbiddenScript), matches: (row) => row.kind === 'csp' && row.message === 'script-src-elem' && row.blocked === 'inline' && row.disposition === 'enforce' },
];

for (const control of controls) {
    test(`guard detects deliberate ${control.kind} fault`, async ({ page, guard }) => {
        await page.goto('/_ci/browser');
        const matches = (row) => control.matches(row) && (control.kind !== 'csp' || row.document === page.url());
        guard.allow(matches);
        // Browsers also log transport/CSP enforcement to console. Scope those allowances
        // to this exact fixture endpoint/directive; the target detector is asserted below.
        if (control.kind === 'http') guard.allow((row) => row.kind === 'console' && row.message === 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)' && row.url.endsWith('/_ci/fault'));
        if (control.kind === 'request') guard.allow((row) => row.kind === 'console' && row.message === 'Failed to load resource: net::ERR_FAILED' && row.url.endsWith('/_ci/aborted'));
        if (control.kind === 'csp') guard.allow((row) => cspCompanionAllowed(row, guard.issues, page.url(), forbiddenScript));
        const fragments = { http: '503', request: 'ERR_FAILED', csp: 'Content Security Policy script-src' };
        if (fragments[control.kind]) {
            const sentinel = `unrelated contract ${control.kind}: ${fragments[control.kind]}`;
            await page.evaluate((message) => console.error(message), sentinel);
            await expect.poll(() => guard.unexpected().some((row) => row.kind === 'console' && row.message === sentinel)).toBe(true);
            const observed = guard.unexpected().find((row) => row.kind === 'console' && row.message === sentinel);
            // Only this already-observed control message is allowed after proving
            // the companion exception did not hide it. Later lookalikes still fail.
            guard.allow((row) => row === observed);
        }
        await control.inject(page);
        await expect.poll(() => guard.issues.filter(matches).length).toBeGreaterThan(0);
        if (control.kind === 'csp') expect(await page.evaluate(() => window.contractForbidden)).toBeUndefined();
    });
}
