import * as React from "react";
import { cn } from "@/lib/utils";
import { Badge, type BadgeProps } from "@/components/ui/badge";

export type StatusTone = "success" | "warning" | "destructive" | "info" | "neutral" | "primary";

export function StatusBadge({
  label,
  tone = "neutral",
  className,
  showDot = true,
}: {
  label: React.ReactNode;
  tone?: StatusTone;
  className?: string;
  showDot?: boolean;
}) {
  const variant: BadgeProps["variant"] = tone === "primary" ? "default" : tone === "neutral" ? "secondary" : tone;
  
  const dotColors = {
    primary: "bg-primary shadow-[0_0_6px_hsl(var(--primary))] animate-pulse",
    success: "bg-success shadow-[0_0_6px_hsl(var(--success))]",
    warning: "bg-warning shadow-[0_0_6px_hsl(var(--warning))]",
    destructive: "bg-destructive shadow-[0_0_6px_hsl(var(--destructive))]",
    info: "bg-info shadow-[0_0_6px_hsl(var(--info))]",
    neutral: "bg-muted-foreground/60",
  };

  return (
    <Badge variant={variant} className={cn("gap-1.5 font-medium", className)}>
      {showDot && (
        <span
          aria-hidden="true"
          className={cn("h-1.5 w-1.5 rounded-full shrink-0", dotColors[tone])}
        />
      )}
      <span>{label}</span>
    </Badge>
  );
}
