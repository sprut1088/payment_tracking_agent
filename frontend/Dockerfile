# ── Frontend Dockerfile ───────────────────────────────────────────────────────
# Multi-stage build:
#   Stage 1 (build)  — Node.js compiles the React/Vite app into static files.
#   Stage 2 (serve)  — nginx serves the static files and proxies /api to backend.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Copy package manifests first to leverage Docker layer cache.
COPY package*.json ./
RUN npm ci --prefer-offline --no-audit

# Copy source and config files.
COPY index.html ./
COPY tsconfig*.json vite.config.ts ./
COPY src/ ./src/

# Build the production bundle (outputs to /app/dist).
RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Replace the default nginx config with our SPA + proxy config.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the Vite build output.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
