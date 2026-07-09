#!/bin/bash
# free5gc NF 빌드
# free5gc_source/{nf}/에서 빌드하여 free5gc_build/{nf}/{nf} 바이너리로 출력
#
# 사용: ./build.sh [NF_NAME...]
#   예: ./build.sh              (전체 NF 빌드)
#       ./build.sh amf smf      (특정 NF만 빌드)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SOURCE_DIR="$PROJECT_DIR/free5gc_source"
BUILD_DIR="$PROJECT_DIR/free5gc_build"

# 전체 NF 목록
ALL_NFS="nrf amf ausf pcf udr udm nssf smf upf ueransim"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }
die() { echo "[ERROR] $1"; exit 1; }

# Go PATH 설정
export PATH=$PATH:/usr/local/go/bin
export GOPATH=${GOPATH:-$HOME/go}

# ────────────────────────────────────────────
# 사전 조건
# ────────────────────────────────────────────
command -v go &>/dev/null || die "go not found. Run arm_init/infra-setup.sh first."
[ -d "$SOURCE_DIR" ] || die "Source directory not found: $SOURCE_DIR\n  Run arm_init/clone-source.sh first."

# ────────────────────────────────────────────
# 빌드 대상 결정
# ────────────────────────────────────────────
if [ $# -gt 0 ]; then
    BUILD_NFS="$*"
else
    BUILD_NFS="$ALL_NFS"
fi

# ────────────────────────────────────────────
# NF 빌드
# ────────────────────────────────────────────
# ────────────────────────────────────────────
# UERANSIM 빌드 (C++ / cmake + make)
# ────────────────────────────────────────────
build_ueransim() {
    local src_dir="$1"
    local out_dir="$2"

    log "  Building ueransim (C++) ..."
    log "    src: $src_dir"
    log "    out: $out_dir"

    cd "$src_dir"
    mkdir -p build && cd build
    cmake ..
    make -j$(nproc)

    mkdir -p "$out_dir"
    cp "$src_dir/build/nr-gnb" "$out_dir/nr-gnb"
    cp "$src_dir/build/nr-ue" "$out_dir/nr-ue"
    chmod +x "$out_dir/nr-gnb" "$out_dir/nr-ue"

    ok "  ueransim built (nr-gnb: $(du -h "$out_dir/nr-gnb" | cut -f1), nr-ue: $(du -h "$out_dir/nr-ue" | cut -f1))"
}

# ────────────────────────────────────────────
# NF 빌드 (Go)
# ────────────────────────────────────────────
build_nf() {
    local nf="$1"
    local src_dir="$SOURCE_DIR/$nf"
    local out_dir="$BUILD_DIR/$nf"

    [ -d "$src_dir" ] || die "Source not found: $src_dir\n  Run: ./clone-source.sh"

    # UERANSIM은 C++ 프로젝트 (make 빌드)
    if [ "$nf" = "ueransim" ]; then
        build_ueransim "$src_dir" "$out_dir"
        return
    fi

    local out_bin="$out_dir/$nf"

    # cmd 디렉토리 찾기
    local cmd_dir=""
    if [ -d "$src_dir/cmd" ]; then
        cmd_dir="$src_dir/cmd"
    elif [ -d "$src_dir/cmd/main" ]; then
        cmd_dir="$src_dir/cmd/main"
    else
        die "Cannot find cmd directory in $src_dir"
    fi

    # main.go 위치 확인
    local main_file=""
    if [ -f "$cmd_dir/main.go" ]; then
        main_file="$cmd_dir/main.go"
    elif [ -f "$cmd_dir/$nf/main.go" ]; then
        main_file="$cmd_dir/$nf/main.go"
        cmd_dir="$cmd_dir/$nf"
    else
        # fallback: cmd 아래에서 main.go 탐색
        main_file=$(find "$cmd_dir" -name "main.go" -type f | head -1)
        [ -n "$main_file" ] || die "Cannot find main.go in $cmd_dir"
        cmd_dir=$(dirname "$main_file")
    fi

    log "  Building $nf ..."
    log "    src: $cmd_dir"
    log "    out: $out_bin"

    mkdir -p "$out_dir"
    cd "$cmd_dir"
    CGO_ENABLED=0 go build -ldflags "-s -w" -o "$out_bin" main.go
    chmod +x "$out_bin"

    local size=$(du -h "$out_bin" | cut -f1)
    ok "  $nf built ($size)"
}

# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────
log "=== Building free5gc NFs ==="
log "  Source: $SOURCE_DIR"
log "  Output: $BUILD_DIR"
log "  Targets: $BUILD_NFS"
echo ""

FAILED=""
SUCCEEDED=""

for nf in $BUILD_NFS; do
    if build_nf "$nf"; then
        SUCCEEDED="$SUCCEEDED $nf"
    else
        FAILED="$FAILED $nf"
        echo "[WARN] Failed to build $nf, continuing ..."
    fi
done

echo ""
echo "════════════════════════════════════════"
if [ -z "$FAILED" ]; then
    ok "All NFs built successfully"
else
    echo "[WARN] Failed:$FAILED"
    echo "[OK] Succeeded:$SUCCEEDED"
fi
echo ""
log "Binaries:"
for nf in $BUILD_NFS; do
    if [ "$nf" = "ueransim" ]; then
        for bin in "$BUILD_DIR/ueransim/nr-gnb" "$BUILD_DIR/ueransim/nr-ue"; do
            [ -f "$bin" ] && echo "  $bin ($(du -h "$bin" | cut -f1))"
        done
    else
        bin="$BUILD_DIR/$nf/$nf"
        [ -f "$bin" ] && echo "  $bin ($(du -h "$bin" | cut -f1))"
    fi
done
