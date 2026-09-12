import * as React from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed border-border/80 bg-card/35 backdrop-blur-md px-4 py-8 text-center shadow-xs", className)}>
      {Icon && (
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-border/80 bg-secondary/70 backdrop-blur-sm text-muted-foreground shadow-xs">
          <Icon aria-hidden="true" className="h-5 w-5" />
        </div>
      )}
      <h3 className="text-sm font-semibold text-foreground tracking-tight">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-xs sm:text-sm leading-relaxed text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
