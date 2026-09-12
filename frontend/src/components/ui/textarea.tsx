import * as React from "react";
import { cn } from "@/lib/utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex min-h-[72px] w-full rounded-lg glass-input px-3 py-2 text-sm text-foreground shadow-xs transition-all duration-150 placeholder:text-muted-foreground/50 focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive disabled:cursor-not-allowed disabled:opacity-40 leading-relaxed overflow-y-auto resize-y",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Textarea.displayName = "Textarea";
