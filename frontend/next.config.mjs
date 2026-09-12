import path from "node:path";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  webpack(config) {
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "@": path.resolve(process.cwd(), "src"),
    };
    return config;
  },
  // Allow local smoke-test or parallel worktree builds to avoid sharing the
  // incremental .next directory with an already running dev server.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
