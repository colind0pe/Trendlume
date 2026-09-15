"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";
import { useModalFocus } from "./modal-focus";

interface SheetContextValue {
  titleId: string;
  descriptionId: string;
}

const SheetContext = React.createContext<SheetContextValue | null>(null);

export interface SheetProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  onClose?: () => void;
  side?: "right" | "left" | "bottom";
  className?: string;
  children: React.ReactNode;
}

export function Sheet({
  open,
  onOpenChange,
  onClose,
  side = "right",
  className,
  children,
}: SheetProps) {
  const titleId = React.useId();
  const descriptionId = React.useId();

  const handleClose = React.useCallback(() => {
    onClose?.();
    onOpenChange?.(false);
  }, [onClose, onOpenChange]);

  const { contentRef, handleContentKeyDown } = useModalFocus(open, handleClose);

  if (!open) return null;

  const sideClasses = {
    right:
      "fixed inset-y-0 right-0 z-50 h-full w-full max-w-xl border-l border-border/80 motion-safe:animate-in motion-safe:slide-in-from-right motion-safe:duration-200",
    left:
      "fixed inset-y-0 left-0 z-50 h-full w-full max-w-xl border-r border-border/80 motion-safe:animate-in motion-safe:slide-in-from-left motion-safe:duration-200",
    bottom:
      "fixed inset-x-0 bottom-0 z-50 max-h-[85vh] w-full rounded-t-2xl border-t border-border/80 motion-safe:animate-in motion-safe:slide-in-from-bottom motion-safe:duration-200",
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      <div
        className="fixed inset-0 bg-background/80 backdrop-blur-md transition-opacity duration-200"
        onClick={handleClose}
        aria-hidden="true"
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
          "relative flex flex-col glass-dialog p-5 sm:p-7 text-card-foreground shadow-2xl focus-visible:outline-none",
          sideClasses[side],
          className
        )}
      >
        <button
          type="button"
          aria-label="关闭"
          onClick={handleClose}
          className="absolute right-4 top-4 z-10 rounded-lg p-1.5 text-muted-foreground transition-all hover:bg-secondary/80 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95 cursor-pointer"
        >
          <X className="h-4 w-4" />
        </button>
        <SheetContext.Provider value={{ titleId, descriptionId }}>
          {children}
        </SheetContext.Provider>
      </div>
    </div>
  );
}

export function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col space-y-1.5 text-left pr-8 mb-4", className)} {...props} />;
}

export function SheetTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  const context = React.useContext(SheetContext);
  return <h2 id={context?.titleId} className={cn("text-lg sm:text-xl font-semibold leading-snug tracking-tight text-foreground", className)} {...props} />;
}

export function SheetDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  const context = React.useContext(SheetContext);
  return <p id={context?.descriptionId} className={cn("text-xs sm:text-sm leading-relaxed text-muted-foreground", className)} {...props} />;
}

export function SheetContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-h-0 flex-1 space-y-5 overflow-y-auto pr-1", className)} {...props} />;
}

export function SheetFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-5 shrink-0 flex flex-col space-y-2 border-t border-border/60 pt-4", className)} {...props} />;
}
