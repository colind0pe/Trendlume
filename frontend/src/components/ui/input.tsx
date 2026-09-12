import * as React from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-lg glass-input px-3 py-1.5 text-sm text-foreground shadow-xs transition-all duration-150 placeholder:text-muted-foreground/50 focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive disabled:cursor-not-allowed disabled:opacity-40",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export interface SearchInputProps extends Omit<InputProps, "type"> {
  onClear?: () => void;
}

export const SearchInput = React.forwardRef<HTMLInputElement, SearchInputProps>(
  ({ className, value, onClear, onChange, ...props }, ref) => {
    const hasValue = Boolean(value && String(value).length > 0);
    return (
      <div className="relative w-full">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          ref={ref}
          type="text"
          value={value}
          onChange={onChange}
          className={cn("pl-9", hasValue && onClear ? "pr-8" : "", className)}
          {...props}
        />
        {hasValue && onClear && (
          <button
            type="button"
            onClick={onClear}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 h-5 w-5 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/70 flex items-center justify-center cursor-pointer transition-colors"
            title="清除搜索"
            aria-label="清除搜索"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    );
  }
);
SearchInput.displayName = "SearchInput";
