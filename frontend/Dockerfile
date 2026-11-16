FROM node:20-alpine

WORKDIR /app

# Copy package manifests
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source files
COPY . .

# Expose Vite port
EXPOSE 3000

# Start Vite dev server with host binding
CMD ["npm", "run", "dev"]

