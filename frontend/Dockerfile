FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_OUTPUT_STANDALONE=true
COPY --from=deps /app/node_modules ./node_modules
COPY . ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
RUN addgroup -S studio && adduser -S studio -G studio
COPY --from=builder /app/public ./public
COPY --from=builder --chown=studio:studio /app/.next/standalone ./
COPY --from=builder --chown=studio:studio /app/.next/static ./.next/static
USER studio
EXPOSE 3000
CMD ["node", "server.js"]
