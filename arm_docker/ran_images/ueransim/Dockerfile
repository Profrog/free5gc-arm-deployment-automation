FROM arm64v8/ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git make g++ cmake \
    libsctp-dev lksctp-tools iproute2 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone -b v3.2.6 https://github.com/aligungr/UERANSIM /UERANSIM

WORKDIR /UERANSIM
RUN make -j$(nproc)

# ──── runtime ────
FROM arm64v8/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    libsctp-dev lksctp-tools iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ueransim

COPY --from=builder /UERANSIM/build/nr-gnb .
COPY --from=builder /UERANSIM/build/nr-ue .

VOLUME ["/ueransim/config"]
