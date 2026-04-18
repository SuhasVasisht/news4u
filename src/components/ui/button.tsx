import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({
  className,
  variant = "primary",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center rounded-full px-4 py-2 text-sm font-medium",
        variant === "primary" &&
          "bg-accent text-white hover:-translate-y-0.5 hover:opacity-95",
        variant === "secondary" &&
          "surface-strong text-ink hover:border-line-strong hover:bg-accent-soft",
        variant === "ghost" && "text-muted hover:bg-accent-soft hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}
