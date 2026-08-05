# Build stage: compile the Vite/React app into static files.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Runtime stage: serve the built assets behind an nginx container that the
# reverse proxy (portal.conf) reaches at `portal-frontend:80`.
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80