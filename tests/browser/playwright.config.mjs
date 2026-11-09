import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const output = resolve(process.env.CONTRACT_RESULTS ?? 'artifacts/browser-native');
export default defineConfig({
    testDir: '.',
    testMatch: '*.spec.mjs',
    forbidOnly: true,
    retries: 0,
    workers: 1,
    timeout: 30_000,
    outputDir: `${output}/traces`,
    reporter: [['list'], ['json', { outputFile: `${output}/results.json` }]],
    use: {
        baseURL: process.env.CONTRACT_URL ?? 'http://127.0.0.1:8000',
        browserName: 'chromium',
        launchOptions: {
            executablePath: process.env.CHROME_PATH,
            args: ['--no-sandbox'],
        },
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
    },
});
