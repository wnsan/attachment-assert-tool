import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  reporter: [['list'], ['html', { open: 'never', outputFolder: '../../playwright-report' }]],
  outputDir: '../../test-results/node',
  use: { baseURL: 'http://127.0.0.1:4321', browserName: 'chromium' },
  webServer: { command: 'node ../server.js', url: 'http://127.0.0.1:4321', reuseExistingServer: !process.env.CI },
});
