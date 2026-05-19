FROM arm64v8/alpine:3.18
RUN apk add --no-cache curl
WORKDIR /app
COPY ./smf ./smf
CMD ["./smf"]
