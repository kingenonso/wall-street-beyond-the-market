FROM node:22-slim
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npx", "vite", "--host", "0.0.0.0"]
