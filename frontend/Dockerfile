# --- Etapa 1: build ---
FROM node:20-alpine AS build

WORKDIR /app

# Copiando ficheros de dependencias primero (cache de capas)
COPY package.json package-lock.json* ./

# Instalando dependencias
RUN npm ci

# Copiando código fuente y assets
COPY index.html vite.config.js ./
COPY public/ ./public/
COPY src/ ./src/

# Build de producción
RUN npm run build

# --- Etapa 2: servir con nginx ---
FROM nginx:alpine

# Copiando configuración de nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiando build estático
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
