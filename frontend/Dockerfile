# HAYABUSA web tier — builds the SPA, serves it from nginx, proxies /api.

# ------------------------------------------------------------------ build ----
FROM node:22-alpine AS build

WORKDIR /build

# Install from the lockfile before copying source, so a change to a component
# does not reinstall node_modules (Docker layer caching).
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# `npm run build` runs `tsc --noEmit` first, so a type error fails the image
# build rather than shipping.
RUN npm run build

# ------------------------------------------------------------------ serve ----
FROM nginx:1.27-alpine AS runtime

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/hayabusa.conf
# Kept out of conf.d/ deliberately: nginx auto-includes conf.d/*.conf at the
# http level, which would apply these headers globally instead of only where
# they are explicitly included.
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf

COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80

# Probe 127.0.0.1, NOT localhost. Inside the container `localhost` resolves to
# ::1 first, and `listen 80;` binds IPv4 only — so a localhost probe gets
# "connection refused" from an nginx that is serving perfectly well, and the
# container is marked unhealthy forever.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
