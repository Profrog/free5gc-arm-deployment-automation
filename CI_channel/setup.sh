#!/bin/bash
# CI_channel 초기 설정 스크립트
# Gerrit 프로젝트 생성 + Jenkins SSH 키 연동 + upstream mirror
#
# 사전 조건: docker compose up -d 실행 후 Gerrit이 healthy 상태
# 사용: ./setup.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

GERRIT_URL="http://localhost:8080"
GERRIT_SSH="localhost"
GERRIT_SSH_PORT=29418
JENKINS_CONTAINER="jenkins"

# NF 프로젝트 목록 (Gerrit 프로젝트명: free5gc/{nf})
ALL_NFS="nrf amf ausf pcf udr udm nssf smf upf ueransim"

# upstream GitHub 리포 매핑
declare -A UPSTREAM_REPOS
UPSTREAM_REPOS[nrf]="https://github.com/free5gc/nrf.git"
UPSTREAM_REPOS[amf]="https://github.com/free5gc/amf.git"
UPSTREAM_REPOS[ausf]="https://github.com/free5gc/ausf.git"
UPSTREAM_REPOS[pcf]="https://github.com/free5gc/pcf.git"
UPSTREAM_REPOS[udr]="https://github.com/free5gc/udr.git"
UPSTREAM_REPOS[udm]="https://github.com/free5gc/udm.git"
UPSTREAM_REPOS[nssf]="https://github.com/free5gc/nssf.git"
UPSTREAM_REPOS[smf]="https://github.com/free5gc/smf.git"
UPSTREAM_REPOS[upf]="https://github.com/free5gc/go-upf.git"
UPSTREAM_REPOS[ueransim]="https://github.com/aligungr/UERANSIM.git"

UPSTREAM_TAG="${1:-v3.4.3}"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# ────────────────────────────────────────────
# 1. Gerrit 상태 확인
# ────────────────────────────────────────────
log "=== Checking Gerrit status ==="
for i in $(seq 1 30); do
    if curl -sf "${GERRIT_URL}/" > /dev/null 2>&1; then
        ok "Gerrit is up"
        break
    fi
    [ $i -eq 30 ] && die "Gerrit not responding at ${GERRIT_URL}"
    echo "  Waiting for Gerrit... ($i/30)"
    sleep 5
done

# ────────────────────────────────────────────
# 2. Jenkins SSH 키 생성
# ────────────────────────────────────────────
log "=== Setting up Jenkins SSH key ==="
SSH_KEY_DIR="$SCRIPT_DIR/.ssh"
mkdir -p "$SSH_KEY_DIR"

if [ ! -f "$SSH_KEY_DIR/jenkins_gerrit_rsa" ]; then
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_DIR/jenkins_gerrit_rsa" -N "" -C "jenkins@ci"
    ok "SSH keypair generated"
else
    log "  SSH key already exists, skipping."
fi

# Jenkins 컨테이너에 키 복사
docker cp "$SSH_KEY_DIR/jenkins_gerrit_rsa" "${JENKINS_CONTAINER}:/var/jenkins_home/.ssh/id_rsa"
docker cp "$SSH_KEY_DIR/jenkins_gerrit_rsa.pub" "${JENKINS_CONTAINER}:/var/jenkins_home/.ssh/id_rsa.pub"
docker exec "${JENKINS_CONTAINER}" chown -R jenkins:jenkins /var/jenkins_home/.ssh
docker exec "${JENKINS_CONTAINER}" chmod 600 /var/jenkins_home/.ssh/id_rsa
ok "SSH key copied to Jenkins container"

# SSH known_hosts에 Gerrit 추가
docker exec "${JENKINS_CONTAINER}" bash -c \
    "ssh-keyscan -p ${GERRIT_SSH_PORT} gerrit >> /var/jenkins_home/.ssh/known_hosts 2>/dev/null"

# ────────────────────────────────────────────
# 3. Gerrit 관리자 계정 설정
# ────────────────────────────────────────────
log "=== Setting up Gerrit admin account ==="

# DEVELOPMENT_BECOME_ANY_ACCOUNT 모드에서 admin 계정 생성
# 첫 번째 접속자가 admin이 됨 — admin 계정에 Jenkins SSH 공개키 등록
JENKINS_PUB_KEY=$(cat "$SSH_KEY_DIR/jenkins_gerrit_rsa.pub")

# Gerrit REST API로 admin 설정 (admin 계정 ID = 1000000)
# 주의: DEVELOPMENT_BECOME_ANY_ACCOUNT에서는 인증 없이 접근 가능
curl -sf "${GERRIT_URL}/accounts/self" > /dev/null 2>&1 || true

