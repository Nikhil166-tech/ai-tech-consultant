FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

RUN npm run build || true

ENV PORT=3000
ENV TASK1_API_URL=http://task1:8000

EXPOSE 3000

CMD ["npm", "start"]
