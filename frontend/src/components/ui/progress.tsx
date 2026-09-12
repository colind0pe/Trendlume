import * as React from "react";
import { cn } from "@/lib/utils";

export function Progress({
  value = 0,
  className,
  indicatorClassName,
  label = "进度",
}: {
  value?: number;
  className?: string;
  indicatorClassName?: string;
  label?: string;
}) {
  const normalizedValue = Math.max(0, Math.min(100, Number(value) || 0));

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={normalizedValue}
      className={cn(
        "relative h-1.5 w-full overflow-hidden rounded-full bg-secondary/80 border border-border/50 shadow-inner",
        className
      )}
    >
      <div
        className={cn(
          "h-full w-full flex-1 bg-gradient-to-r from-primary via-indigo-500 to-accent transition-all duration-300 ease-out rounded-full shadow-[0_0_10px_rgba(99,102,241,0.5)]",
          indicatorClassName
        )}
        style={{ transform: `translateX(-${100 - normalizedValue}%)` }}
      />
    </div>
  );
}
