# WorkflowPro frontend — Vite build served by nginx (API/WS proxied to backend)
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Same-origin in Docker: nginx proxies /api and /ws to the backend container.
ENV VITE_API_URL="" \
    VITE_WS_URL=""
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
