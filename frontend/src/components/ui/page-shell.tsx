import * as React from "react";
import { cn } from "@/lib/utils";

export function PageContainer({
  children,
  className,
  width = "standard",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  width?: "standard" | "wide" | "full";
}) {
  return (
    <div
      {...props}
      className={cn(
        "mx-auto w-full pt-4 sm:pt-5 pb-8 sm:pb-10",
        width === "standard" && "max-w-7xl px-4 sm:px-6 lg:px-8",
        width === "wide" && "max-w-[1440px] px-4 sm:px-6 lg:px-8",
        width === "full" && "max-w-[1680px] px-4 sm:px-6 lg:px-8",
        className
      )}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  eyebrow,
  back,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  back?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-3 border-b border-border/70 pb-3.5 sm:flex-row sm:items-center sm:justify-between", className)}>
      <div className="min-w-0 space-y-1">
        {back}
        {eyebrow && <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-xl sm:text-2xl font-bold leading-tight tracking-tight text-foreground">{title}</h1>
        {description && <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between", className)}>
      <div className="min-w-0">
        <h2 className="text-base sm:text-lg font-semibold leading-snug tracking-tight text-foreground">{title}</h2>
        {description && <p className="mt-0.5 text-xs sm:text-sm leading-normal text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
