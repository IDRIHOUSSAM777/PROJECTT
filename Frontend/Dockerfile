# Use Node.js as the base image for building the app
FROM node:20-alpine AS build

# Set working directory
WORKDIR /app

# Copy package.json and install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy all source files
COPY . .

# Build the frontend (Vite builds into /app/dist)
RUN npm run build

# Stage 2: Serve the app using Nginx
FROM nginx:alpine

# Copy the built files from the previous stage to Nginx html directory
COPY --from=build /app/dist /usr/share/nginx/html

# Add basic Nginx config for React Router
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

# Expose port (inside container)
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
