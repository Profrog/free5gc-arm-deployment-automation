FROM python:3.11-slim

# kubectl 설치 (ARM64)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/ && \
    apt-get remove -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip install --no-cache-dir numpy==1.26.4 scikit-learn==1.4.2 joblib==1.3.2

# NWDAF 소스
WORKDIR /app
COPY src/ /app/

# nwdaf-switch.sh (DRANET 실행용)
COPY nwdaf-switch.sh /app/nwdaf-switch.sh
RUN chmod +x /app/nwdaf-switch.sh

# 기본 실행
ENTRYPOINT ["python3", "nwdaf-engine.py"]
CMD ["--interval", "5", "--window", "5"]
