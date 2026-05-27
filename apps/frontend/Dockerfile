# syntax=docker/dockerfile:1.7

# ---- build stage ----------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Vite inlines VITE_* env vars at build time, so the API URL is a build arg.
ARG VITE_PAPI_API_URL=http://localhost:8000
ENV VITE_PAPI_API_URL=$VITE_PAPI_API_URL

# Lockfile-aware install for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- serve stage ----------------------------------------------------------
FROM nginx:alpine AS serve

# SPA-aware nginx config (react-router fallback to /index.html).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static bundle from the build stage.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
