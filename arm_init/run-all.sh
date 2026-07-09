#!/bin/bash
# free5gc ARM 전체 파이프라인 (one-shot)
# infra-setup → clone-source → build → docker-build → deploy
#
# 사용: ./run-all.sh [OPTIONS]
#   --skip-infra    infra-setup 건너뛰기 (이미 설치된 경우)
#   --skip-clone    clone-source 건너뛰기 (이미 소스 있는 경우)
#   --from STEP     특정 단계부터 시작 (infra|clone|build|docker|deploy)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# ────────────────────────────────────────────
# 옵션 파싱
# ────────────────────────────────────────────
SKIP_INFRA=false
SKIP_CLONE=false
FROM_STEP="infra"

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-infra) SKIP_INFRA=true; shift ;;
        --skip-clone) SKIP_CLONE=true; shift ;;
        --from)
            FROM_STEP="$2"; shift 2 ;;
        *)
            echo "Usage: $0 [--skip-infra] [--skip-clone] [--from infra|clone|build|docker|deploy]"
            exit 1 ;;
    esac
done

# from 옵션에 따라 skip 설정
case "$FROM_STEP" in
    infra)  ;;
    clone)  SKIP_INFRA=true ;;
    build)  SKIP_INFRA=true; SKIP_CLONE=true ;;
    docker) SKIP_INFRA=true; SKIP_CLONE=true; SKIP_BUILD=true ;;
    deploy) SKIP_INFRA=true; SKIP_CLONE=true; SKIP_BUILD=true; SKIP_DOCKER=true ;;
    *) die "Unknown step: $FROM_STEP (use: infra|clone|build|docker|deploy)" ;;
esac

# ────────────────────────────────────────────
# 실행
# ────────────────────────────────────────────
echo "╔══════════════════════════════════════════╗"
echo "║   free5gc ARM64 - Full Pipeline          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Infra
if [ "$SKIP_INFRA" = false ]; then
    log "━━━ [1/5] infra-setup.sh ━━━"
    bash "$SCRIPT_DIR/infra-setup.sh"
    echo ""
else
    log "━━━ [1/5] infra-setup.sh (skipped) ━━━"
fi

# 2. Clone
if [ "$SKIP_CLONE" = false ]; then
    log "━━━ [2/5] clone-source.sh ━━━"
    bash "$SCRIPT_DIR/clone-source.sh"
    echo ""
else
    log "━━━ [2/5] clone-source.sh (skipped) ━━━"
fi

# 3. Build
if [ "${SKIP_BUILD:-false}" = false ]; then
    log "━━━ [3/5] build.sh ━━━"
    bash "$SCRIPT_DIR/build.sh"
    echo ""
else
    log "━━━ [3/5] build.sh (skipped) ━━━"
fi

# 4. Docker
if [ "${SKIP_DOCKER:-false}" = false ]; then
    log "━━━ [4/5] docker-build.sh ━━━"
    bash "$SCRIPT_DIR/docker-build.sh"
    echo ""
else
    log "━━━ [4/5] docker-build.sh (skipped) ━━━"
fi

# 5. Deploy
log "━━━ [5/5] deploy.sh ━━━"
bash "$SCRIPT_DIR/deploy.sh"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Pipeline complete!                     ║"
echo "╚══════════════════════════════════════════╝"
echo ""
log "Verify: ./arm_script/test-connectivity.sh"
