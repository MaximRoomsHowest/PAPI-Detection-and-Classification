# syntax=docker/dockerfile:1.7

# ---- build stage ----------------------------------------------------------
FROM node:24-alpine@sha256:2bdb65ed1dab192432bc31c95f94155ca5ad7fc1392fb7eb7526ab682fa5bf14 AS build

WORKDIR /app

# Vite inlines VITE_* env vars at build time, so the API URL is a build arg.
# Default empty => the bundle uses relative URLs (/api, /media) served
# same-origin by this image's nginx reverse proxy (audit DCK-D4). Set an
# absolute backend URL only for a direct (non-proxied) deployment — which then
# also needs the backend host added back to nginx.conf's CSP and the backend's
# CORS allowlist.
ARG VITE_PAPI_API_URL=
ARG VITE_PAPI_API_KEY=
ENV VITE_PAPI_API_URL=$VITE_PAPI_API_URL
ENV VITE_PAPI_API_KEY=$VITE_PAPI_API_KEY

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
FROM nginxinc/nginx-unprivileged:alpine@sha256:85bcbc6b2edd325462560c597d784ecee415024f1c6a004e53ac5f202b8ca561 AS serve

# nginx-unprivileged listens on 8080 by default and runs as the ``nginx`` user
# (uid 101) without needing root for binding. This is the upstream-blessed
# image for running nginx without root (audit DCK-MAJ-3).
EXPOSE 8080

# SPA-aware nginx config (react-router fallback to /index.html) + security
# headers (audit F-MAJ-13 / DCK-MAJ-6). Shipped as a TEMPLATE: the image's
# stock 20-envsubst-on-templates.sh renders it to /etc/nginx/conf.d/default.conf
# at container start, substituting the body-size knob below — so the upload cap
# can follow PAPI_MAX_BATCH_UPLOAD_MB without an image rebuild (audit IS-7).
# Do NOT also COPY a literal conf.d/default.conf: the render would silently
# overwrite it and mask template errors. Default = 400 MB budget + 10m headroom.
# NGINX_CONF selects WHICH template ships in the image: the default proxies
# /api + /media to the compose backend; the Azure Container Apps build passes
# NGINX_CONF=nginx.azure.conf.template (sidecar backend on localhost:8000).
# envsubst only substitutes variables that exist in the container environment,
# so nginx runtime vars ($uri, $host, ...) pass through untouched.
ENV NGINX_CLIENT_MAX_BODY_SIZE=2048m
ARG NGINX_CONF=nginx.conf.template
COPY ${NGINX_CONF} /etc/nginx/templates/default.conf.template

# Static bundle from the build stage.
COPY --from=build /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
