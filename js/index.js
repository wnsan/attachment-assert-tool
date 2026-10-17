'use strict';
// Node wrapper around the bundled Python engine (same renderer => same pixels as the UI/CLI).
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PKG_ROOT = path.resolve(__dirname, '..');
const REQUIREMENTS = path.join(PKG_ROOT, 'requirements.txt');
const PROBE = 'import numpy, PIL, pypdfium2';

let cachedPython = null;

function pythonEnv() {
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' };
  env.PYTHONPATH = PKG_ROOT + (env.PYTHONPATH ? path.delimiter + env.PYTHONPATH : '');
  return env;
}

/** Resolve the Python interpreter: options.python, $ATTACHMENT_ASSERT_PYTHON, then py -3 / python3 / python. */
function findPython(explicit) {
  const wanted = explicit || process.env.ATTACHMENT_ASSERT_PYTHON;
  if (wanted) return { cmd: wanted, args: [] };
  if (cachedPython) return cachedPython;
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  const tried = [];
  for (const [cmd, args] of candidates) {
    const r = spawnSync(cmd, [...args, '-c', PROBE], { env: pythonEnv(), encoding: 'utf-8' });
    if (r.status === 0) return (cachedPython = { cmd, args });
    tried.push(`${cmd} ${args.join(' ')}`.trim() + (r.error ? ' (not found)' : ' (missing packages)'));
  }
  throw new Error(
    'attachment-assert needs Python 3.9+ with pillow, numpy and pypdfium2.\n' +
    `Tried: ${tried.join(', ')}.\n` +
    `Install with: pip install -r "${REQUIREMENTS}"  or set ATTACHMENT_ASSERT_PYTHON=/path/to/python`);
}

function isDownload(x) {
  return x && typeof x.saveAs === 'function' && typeof x.suggestedFilename === 'function';
}
function isScreenshotable(x) {
  return x && typeof x.screenshot === 'function' && !isDownload(x);
}

/** Write any supported candidate to disk; returns { file, name }. */
async function materialize(candidate, workDir, name) {
  if (typeof candidate === 'string') return { file: path.resolve(candidate), name: name || path.basename(candidate) };
  if (candidate instanceof URL) return materialize(candidate.pathname, workDir, name);
  if (Buffer.isBuffer(candidate) || candidate instanceof Uint8Array) {
    const file = path.join(workDir, path.basename(name || 'candidate'));
    fs.writeFileSync(file, candidate);
    return { file, name: name || 'candidate' };
  }
  if (isDownload(candidate)) {
    const fname = name || candidate.suggestedFilename() || 'download';
    const file = path.join(workDir, path.basename(fname));
    await candidate.saveAs(file);
    return { file, name: fname };
  }
  if (isScreenshotable(candidate)) {   // Page or Locator -> PNG
    return materialize(await candidate.screenshot(), workDir, name || 'screenshot.png');
  }
  throw new TypeError('candidate must be a file path, Buffer, Playwright Download, Page or Locator');
}

function runPython(args, opts) {
  const py = findPython(opts.python);
  return new Promise((resolve, reject) => {
    const child = spawn(py.cmd, [...py.args, '-m', 'attachment_assert', ...args], { env: pythonEnv() });
    let out = '', err = '';
    child.stdout.setEncoding('utf-8').on('data', d => (out += d));
    child.stderr.setEncoding('utf-8').on('data', d => (err += d));
    child.on('error', reject);
    child.on('close', code => resolve({ code, out, err }));
  });
}

/**
 * Compare a candidate (path | Buffer | Download | Page | Locator) with a template folder.
 * Resolves to the JSON report ({ passed, counts, results[], outDir, ... }); never throws on mismatch.
 */
async function compareAttachment(candidate, template, options = {}) {
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'attachment-assert-'));
  try {
    const { file, name } = await materialize(candidate, workDir, options.name);
    const tpl = path.resolve(options.templatesDir || '', template);
    const outDir = path.resolve(options.outDir || path.join(workDir, 'report'));
    const args = ['compare', tpl, file, '--json', '--out', outDir];
    if (options.threshold != null) args.push('--threshold', String(options.threshold));
    if (options.maxDiffPercent != null) args.push('--max-diff-percent', String(options.maxDiffPercent));
    if (options.shift != null) args.push('--shift', String(options.shift));
    if (options.resize) args.push('--resize');
    for (const r of [].concat(options.only || [])) args.push('--only', r);
    const { code, out, err } = await runPython(args, options);
    if (code !== 0 && code !== 1) throw new Error(`attachment-assert failed (exit ${code}): ${err.trim() || out.trim()}`);
    const report = JSON.parse(out);
    report.candidate = name;
    report.outDir = outDir;
    report.reportHtml = path.join(outDir, 'report.html');
    report.summary = summarize(report);
    return report;
  } finally {
    if (!options.outDir) cleanupLater(workDir);
  }
}

function cleanupLater(dir) {
  // keep the report around for the current process (paths are returned to the caller)
  process.once('exit', () => { try { fs.rmSync(dir, { recursive: true, force: true }); } catch (_) {} });
}

function summarize(report) {
  const c = report.counts;
  const lines = [`${report.passed ? 'PASS' : 'FAIL'}: ${c.pass}/${report.results.length} regions match ` +
    `(${c.fail} failed, ${c.error} errors) - ${report.candidate} vs template ${report.template}`];
  for (const r of report.results) {
    if (r.status !== 'pass') lines.push(`  [${r.status.toUpperCase()}] ${r.name} (page ${r.page + 1}): ${r.message}`);
  }
  return lines.join('\n');
}

/** Like compareAttachment but throws an Error listing failed regions. */
async function assertAttachment(candidate, template, options = {}) {
  const report = await compareAttachment(candidate, template, options);
  if (!report.passed) {
    const e = new Error(report.summary + `\n  report: ${report.reportHtml}`);
    e.report = report;
    throw e;
  }
  return report;
}

module.exports = { compareAttachment, assertAttachment, findPython, materialize };
