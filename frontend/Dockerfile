# syntax=docker/dockerfile:1

# Frontend: Next.js 14 (App Router), production build.

# ---- build stage ----
FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* is inlined into the client bundle at BUILD time. The browser
# (running on the host) reaches the backend on its host-published port, so this
# defaults to http://localhost:8000 — override with a build arg when deploying
# behind a different origin / reverse proxy.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# ---- runtime stage ----
FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Ship the built app (.next), its deps, public assets, and config.
COPY --from=build /app ./

EXPOSE 3000
CMD ["npm", "run", "start"]
