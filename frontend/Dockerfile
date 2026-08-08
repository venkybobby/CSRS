# CSRSupport frontend -- static Vite build served by nginx on Cloud Run
# (plan §1.3: "simplest, cheapest, no server code needed beyond the BFF").
# Build context is frontend/ itself (unlike bff/Dockerfile, this has no
# dependency on shared/): docker build -f frontend/Dockerfile -t <tag> frontend/

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Cloud Run injects $PORT -- nginx.conf listens on it via envsubst at
# startup (nginx's default image supports NGINX_ENVSUBST_TEMPLATE_DIR out
# of the box for /etc/nginx/templates/*.template; simplest to just fix the
# port at build time here since Cloud Run's $PORT is stable per revision).
EXPOSE 8080
