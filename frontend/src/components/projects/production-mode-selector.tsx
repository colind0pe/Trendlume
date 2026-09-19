"use client";

import type { LucideIcon } from "lucide-react";
import { BookOpen, Clapperboard, ShoppingBag } from "lucide-react";
import { PRODUCTION_MODE_SPECS, PRODUCTION_MODE_VALUES } from "@/lib/ui-constants";
import type { ProductionMode } from "@/lib/types";

const MODE_ICONS: Record<ProductionMode, LucideIcon> = {
  knowledge: BookOpen,
  commerce: ShoppingBag,
  drama: Clapperboard,
};

export function ProductionModeSelector({
  value,
  onChange,
}: {
  value: ProductionMode;
  onChange: (mode: ProductionMode) => void;
}) {
  return (
    <fieldset className="space-y-2.5">
      <legend className="text-sm font-medium text-foreground">生产模式</legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="生产模式">
        {PRODUCTION_MODE_VALUES.map((mode) => {
          const spec = PRODUCTION_MODE_SPECS[mode];
          const Icon = MODE_ICONS[mode];
          const selected = value === mode;

          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={spec.label}
              onClick={() => onChange(mode)}
              className={`min-h-20 rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background ${
                selected
                  ? "border-primary/60 bg-primary/10 text-foreground"
                  : "border-border/70 bg-card/40 text-muted-foreground hover:border-foreground/20 hover:bg-secondary/50"
              }`}
            >
              <span className="flex items-start justify-between gap-2">
                <span className="flex items-center gap-2 font-medium">
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {spec.label}
                </span>
              </span>
              <span className="mt-1.5 block text-xs leading-5 text-muted-foreground">
                {spec.description}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
