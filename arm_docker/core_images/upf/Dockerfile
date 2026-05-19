FROM arm64v8/ubuntu:22.04

RUN apt-get update && apt-get install -y \
    iproute2 iptables kmod \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /free5gc

# ARM64 빌드된 upf 바이너리를 복사
# 빌드 방법: free5gc_build/free5gc/ 에서 make upf (GOARCH=arm64)
COPY upf ./upf
RUN chmod +x ./upf

COPY upfcfg.yaml ./config/upfcfg.yaml
COPY wrapper.sh ./config/wrapper.sh
RUN chmod +x ./config/wrapper.sh

ENTRYPOINT ["/free5gc/config/wrapper.sh"]
