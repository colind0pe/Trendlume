"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastVariant = "default" | "success" | "error" | "warning";

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

const variantClasses: Record<ToastVariant, string> = {
  default: "border-border bg-card text-foreground",
  success: "border-success/30 bg-success-soft text-foreground",
  error: "border-destructive/40 bg-destructive-soft text-foreground",
  warning: "border-warning/40 bg-warning-soft text-foreground",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const nextId = React.useRef(0);

  const dismiss = React.useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = React.useCallback(
    (message: string, variant: ToastVariant = "default") => {
      const id = nextId.current++;
      setItems((current) => [...current, { id, message, variant }].slice(-4));
      window.setTimeout(() => dismiss(id), 4500);
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        aria-label="操作提示"
        className="fixed bottom-5 right-5 z-[100] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
      >
        {items.map((item) => (
          <div
            key={item.id}
            role="status"
            className={cn(
              "flex items-start gap-3 rounded-lg border px-3.5 py-3 text-xs shadow-popover motion-safe:animate-in motion-safe:slide-in-from-right-2",
              variantClasses[item.variant]
            )}
          >
            <span className="flex-1 leading-relaxed">{item.message}</span>
            <button
              type="button"
              aria-label="关闭提示"
              onClick={() => dismiss(item.id)}
              className="shrink-0 rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = React.useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return context;
}
