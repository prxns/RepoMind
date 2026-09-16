FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package.json /app/package.json
RUN npm install --no-audit --no-fund
COPY apps/web /app
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app /app
EXPOSE 3000
CMD ["npm", "run", "start"]
