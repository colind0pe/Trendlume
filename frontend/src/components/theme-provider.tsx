"use client";

import * as React from "react";
import { Moon, Sun, Laptop } from "lucide-react";
import { cn } from "@/lib/utils";

type Theme = "light" | "dark" | "system";

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: "light" | "dark";
}

const ThemeContext = React.createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = React.useState<"light" | "dark">("dark");

  React.useEffect(() => {
    const saved = localStorage.getItem("trendlume-theme") as Theme | null;
    if (saved && (saved === "light" || saved === "dark" || saved === "system")) {
      setThemeState(saved);
    }
  }, []);

  React.useEffect(() => {
    const root = document.documentElement;

    const applyTheme = () => {
      let isDark = false;
      if (theme === "system") {
        isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      } else {
        isDark = theme === "dark";
      }

      setResolvedTheme(isDark ? "dark" : "light");

      if (isDark) {
        root.classList.add("dark");
      } else {
        root.classList.remove("dark");
      }
    };

    applyTheme();

    if (theme === "system") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const listener = () => applyTheme();
      mediaQuery.addEventListener("change", listener);
      return () => mediaQuery.removeEventListener("change", listener);
    }
  }, [theme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem("trendlume-theme", newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = React.useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="主题模式"
      className={cn("inline-flex items-center rounded-lg border border-border bg-secondary/50 p-0.5 text-muted-foreground", className)}
    >
      <button
        type="button"
        aria-label="浅色主题"
        aria-pressed={theme === "light"}
        title="浅色主题"
        onClick={() => setTheme("light")}
        className={cn("rounded-md p-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-secondary", 
          theme === "light" ? "bg-background text-foreground shadow-sm font-medium" : "hover:text-foreground"
        )}
      >
        <Sun aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        aria-label="跟随系统"
        aria-pressed={theme === "system"}
        title="跟随系统"
        onClick={() => setTheme("system")}
        className={cn("rounded-md p-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-secondary",
          theme === "system" ? "bg-background text-foreground shadow-sm font-medium" : "hover:text-foreground"
        )}
      >
        <Laptop aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        aria-label="深色主题"
        aria-pressed={theme === "dark"}
        title="深色主题"
        onClick={() => setTheme("dark")}
        className={cn("rounded-md p-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-secondary",
          theme === "dark" ? "bg-background text-foreground shadow-sm font-medium" : "hover:text-foreground"
        )}
      >
        <Moon aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
