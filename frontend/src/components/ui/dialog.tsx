"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface DialogContextValue {
  titleId: string;
  descriptionId: string;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

export interface DialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  onClose?: () => void;
  className?: string;
  children: React.ReactNode;
}

export function Dialog({ open, onOpenChange, onClose, className, children }: DialogProps) {
  const contentRef = React.useRef<HTMLDivElement>(null);
  const previousActiveElement = React.useRef<HTMLElement | null>(null);
  const titleId = React.useId();
  const descriptionId = React.useId();

  React.useEffect(() => {
    if (!open) return;

    previousActiveElement.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusFirstElement = () => {
      const firstFocusable = contentRef.current?.querySelector<HTMLElement>(
        'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
      );
      (firstFocusable || contentRef.current)?.focus();
    };
    const frame = window.requestAnimationFrame(focusFirstElement);
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        handleClose();
      }
    };
    document.addEventListener("keydown", handleEscape);

    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = previousOverflow;
      previousActiveElement.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  const handleClose = () => {
    onClose?.();
    onOpenChange?.(false);
  };

  const handleContentKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
      )
    );
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 overflow-hidden">
      <div
        className="fixed inset-0 bg-background/70 backdrop-blur-md transition-opacity duration-200"
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        ref={contentRef}
        tabIndex={-1}
        onKeyDown={handleContentKeyDown}
        className={cn(
          "relative z-50 w-full max-w-lg max-h-[min(90vh,calc(100vh-2rem))] overflow-y-auto rounded-2xl glass-dialog p-5 sm:p-6 text-card-foreground shadow-glass-modal motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95 motion-safe:duration-200",
          className
        )}
      >
        <button
          type="button"
          aria-label="关闭"
          onClick={handleClose}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-muted-foreground transition-all hover:bg-secondary/80 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95 cursor-pointer"
        >
          <X className="h-4 w-4" />
        </button>
        <DialogContext.Provider value={{ titleId, descriptionId }}>
          {children}
        </DialogContext.Provider>
      </div>
    </div>
  );
}

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col space-y-1.5 text-left mb-4", className)} {...props} />;
}

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  const context = React.useContext(DialogContext);
  return <h2 id={context?.titleId} className={cn("text-base sm:text-lg font-semibold tracking-tight text-foreground", className)} {...props} />;
}

export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  const context = React.useContext(DialogContext);
  return <p id={context?.descriptionId} className={cn("text-xs sm:text-sm leading-relaxed text-muted-foreground", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2.5 gap-2 mt-5 sm:mt-6 pt-4 border-t border-border/60", className)} {...props} />;
}
