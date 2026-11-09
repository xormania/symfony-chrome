import { test, expect } from './guards.mjs';

test('real input changes state without creating a request', async ({ page }) => {
    await page.goto('/_ci/browser');
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
    { kind: 'csp', inject: (page) => page.evaluate(() => { const script = document.createElement('script'); script.textContent = 'window.contractForbidden = true'; document.body.append(script); }), matches: (row) => row.kind === 'csp' && row.message.startsWith('script-src') },
];

for (const control of controls) {
    test(`guard detects deliberate ${control.kind} fault`, async ({ page, guard }) => {
        await page.goto('/_ci/browser');
        guard.allow(control.matches);
        // Browsers also log transport/CSP enforcement to console. Scope those allowances
        // to this exact fixture endpoint/directive; the target detector is asserted below.
        if (control.kind === 'http') guard.allow((row) => row.kind === 'console' && row.message === 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)' && row.url.endsWith('/_ci/fault'));
        if (control.kind === 'request') guard.allow((row) => row.kind === 'console' && row.message === 'Failed to load resource: net::ERR_FAILED' && row.url.endsWith('/_ci/aborted'));
        if (control.kind === 'csp') guard.allow((row) => row.kind === 'console' && row.message.startsWith('Executing inline script violates the following Content Security Policy directive') && row.message.includes("script-src 'self'") && row.url === page.url());
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
        await expect.poll(() => guard.issues.filter(control.matches).length).toBeGreaterThan(0);
        if (control.kind === 'csp') expect(await page.evaluate(() => window.contractForbidden)).toBeUndefined();
    });
}
