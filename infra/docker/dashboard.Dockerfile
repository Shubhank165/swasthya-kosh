# The doctor's dashboard, served beside the API — 3/3 §4, and the reason
# docker-compose.yml exists at all.
#
# The compose stack is the demo path if the venue wifi fails. Until now it
# produced a working kiosk-to-report flow with nothing to *read* the report on,
# which made the offline path a demonstration of the half of the system nobody
# watches. This image closes that.
#
# Two stages. The first builds; the second serves static files and nothing else
# — no Node, no build tooling, no source. What reaches a machine in a hospital
# is a directory of assets and a reverse proxy.

FROM node:22-alpine AS build
WORKDIR /build

# The manifest first, so a source edit does not re-resolve the dependency tree.
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

COPY dashboard/ ./
# `npm run build` runs `tsc --noEmit` before vite, so a type error fails the
# image rather than shipping. The API types are committed rather than
# regenerated here: this stage has no backend to read an OpenAPI document from,
# and a build that silently fell back to stale types would be worse than one
# that used the committed ones deliberately.
RUN npm run build


FROM nginx:1.27-alpine AS runtime

# Same origin for the page, the API and the socket. That is how the deployment
# serves them, and it is what keeps the refresh cookie first-party and CORS out
# of the picture entirely — see `dashboard/vite.config.ts`, which reproduces
# exactly this in development.
COPY infra/docker/dashboard.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80
