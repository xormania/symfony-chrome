import { test as base, expect } from '@playwright/test';

export class BrowserGuard {
    constructor(page) {
        this.page = page;
        this.issues = [];
        this.allowed = [];
    }

    async install() {
        this.page.on('console', (message) => {
            if (message.type() === 'error') this.issues.push({ kind: 'console', message: message.text(), url: message.location().url });
        });
        this.page.on('pageerror', (error) => this.issues.push({ kind: 'page', message: error.message }));
        this.page.on('requestfailed', (request) => this.issues.push({ kind: 'request', message: request.url() }));
        this.page.on('response', (response) => {
            if (response.status() >= 400) this.issues.push({ kind: 'http', status: response.status(), message: response.url() });
        });
        await this.page.exposeBinding('__contractCsp', (_, value) => this.issues.push({ kind: 'csp', ...value }));
        await this.page.addInitScript(() => document.addEventListener('securitypolicyviolation', (event) => {
            window.__contractCsp({ message: event.effectiveDirective, blocked: event.blockedURI,
                document: event.documentURI, source: event.sourceFile, policy: event.originalPolicy, disposition: event.disposition });
        }, true));
    }

    allow(predicate) { this.allowed.push(predicate); }
    unexpected() { return this.issues.filter((row) => !this.allowed.some((predicate) => predicate(row))); }
}

export const test = base.extend({
    guard: [async ({ page, baseURL }, use) => {
        await page.route('**/*', async (route) => {
            if (new URL(route.request().url()).origin !== new URL(baseURL).origin) return route.abort('blockedbyclient');
            return route.continue();
        });
        const guard = new BrowserGuard(page);
        await guard.install();
        await use(guard);
        expect(guard.unexpected(), 'Unexpected console/page/network/CSP faults').toEqual([]);
    }, { auto: true }],
});
export { expect };
