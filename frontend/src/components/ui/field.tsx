import * as React from "react";
import { cn } from "@/lib/utils";

export function Field({
  label,
  htmlFor,
  description,
  error,
  required = false,
  className,
  children,
}: {
  label: React.ReactNode;
  htmlFor?: string;
  description?: React.ReactNode;
  error?: React.ReactNode;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const descriptionId = htmlFor ? `${htmlFor}-description` : undefined;
  const errorId = htmlFor ? `${htmlFor}-error` : undefined;
  const describedBy = [description && descriptionId, error && errorId].filter(Boolean).join(" ") || undefined;
  const control = React.isValidElement<Record<string, unknown>>(children)
    ? React.cloneElement(children, {
        "aria-describedby": [children.props["aria-describedby"], describedBy].filter(Boolean).join(" ") || undefined,
        "aria-invalid": error ? true : children.props["aria-invalid"],
      })
    : children;

  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-sm font-medium leading-none text-foreground tracking-tight">
        {label}
        {required && <span className="ml-1 text-destructive" aria-hidden="true">*</span>}
      </label>
      {control}
      {description && !error && (
        <p id={descriptionId} className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs leading-relaxed text-destructive font-medium">{error}</p>
      )}
    </div>
  );
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-lg glass-input px-3 py-1.5 text-sm text-foreground shadow-xs transition-all duration-150 cursor-pointer focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 aria-[invalid=true]:border-destructive disabled:cursor-not-allowed disabled:opacity-40",
        className
      )}
      {...props}
    />
  )
);
Select.displayName = "Select";
