import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "outline" | "ghost" | "destructive" | "glow" | "glass";
  size?: "default" | "sm" | "lg" | "icon" | "icon-sm" | "xs";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    const variantStyles = {
      default:
        "bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] shadow-sm font-medium",
      glow:
        "bg-primary text-primary-foreground hover:bg-primary/90 shadow-[0_0_15px_rgba(99,102,241,0.35)] active:scale-[0.98] font-medium",
      secondary:
        "bg-secondary/80 text-secondary-foreground hover:bg-secondary border border-border/60 active:scale-[0.98] font-medium",
      outline:
        "border border-border/80 bg-card/50 backdrop-blur-sm text-foreground hover:bg-secondary/80 hover:border-foreground/20 active:scale-[0.98]",
      ghost:
        "text-muted-foreground hover:text-foreground hover:bg-secondary/70 active:scale-[0.98]",
      destructive:
        "bg-destructive text-destructive-foreground hover:bg-destructive/90 active:scale-[0.98] shadow-sm font-medium",
      glass:
        "border border-border/80 bg-card/60 backdrop-blur-md text-foreground hover:bg-card/90 hover:border-primary/40 shadow-xs active:scale-[0.98]",
    };

    const sizeStyles = {
      default: "h-9 px-3.5 text-sm font-medium rounded-lg",
      sm: "h-8 px-3 text-xs font-medium rounded-md",
      lg: "h-10 px-4 text-sm font-medium rounded-xl",
      xs: "h-7 px-2 text-xs font-medium rounded-md",
      icon: "h-9 w-9 p-0 rounded-lg",
      "icon-sm": "h-8 w-8 p-0 rounded-md",
    };

    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap text-sm font-medium leading-none cursor-pointer select-none transition-all duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
