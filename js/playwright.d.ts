import type { Expect } from '@playwright/test';
import type { AttachmentAssertOptions, Candidate } from './index';
export * from './index';

type MatcherResult = { pass: boolean; message: () => string; name?: string; expected?: unknown; actual?: unknown };

export declare const attachmentMatchers: {
  toMatchAttachment(this: unknown, received: Candidate, template: string, options?: AttachmentAssertOptions): Promise<MatcherResult>;
};

/** `expect` from @playwright/test extended with `toMatchAttachment`. */
export declare const expect: Expect<{
  toMatchAttachment(this: unknown, received: unknown, template: string, options?: AttachmentAssertOptions): Promise<MatcherResult>;
}>;
