# syntax=docker/dockerfile:1
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* se incrusta en el bundle del cliente al compilar
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8010
ARG NEXT_PUBLIC_TAWK_PROPERTY_ID=
ARG NEXT_PUBLIC_TAWK_WIDGET_ID=
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_PUBLIC_TAWK_PROPERTY_ID=$NEXT_PUBLIC_TAWK_PROPERTY_ID \
    NEXT_PUBLIC_TAWK_WIDGET_ID=$NEXT_PUBLIC_TAWK_WIDGET_ID
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
