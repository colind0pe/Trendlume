import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Asset } from "./types";

export const BGM_STORAGE_PREFIX = "audio/bgm/";

export function isBgmAsset(
  asset: Pick<Asset, "asset_type" | "file_path"> | null | undefined,
) {
  const normalizedPath = asset?.file_path?.replace(/\\/g, "/") || "";
  return asset?.asset_type === "bgm" && normalizedPath.startsWith(BGM_STORAGE_PREFIX);
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number, decimals = 2) {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function formatDate(isoString: string) {
  if (!isoString) return "-";
  const d = new Date(isoString);
  return d.toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function safePexelsPageUrl(value: unknown, kind: "video" | "author" = "video") {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    const path = url.pathname.replace(/\/+$/, "");
    const validHost = host === "www.pexels.com" || host === "pexels.com";
    const validPath = kind === "author"
      ? path.startsWith("/@") && path.length > 2
      : path.startsWith("/video/") && path.length > 7;
    if (
      url.protocol !== "https:" ||
      (url.port && url.port !== "443") ||
      !validHost ||
      !validPath ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}