# Jenkins 서비스 계정 생성 시도
log "  Creating jenkins service account in Gerrit..."
curl -sf -X PUT "${GERRIT_URL}/a/accounts/jenkins" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"Jenkins CI\", \"email\": \"jenkins@localhost\"}" 2>/dev/null || true

# SSH 키 등록
curl -sf -X POST "${GERRIT_URL}/a/accounts/jenkins/sshkeys" \
    -H "Content-Type: text/plain" \
    -d "${JENKINS_PUB_KEY}" 2>/dev/null || true

ok "Gerrit admin setup complete"

# ────────────────────────────────────────────
# 4. Gerrit 프로젝트 생성 + upstream mirror
# ────────────────────────────────────────────
log "=== Creating Gerrit projects ==="

# parent 프로젝트 생성
curl -sf -X PUT "${GERRIT_URL}/a/projects/free5gc" \
    -H "Content-Type: application/json" \
    -d '{"description": "free5gc parent project", "create_empty_commit": true}' 2>/dev/null || true

for nf in $ALL_NFS; do
    local_project="free5gc/${nf}"
    upstream="${UPSTREAM_REPOS[$nf]}"

    log "  Creating project: ${local_project}"

    # Gerrit 프로젝트 생성
    curl -sf -X PUT "${GERRIT_URL}/a/projects/free5gc%2F${nf}" \
        -H "Content-Type: application/json" \
        -d "{\"description\": \"free5gc ${nf} NF\", \"create_empty_commit\": false, \"parent\": \"free5gc\"}" \
        2>/dev/null || true

    # 로컬 소스를 Gerrit에 push (upstream 코드 기반)
    local src_dir="${PROJECT_DIR}/free5gc_source/${nf}"
    if [ -d "$src_dir/.git" ]; then
        cd "$src_dir"

        # Gerrit을 remote로 추가
        git remote remove gerrit 2>/dev/null || true
        git remote add gerrit "http://localhost:8080/a/free5gc/${nf}"

        # upstream 태그 기준으로 main 브랜치 push
        git fetch origin 2>/dev/null || true
        if git rev-parse "${UPSTREAM_TAG}" >/dev/null 2>&1; then
            git checkout "${UPSTREAM_TAG}" 2>/dev/null || true
        fi

        # Gerrit에 push (초기 코드)
        git push gerrit HEAD:refs/heads/main 2>/dev/null || true
        ok "  ${nf}: pushed to Gerrit (tag: ${UPSTREAM_TAG})"

        cd "$SCRIPT_DIR"
    else
        echo "  WARN: ${src_dir} has no .git, skipping push."
    fi
done

# ────────────────────────────────────────────
# 5. Gerrit Verified 레이블 설정
# ────────────────────────────────────────────
log "=== Configuring Verified label ==="

# All-Projects의 project.config에 Verified 레이블 추가
# Gerrit이 refs/meta/config를 사용하므로 git으로 직접 수정
docker exec gerrit bash -c "
    cd /var/gerrit/git/All-Projects.git
    git config --add label.Verified.function MaxWithBlock
    git config --add label.Verified.value '-1 Fails'
    git config --add label.Verified.value '0 No score'
    git config --add label.Verified.value '+1 Verified'
    git config --add label.Verified.defaultValue 0
" 2>/dev/null || log "  Verified label may already exist"

ok "Verified label configured"

# ────────────────────────────────────────────
# 6. 요약
# ────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  CI Channel Setup Complete"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  Gerrit:  ${GERRIT_URL}"
echo "  Jenkins: http://localhost:8081"
echo "  SSH:     ssh -p ${GERRIT_SSH_PORT} ${GERRIT_SSH}"
echo ""
echo "  Projects created:"
for nf in $ALL_NFS; do
    echo "    - free5gc/${nf}"
done
echo ""
echo "  Upstream tag: ${UPSTREAM_TAG}"
echo ""
echo "  Next steps:"
echo "    1. Jenkins UI (http://localhost:8081)에서 Gerrit Trigger 설정"
echo "       - Gerrit Connection: gerrit:29418"
echo "       - Username: jenkins"
echo "       - SSH Key: /var/jenkins_home/.ssh/id_rsa"
echo "    2. Pipeline job 생성 → SCM: Gerrit, Jenkinsfile 경로 지정"
echo "    3. 코드 수정 후 push:"
echo "       cd free5gc_source/{nf}"
echo "       git checkout -b dev/my-feature"
echo "       # ... 수정 ..."
echo "       git add . && git commit -m 'feat: my change'"
echo "       git push gerrit HEAD:refs/for/main"
echo ""
echo "════════════════════════════════════════════════════════"
