# STEP 14 — Dockerfile for React Frontend
#
# Multi-stage build — two phases:
#
# Stage 1 "builder": installs Node.js, installs packages, runs "npm run build"
#   → produces a dist/ folder with plain HTML/CSS/JS (no Node.js needed anymore)
#
# Stage 2 "production": copies just the dist/ folder into a tiny Nginx image
#   → the final image is ~25MB instead of ~500MB
#   → Nginx serves the static files and proxies /api/ to Django

# ── Stage 1: Build React app ──────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first — Docker caches this layer
# If package.json didn't change, Docker skips npm install on next build
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code and build
COPY . .
RUN npm run build
# Output: /app/dist/ — a folder of static files ready to serve

# ── Stage 2: Serve with Nginx ─────────────────────────────────────────────────
FROM nginx:alpine

# Copy the built React app into Nginx's web root
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our custom Nginx config (handles routing + API proxy)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
