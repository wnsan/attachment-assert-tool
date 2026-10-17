'use strict';
// Custom matcher for @playwright/test:  await expect(download).toMatchAttachment('templates/invoice')
const path = require('path');
const { compareAttachment } = require('./index');

let counter = 0;

function testInfo() {
  try { return require('@playwright/test').test.info(); } catch (_) { return null; }
}

async function attachArtifacts(info, report, all) {
  if (!info) return;
  const label = `attachment-assert ${report.template}`;
  await info.attach(`${label} report.html`, { path: report.reportHtml, contentType: 'text/html' });
  for (const r of report.results) {
    if (!all && r.status === 'pass') continue;
    for (const kind of ['reference', 'candidate', 'diff']) {
      if (r.images && r.images[kind]) {
        await info.attach(`${label} ${r.name} ${kind}`, { path: path.join(report.outDir, r.images[kind]), contentType: 'image/png' });
      }
    }
  }
}

const attachmentMatchers = {
  /**
   * @param received Download | Buffer | file path | Page | Locator
   * @param template template folder (relative to cwd or options.templatesDir)
   */
  async toMatchAttachment(received, template, options = {}) {
    const name = 'toMatchAttachment';
    const info = testInfo();
    const opts = { ...options };
    if (!opts.outDir && info) {
      opts.outDir = info.outputPath('attachment-assert', `${String(++counter).padStart(2, '0')}-${path.basename(template)}`);
    }
    let report;
    try {
      report = await compareAttachment(received, template, opts);
    } catch (e) {
      return { name, pass: this.isNot, message: () => `${name}: ${e.message}` };
    }
    await attachArtifacts(info, report, options.attachAll);
    const pass = report.passed;
    const message = () => this.isNot
      ? `expected ${report.candidate} NOT to match template ${report.template}, but all regions match\n  report: ${report.reportHtml}`
      : `${report.summary}\n  report: ${report.reportHtml}`;
    return { name, pass, message, expected: template, actual: report.counts };
  },
};

let extendedExpect;
function getExpect() {
  if (!extendedExpect) extendedExpect = require('@playwright/test').expect.extend(attachmentMatchers);
  return extendedExpect;
}

module.exports = {
  attachmentMatchers,
  get expect() { return getExpect(); },
  compareAttachment,
  assertAttachment: require('./index').assertAttachment,
};
