import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "destructive" | "info" | "outline" | "glass";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variantStyles = {
    default: "border-primary/25 bg-primary/10 text-primary",
    secondary: "border-border/80 bg-secondary/80 text-secondary-foreground",
    success: "border-success/25 bg-success/10 text-success",
    warning: "border-warning/30 bg-warning/10 text-warning",
    destructive: "border-destructive/25 bg-destructive/10 text-destructive",
    info: "border-info/25 bg-info/10 text-info",
    outline: "border-border bg-transparent text-foreground",
    glass: "border-border/70 bg-card/60 backdrop-blur-md text-foreground shadow-xs",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium leading-none transition-colors select-none",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}
