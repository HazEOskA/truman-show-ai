# Hydra World — Observatory (Next.js)
FROM node:22-alpine AS deps
WORKDIR /app
COPY apps/observatory/package.json ./
RUN npm install --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY apps/observatory ./
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Next's standalone server reads PORT and HOSTNAME, so Cloud Run's injected port just works.
# HYDRA_API_URL is read per request in app/layout.tsx, so this image is not welded to one API.
EXPOSE 3000
CMD ["node", "server.js"]
