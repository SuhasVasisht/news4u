import type { StdioOptions } from "node:child_process";

// Keep the OS lock in direct stage children if their Node supervisor is killed.
// Preserve its descriptor number so another TS entry point can forward it again.
export function publisherStdio(stdout: "pipe" | "inherit" = "inherit"): StdioOptions {
  const options: Exclude<StdioOptions, string> = ["inherit", stdout, "inherit"];
  const fd = Number(process.env.NEWS_PUBLISHER_LOCK_FD);
  if (Number.isInteger(fd) && fd >= 3 && fd < 1024) {
    while (options.length <= fd) options.push("ignore");
    options[fd] = fd;
  }
  return options;
}
