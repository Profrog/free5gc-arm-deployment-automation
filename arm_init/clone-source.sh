#!/bin/bash
# free5gc NF별 소스 clone
# 각 NF 레포를 free5gc_source/{nf}/ 디렉토리에 clone
#
# 사용: ./clone-source.sh [VERSION]
#   예: ./clone-source.sh v3.4.3
#       ./clone-source.sh          (기본: main branch)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SOURCE_DIR="$PROJECT_DIR/free5gc_source"

# NF 목록 및 레포 매핑
declare -A NF_REPOS=(
    [nrf]="https://github.com/free5gc/nrf.git"
    [amf]="https://github.com/free5gc/amf.git"
    [ausf]="https://github.com/free5gc/ausf.git"
    [pcf]="https://github.com/free5gc/pcf.git"
    [udr]="https://github.com/free5gc/udr.git"
    [udm]="https://github.com/free5gc/udm.git"
    [nssf]="https://github.com/free5gc/nssf.git"
    [smf]="https://github.com/free5gc/smf.git"
    [upf]="https://github.com/free5gc/go-upf.git"
    [ueransim]="https://github.com/aligungr/UERANSIM.git"
)

VERSION="${1:-}"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }
warn() { echo "[WARN] $1"; }

# ────────────────────────────────────────────
# 로컬 변경사항 확인
# ────────────────────────────────────────────
has_local_changes() {
    local dir="$1"
    cd "$dir"
    # 스테이징/언스테이징된 변경사항 또는 untracked 파일 확인
    if [ -n "$(git status --porcelain)" ]; then
        return 0
    fi
    return 1
}

# ────────────────────────────────────────────
# Clone or update
# ────────────────────────────────────────────
clone_or_update() {
    local nf="$1"
    local repo="$2"
    local dest="$SOURCE_DIR/$nf"

    if [ -d "$dest/.git" ]; then
        # 로컬 변경사항 확인
        if has_local_changes "$dest"; then
            warn "$nf: 로컬에 수정된 파일이 있습니다."
            echo "    $(cd "$dest" && git status --short | head -5)"
            local changed_count=$(cd "$dest" && git status --short | wc -l)
            [ "$changed_count" -gt 5 ] && echo "    ... (+$((changed_count - 5)) more files)"
            echo ""
            read -p "  $nf: 원격 최신 버전으로 덮어쓸까요? (y/N): " answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                log "  $nf: force reset to remote ..."
                cd "$dest"
                git fetch --all --tags
                git checkout -- .
                git clean -fd
                if [ -n "$VERSION" ]; then
                    git checkout "$VERSION" 2>/dev/null || git checkout "origin/main"
                else
                    git checkout main 2>/dev/null || git checkout master
                    git reset --hard origin/main 2>/dev/null || git reset --hard origin/master
                fi
            else
                log "  $nf: 로컬 변경사항 유지, skip."
                return
            fi
        else
            log "  $nf: already cloned, pulling latest ..."
            cd "$dest"
            git fetch --all --tags
            if [ -n "$VERSION" ]; then
                git checkout "$VERSION" 2>/dev/null || git checkout "origin/main"
            else
                git pull origin main 2>/dev/null || git pull
            fi
        fi
    else
        log "  $nf: cloning from $repo ..."
        mkdir -p "$dest"
        if [ -n "$VERSION" ]; then
            git clone --branch "$VERSION" --depth 1 "$repo" "$dest" 2>/dev/null || \
            git clone "$repo" "$dest"
        else
            git clone "$repo" "$dest"
        fi
    fi
}

# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────
log "=== Cloning free5gc NF sources ==="
[ -n "$VERSION" ] && log "  Target version: $VERSION"
log "  Destination: $SOURCE_DIR"
echo ""

mkdir -p "$SOURCE_DIR"

for nf in "${!NF_REPOS[@]}"; do
    clone_or_update "$nf" "${NF_REPOS[$nf]}"
done

echo ""
ok "All NF sources ready at $SOURCE_DIR"
echo ""
log "Directory structure:"
for nf in "${!NF_REPOS[@]}"; do
    if [ -d "$SOURCE_DIR/$nf" ]; then
        local_ver=$(cd "$SOURCE_DIR/$nf" && git describe --tags 2>/dev/null || git rev-parse --short HEAD)
        echo "  $SOURCE_DIR/$nf/ ($local_ver)"
    fi
done
