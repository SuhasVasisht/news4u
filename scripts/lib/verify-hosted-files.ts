import { hash } from "./static-release";

/** Check every byte with a bounded pool; retry transport, never bad content. */
export async function verifyHostedFiles(base: string, files: Record<string, string>, options: {
  concurrency?: number; attempts?: number; retryDelayMs?: number;
  progress?: (completed: number, total: number) => void;
} = {}) {
  const names = Object.keys(files);
  const concurrency = options.concurrency ?? 6;
  const attempts = options.attempts ?? 3;
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8
      || !Number.isInteger(attempts) || attempts < 1 || attempts > 3) throw new Error("Invalid hosted verification bounds");
  let cursor = 0, completed = 0;
  let failure: unknown;
  async function check(name: string) {
    for (let attempt = 0; attempt < attempts; attempt++) {
      let terminal = false;
      try {
        const response = await fetch(new URL(`/${name}`, base), { signal: AbortSignal.timeout(30_000) });
        if (!response.ok) {
          terminal = response.status !== 429 && response.status < 500;
          throw new Error(`Hosted file unavailable: ${name} (HTTP ${response.status})`);
        }
        if (hash(Buffer.from(await response.arrayBuffer())) !== files[name]) {
          terminal = true;
          throw new Error(`Hosted file changed: ${name}`);
        }
        return;
      } catch (error) {
        if (terminal || attempt + 1 === attempts) throw error;
        console.log(JSON.stringify({ event: "verification_file_retry", host: new URL(base).hostname,
          file: name, attempt: attempt + 1, reason: error instanceof Error ? error.message : String(error) }));
        await new Promise(resolve => setTimeout(resolve, (options.retryDelayMs ?? 500) * (attempt + 1)));
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, names.length) }, async () => {
    while (cursor < names.length && !failure) {
      const name = names[cursor++];
      try { await check(name); }
      catch (error) { failure ??= error; return; }
      completed++;
      options.progress?.(completed, names.length);
    }
  }));
  if (failure) throw failure;
}
