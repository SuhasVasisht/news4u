import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "surface-strong w-full rounded-full px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted focus:border-line-strong",
        className,
      )}
      {...props}
    />
  );
}
