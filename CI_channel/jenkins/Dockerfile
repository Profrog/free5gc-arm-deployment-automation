FROM jenkins/jenkins:lts-jdk17

USER root

# ────────────────────────────────────────────
# 기본 패키지
# ────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git ssh make gcc g++ cmake \
    ca-certificates gnupg lsb-release \
    jq unzip \
    && rm -rf /var/lib/apt/lists/*

# ────────────────────────────────────────────
# Go 1.21 (ARM64)
# ────────────────────────────────────────────
ARG GO_VERSION=1.21.13
RUN wget -q "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz" -O /tmp/go.tar.gz \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz

ENV PATH="/usr/local/go/bin:${PATH}"
ENV GOPATH="/var/jenkins_home/go"

# ────────────────────────────────────────────
# Docker CLI (호스트 Docker 소켓 사용)
# ────────────────────────────────────────────
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
       $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Jenkins 사용자에게 docker 그룹 접근 권한
RUN groupadd -f docker && usermod -aG docker jenkins

# ────────────────────────────────────────────
# kubectl
# ────────────────────────────────────────────
RUN curl -fsSL "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl" \
    -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# ────────────────────────────────────────────
# Gerrit trigger용 SSH 키 디렉토리
# ────────────────────────────────────────────
RUN mkdir -p /var/jenkins_home/.ssh \
    && chown -R jenkins:jenkins /var/jenkins_home/.ssh

# ────────────────────────────────────────────
# 플러그인 설치
# ────────────────────────────────────────────
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

USER jenkins

ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
