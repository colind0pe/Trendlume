# ==============================================================================
# Trendlume - Next.js Frontend Dockerfile
# ==============================================================================

FROM node:18-alpine AS builder

WORKDIR /app

ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

COPY frontend/tsconfig.json frontend/next-env.d.ts frontend/next.config.mjs frontend/postcss.config.mjs frontend/tailwind.config.ts ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN npm run build

FROM node:18-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
