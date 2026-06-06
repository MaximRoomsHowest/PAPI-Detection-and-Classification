# syntax=docker/dockerfile:1.7

# ---- build stage ----------------------------------------------------------
FROM node:26-alpine@sha256:144769ec3f32e8ee36b3cfde91e82bee25d9367b20f31a151f3f7eea3a2a8541 AS build

WORKDIR /app

# Vite inlines VITE_* env vars at build time, so the API URL is a build arg.
# Default empty => the bundle uses relative URLs (/api, /media) served
# same-origin by this image's nginx reverse proxy (audit DCK-D4). Set an
# absolute backend URL only for a direct (non-proxied) deployment — which then
# also needs the backend host added back to nginx.conf's CSP and the backend's
# CORS allowlist.
ARG VITE_PAPI_API_URL=
ENV VITE_PAPI_API_URL=$VITE_PAPI_API_URL

# Lockfile-aware install for reproducible builds.
# Use `npm install` rather than `npm ci` because the lockfile is generated on
# Windows and omits @emnapi/* optional native packages that the Linux image
# needs. `npm install` resolves them at install time without losing the rest
# of the lockfile's reproducibility. Track-and-fix item: regenerate the
# lockfile from Linux (e.g. WSL or this same image) so `npm ci` works again.
COPY package.json package-lock.json ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

# ---- serve stage ----------------------------------------------------------
FROM nginxinc/nginx-unprivileged:alpine@sha256:02c985e54bee40c14c6de677226f394d96c661944185d407e77ca73602f15e1b AS serve

# nginx-unprivileged listens on 8080 by default and runs as the ``nginx`` user
# (uid 101) without needing root for binding. This is the upstream-blessed
# image for running nginx without root (audit DCK-MAJ-3).
EXPOSE 8080

# SPA-aware nginx config (react-router fallback to /index.html) + security
# headers (audit F-MAJ-13 / DCK-MAJ-6).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static bundle from the build stage.
COPY --from=build /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
