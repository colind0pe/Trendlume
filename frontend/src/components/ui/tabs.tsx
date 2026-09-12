"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (value: string) => void;
  tabsId: string;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

export function Tabs({
  defaultValue,
  value,
  onValueChange,
  children,
  className,
}: {
  defaultValue?: string;
  value?: string;
  onValueChange?: (val: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const [selected, setSelected] = React.useState(defaultValue || "");
  const tabsId = React.useId();

  const activeTab = value !== undefined ? value : selected;
  const setActiveTab = (val: string) => {
    if (value === undefined) setSelected(val);
    onValueChange?.(val);
  };

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab, tabsId }}>
      <div className={cn("space-y-4", className)}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      role="tablist"
      aria-orientation="horizontal"
      className={cn(
        "inline-flex h-9 items-center justify-start gap-1 rounded-lg glass-pill p-1 text-muted-foreground overflow-x-auto no-scrollbar shadow-xs",
        className
      )}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  children,
  className,
  disabled = false,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error("TabsTrigger must be used within Tabs");

  const isActive = context.activeTab === value;
  const triggerId = `${context.tabsId}-tab-${encodeURIComponent(value)}`;
  const panelId = `${context.tabsId}-panel-${encodeURIComponent(value)}`;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;

    const triggers = Array.from(
      event.currentTarget.closest('[role="tablist"]')?.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]:not([disabled])'
      ) || []
    );
    const currentIndex = triggers.indexOf(event.currentTarget);
    if (currentIndex === -1 || triggers.length === 0) return;

    event.preventDefault();
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? triggers.length - 1
          : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + triggers.length) % triggers.length;
    const nextTrigger = triggers[nextIndex];
    nextTrigger.focus();
    nextTrigger.click();
  };

  return (
    <button
      type="button"
      id={triggerId}
      role="tab"
      aria-selected={isActive}
      aria-controls={panelId}
      tabIndex={isActive ? 0 : -1}
      disabled={disabled}
      onClick={() => context.setActiveTab(value)}
      onKeyDown={handleKeyDown}
      className={cn(
        "inline-flex h-7 px-3 items-center justify-center whitespace-nowrap rounded-md text-xs sm:text-sm font-medium cursor-pointer transition-all duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40 select-none",
        isActive
          ? "bg-card text-foreground shadow-xs font-semibold border border-border/80"
          : "text-muted-foreground hover:text-foreground hover:bg-card/40",
        className
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
}) {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error("TabsContent must be used within Tabs");

  const triggerId = `${context.tabsId}-tab-${encodeURIComponent(value)}`;
  const panelId = `${context.tabsId}-panel-${encodeURIComponent(value)}`;

  if (context.activeTab !== value) return null;

  return (
    <div
      id={panelId}
      role="tabpanel"
      aria-labelledby={triggerId}
      tabIndex={0}
      className={cn(
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-safe:animate-in motion-safe:fade-in-50 motion-safe:duration-150",
        className
      )}
    >
      {children}
    </div>
  );
}
