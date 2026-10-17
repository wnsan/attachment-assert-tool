import { test } from '@playwright/test';
// In your project:  import { expect, compareAttachment } from 'attachment-assert/playwright';
import { expect, compareAttachment, assertAttachment } from '../../js/playwright';

const TEMPLATE = 'examples/templates/invoice'; // relative to the folder you run `npx playwright test` from

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('downloaded invoice matches the template', async ({ page }) => {
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('#dl-same')]);
  await expect(download).toMatchAttachment(TEMPLATE);
});

test('changed total is detected', async ({ page }) => {
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('#dl-changed')]);
  await expect(download).not.toMatchAttachment(TEMPLATE);
  await expect(download).toMatchAttachment(TEMPLATE, { only: ['header', 'header p2'] });

  const report = await compareAttachment(download, TEMPLATE);
  expect(report.passed).toBe(false);
  expect(report.results.filter(r => r.status !== 'pass').map(r => r.name)).toEqual(['total']);
  await expect(assertAttachment(download, TEMPLATE)).rejects.toThrow(/total/);
});

test('tolerance options and Buffer input', async ({ page }) => {
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('#dl-changed')]);
  const fs = await import('fs');
  const buf = fs.readFileSync(await download.path());
  await expect(buf).toMatchAttachment(TEMPLATE, { only: 'total', maxDiffPercent: 50 });
});
