import React from "react";
import { cn } from "@/lib/utils";

export interface BrandMarkProps extends React.SVGProps<SVGSVGElement> {
  size?: number | "xs" | "sm" | "md" | "lg" | "xl";
  glow?: boolean;
  className?: string;
}

const SIZE_MAP = {
  xs: 18,
  sm: 24,
  md: 32,
  lg: 44,
  xl: 60,
};

/**
 * Trendlume 品牌符号：故事板轨道、播放棱镜与发布光点。
 */
export function BrandMark({
  size = "md",
  glow = true,
  className,
  ...props
}: BrandMarkProps) {
  const pixelSize = typeof size === "number" ? size : SIZE_MAP[size] || 32;

  return (
    <div
      className={cn(
        "relative inline-flex items-center justify-center shrink-0 select-none",
        className
      )}
      style={{ width: pixelSize, height: pixelSize }}
    >
      {glow && (
        <div
          aria-hidden="true"
          className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-primary/40 via-accent/30 to-cyan-400/20 blur-md opacity-60 pointer-events-none transition-opacity duration-300 group-hover:opacity-90"
        />
      )}

      <svg
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="relative z-10 w-full h-full drop-shadow-sm"
        aria-label="Trendlume Logo"
        {...props}
      >
        <defs>
          <linearGradient id="tl-brand-bg" x1="4" y1="4" x2="60" y2="60" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#111827" />
            <stop offset="54%" stopColor="#172554" />
            <stop offset="100%" stopColor="#312E81" />
          </linearGradient>
          <linearGradient id="tl-brand-play" x1="24" y1="43" x2="46" y2="21" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#7C3AED" />
            <stop offset="48%" stopColor="#6366F1" />
            <stop offset="100%" stopColor="#22D3EE" />
          </linearGradient>
          <linearGradient id="tl-brand-line" x1="15" y1="48" x2="49" y2="20" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#A78BFA" />
            <stop offset="100%" stopColor="#67E8F9" />
          </linearGradient>
          <linearGradient id="tl-brand-spark" x1="39" y1="16" x2="48" y2="29" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="100%" stopColor="#67E8F9" />
          </linearGradient>
          <filter id="tl-brand-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="1.8" floodColor="#020617" floodOpacity="0.5" />
          </filter>
        </defs>

        <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#tl-brand-bg)" stroke="#A5B4FC" strokeOpacity="0.34" strokeWidth="1.6" />
        <rect x="10.5" y="12.5" width="43" height="35" rx="10" fill="#0F172A" fillOpacity="0.16" stroke="#C4B5FD" strokeOpacity="0.24" />
        <path d="M16 21.5H21M16 28H19.5M16 40.5H21" stroke="#A5B4FC" strokeOpacity="0.7" strokeWidth="2" strokeLinecap="round" />
        <path
          d="M28.2 20.7C26.1 19.5 23.5 20.9 23.5 23.3V40.7C23.5 43.1 26.1 44.5 28.2 43.3L44.3 34C46.4 32.8 46.4 29.8 44.3 28.6L28.2 20.7Z"
          fill="url(#tl-brand-play)"
          filter="url(#tl-brand-shadow)"
        />
        <path d="M29 25.4L41.2 32L29 38.6V25.4Z" fill="#FFFFFF" fillOpacity="0.22" />
        <path d="M14 49H50" stroke="url(#tl-brand-line)" strokeOpacity="0.82" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="18" cy="49" r="2" fill="#C4B5FD" />
        <circle cx="32" cy="49" r="2" fill="#818CF8" />
        <circle cx="46" cy="49" r="2" fill="#67E8F9" />
        <path d="M43 16C43 19.1 44.8 21 48 21C44.8 21 43 22.9 43 26C43 22.9 41.2 21 38 21C41.2 21 43 19.1 43 16Z" fill="url(#tl-brand-spark)" />
        <circle cx="43" cy="21" r="1.2" fill="#FFFFFF" />
      </svg>
    </div>
  );
}

export interface BrandLogoProps {
  size?: "sm" | "md" | "lg";
  showSubtitle?: boolean;
  subtitleText?: string;
  className?: string;
  glow?: boolean;
}

/** Trendlume 完整品牌图文标。 */
export function BrandLogo({
  size = "md",
  showSubtitle = true,
  subtitleText = "AI 短视频创作与发布",
  className,
  glow = true,
}: BrandLogoProps) {
  const markSize = size === "sm" ? 26 : size === "lg" ? 42 : 32;

  return (
    <div className={cn("flex items-center gap-2.5 select-none", className)}>
      <BrandMark size={markSize} glow={glow} />
      <div className="flex flex-col justify-center min-w-0">
        <div className="flex items-center gap-1.5 leading-none">
          <span className="font-extrabold text-sm sm:text-base tracking-tight font-sans brand-wordmark select-none">
            Trendlume
          </span>
          <span className="rounded-[4px] border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-xs font-mono font-medium tracking-wider text-primary">
            STUDIO
          </span>
        </div>
        {showSubtitle && (
          <p className="text-xs text-muted-foreground leading-tight mt-1 font-normal tracking-wide">
            {subtitleText}
          </p>
        )}
      </div>
    </div>
  );
}
