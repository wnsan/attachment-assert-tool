export interface AttachmentAssertOptions {
  /** per-channel colour difference (0-255) still treated as equal */
  threshold?: number;
  /** percent of region pixels allowed to differ */
  maxDiffPercent?: number;
  /** search +/-N px for the best alignment */
  shift?: number;
  /** scale candidate pages to the reference size when they differ */
  resize?: boolean;
  /** only check these region names */
  only?: string | string[];
  /** where to write report.html / report.json / crops (default: temp dir, or testInfo.outputPath in the matcher) */
  outDir?: string;
  /** base folder for relative template paths (default: process.cwd()) */
  templatesDir?: string;
  /** Python interpreter (default: $ATTACHMENT_ASSERT_PYTHON, then py -3 / python3 / python) */
  python?: string;
  /** display / temp file name for Buffer candidates (extension helps detection) */
  name?: string;
  /** matcher only: also attach crops of passing regions to the Playwright report */
  attachAll?: boolean;
}

export interface RegionResult {
  name: string;
  page: number;
  box: [number, number, number, number];
  status: 'pass' | 'fail' | 'error';
  message: string;
  total_pixels: number;
  diff_pixels: number;
  diff_percent: number;
  max_channel_diff: number;
  mean_abs_diff: number;
  offset: [number, number];
  tolerance: { threshold: number; max_diff_percent: number; shift: number };
  images: { reference?: string; candidate?: string; diff?: string };
}

export interface AttachmentReport {
  passed: boolean;
  counts: { pass: number; fail: number; error: number };
  template: string;
  candidate: string;
  dpi: number;
  results: RegionResult[];
  pages: string[];
  outDir: string;
  reportHtml: string;
  summary: string;
}

/** Path, Buffer, Playwright Download, Page or Locator (screenshot). */
export type Candidate = string | URL | Uint8Array | { saveAs(path: string): Promise<void>; suggestedFilename(): string } | { screenshot(): Promise<Buffer> };

export function compareAttachment(candidate: Candidate, template: string, options?: AttachmentAssertOptions): Promise<AttachmentReport>;
export function assertAttachment(candidate: Candidate, template: string, options?: AttachmentAssertOptions): Promise<AttachmentReport>;
export function findPython(explicit?: string): { cmd: string; args: string[] };
