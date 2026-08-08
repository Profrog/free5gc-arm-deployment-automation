# CI_channel — Gerrit + Jenkins CI/CD Pipeline

free5GC NF 로컬 변경의 안정성을 자동 검증하는 CI 파이프라인입니다.

**목적**: NF 소스를 수정했을 때, upstream 기준 전체 5GC 시스템과의 호환성을 자동으로 확인합니다.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Developer Workflow                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  free5gc_source/amf/ 수정                                       │
│       ↓                                                          │
│  git push gerrit HEAD:refs/for/main                             │
│       ↓                                                          │
│  ┌──────────┐    trigger    ┌──────────┐                        │
│  │  Gerrit  │ ────────────→ │ Jenkins  │                        │
│  │ :8080    │               │ :8081    │                        │
│  └──────────┘               └────┬─────┘                        │
│                                  │                               │
│                    ┌─────────────┼─────────────┐                │
│                    ↓             ↓             ↓                │
│              upstream     + cherry-pick   전체 빌드             │
│              checkout       (patch)       + 배포               │
│                    │             │             │                │
│                    └─────────────┼─────────────┘                │
│                                  ↓                               │
│                         Integration Test                         │
│                    (UE 등록, PDU, ping 검증)                    │
│                                  ↓                               │
│                      Gerrit Verified ±1                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 검증 원리

```
free5gc_source/amf  ← upstream v3.4.3 + 내 patch (cherry-pick)
free5gc_source/smf  ← upstream v3.4.3 (그대로)
free5gc_source/nrf  ← upstream v3.4.3 (그대로)
...
              ↓
    전체 빌드 → K8s 배포 → 통합 테스트
              ↓
    "이 변경이 전체 시스템을 깨뜨리는가?"
```

## Quick Start

```bash
# 1. 서비스 시작
cd CI_channel
docker compose up -d

# 2. 초기 설정 (Gerrit 프로젝트 + Jenkins 연동)
./setup.sh

# 3. 코드 수정 & push
cd ../free5gc_source/amf
git checkout -b dev/my-feature
# ... 코드 수정 ...
git add . && git commit -m "feat: my change"
git push gerrit HEAD:refs/for/main

# 4. Jenkins가 자동으로 빌드/테스트 → Gerrit에 Verified ±1
```

## File Structure

```
CI_channel/
├── docker-compose.yml        # Gerrit + Jenkins 컨테이너
├── gerrit/
│   └── etc/
│       └── gerrit.config     # Gerrit 설정 (auth, SSH, plugins)
├── jenkins/
│   ├── Dockerfile            # Jenkins + Go + Docker CLI + kubectl
│   └── plugins.txt           # Gerrit trigger, pipeline 등
├── Jenkinsfile               # CI 파이프라인 정의
├── setup.sh                  # 초기 설정 자동화
└── README.md
```

## Services

| Service | Port | URL | 용도 |
|---------|------|-----|------|
| Gerrit | 8080, 29418 | http://localhost:8080 | 코드 리뷰 + Git 호스팅 |
| Jenkins | 8081 | http://localhost:8081 | CI 빌드/테스트 자동화 |

## Pipeline Stages

| Stage | 설명 |
|-------|------|
| Detect NF | Gerrit project에서 대상 NF 자동 감지 |
| Checkout & Apply Patch | upstream tag checkout + Gerrit patchset cherry-pick |
| Build NF | Go build (또는 C++ cmake for UERANSIM) |
| Docker Build | arm-curl:{nf} 이미지 빌드 + containerd import |
| Deploy to K8s | 해당 NF pod rolling restart |
| Integration Test | test-connectivity.sh (UE 등록 ~ ping) |
| Gerrit Verify | Verified +1/-1 리포트 |

## Gerrit Project Structure

```
Gerrit
├── free5gc/            (parent project)
│   ├── free5gc/nrf
│   ├── free5gc/amf
│   ├── free5gc/ausf
│   ├── free5gc/pcf
│   ├── free5gc/udr
│   ├── free5gc/udm
│   ├── free5gc/nssf
│   ├── free5gc/smf
│   ├── free5gc/upf
│   └── free5gc/ueransim
```

각 프로젝트의 `main` 브랜치 = upstream 태그 고정 (기준점)

## 개발 워크플로우

### 1. NF 수정

```bash
cd free5gc_source/amf
git checkout -b dev/fix-registration
# 코드 수정
git add -A
git commit -m "fix: registration timeout handling"
```

### 2. Gerrit에 리뷰 요청

```bash
git push gerrit HEAD:refs/for/main
```

### 3. 자동 검증

Jenkins가 자동으로:
1. upstream v3.4.3 기준 checkout
2. 내 patch를 cherry-pick
3. 빌드 + Docker 이미지 + K8s 배포
4. 전체 통합 테스트 (UE 등록, PDU 세션, ping)
5. Gerrit에 Verified +1 (pass) / -1 (fail) 리포트

### 4. 코드 리뷰 & 머지

Gerrit UI에서 Code-Review +2 → Submit

## 초기 설정 상세

### Gerrit 첫 접속

Gerrit은 `DEVELOPMENT_BECOME_ANY_ACCOUNT` 모드로 설정되어 있어 인증 없이 접속 가능합니다.

1. http://localhost:8080 접속
2. 우측 상단 → "Become" 클릭 → "admin" 선택 (첫 번째 계정이 admin)
3. Settings → SSH Keys에서 필요시 추가 키 등록

### Jenkins Gerrit Trigger 설정

`setup.sh` 실행 후, Jenkins UI에서 다음을 설정합니다:

1. **Gerrit Connection 추가**
   - Jenkins 관리 → 시스템 설정 → Gerrit Trigger
   - Hostname: `gerrit` (Docker 네트워크 내부) 또는 `localhost` (호스트에서)
   - Frontend URL: `http://gerrit:8080`
   - SSH Port: `29418`
   - Username: `jenkins`
   - SSH Keyfile: `/var/jenkins_home/.ssh/id_rsa`
   - "Test Connection" 클릭 → 성공 확인

2. **Pipeline Job 생성**
   - New Item → Pipeline
   - Build Triggers → Gerrit event 체크
     - Trigger on: Patchset Created
     - Gerrit Project: `free5gc/**` (pattern type: Path)
     - Branch: `**`
   - Pipeline → Definition: "Pipeline script from SCM" 또는 직접 붙여넣기
     - SCM 사용 시: Jenkinsfile 경로 = `CI_channel/Jenkinsfile`
     - 직접 입력 시: `CI_channel/Jenkinsfile` 내용 복사

### Git commit-msg hook 설치 (필수)

Gerrit은 모든 커밋에 `Change-Id`가 필요합니다. 각 NF 소스에 hook을 설치해야 합니다:

```bash
# 단일 NF에 설치
cd free5gc_source/amf
scp -p -P 29418 localhost:/hooks/commit-msg .git/hooks/

# 전체 NF에 일괄 설치
for nf in nrf amf ausf pcf udr udm nssf smf upf ueransim; do
    scp -p -P 29418 localhost:/hooks/commit-msg \
        free5gc_source/${nf}/.git/hooks/
done
```

이후 `git commit` 시 자동으로 `Change-Id: I...` 라인이 추가됩니다.

### Gerrit remote 확인

`setup.sh`가 자동으로 추가하지만, 수동으로 확인/추가하려면:

```bash
cd free5gc_source/amf
git remote -v
# gerrit  http://localhost:8080/a/free5gc/amf (fetch)
# origin  https://github.com/free5gc/amf.git (fetch)

# 없으면 수동 추가
git remote add gerrit http://localhost:8080/a/free5gc/amf
```

## Configuration

### upstream 태그 변경

```bash
# setup.sh 실행 시 태그 지정
./setup.sh v3.4.4
```

### Jenkins 수동 빌드 트리거

Jenkins UI → Build with Parameters:
- `NF_NAME`: amf, smf, upf 등
- `UPSTREAM_TAG`: 기준 태그

## 관리

```bash
# 서비스 상태
docker compose ps

# 로그 확인
docker compose logs -f gerrit
docker compose logs -f jenkins

# 중지
docker compose down

# 데이터 포함 완전 삭제
docker compose down -v
```

## 요구사항

- Docker + Docker Compose
- ARM64 호스트 (aarch64)
- K8s 클러스터 (kubectl 접근 가능)
- free5gc_source/ 디렉토리에 NF 소스 존재 (`clone-source.sh` 실행 완료)

## Troubleshooting

### Gerrit 시작이 느림

첫 실행 시 인덱스 빌드로 1~2분 소요됩니다. `docker compose logs -f gerrit`에서 `Gerrit Code Review ... ready`를 확인하세요.

### 포트 충돌

```bash
# 8080 또는 8081이 사용 중인 경우
sudo lsof -i :8080
# docker-compose.yml에서 포트 변경: "9080:8080" 등
```

### Jenkins에서 Gerrit 연결 실패

```bash
# SSH 키 확인
docker exec jenkins cat /var/jenkins_home/.ssh/id_rsa.pub
# Gerrit에 해당 키가 등록되어 있는지 확인
# 네트워크 확인
docker exec jenkins ssh -p 29418 jenkins@gerrit gerrit version
```

### Cherry-pick conflict

파이프라인에서 conflict 발생 시 Verified -1이 됩니다. Gerrit UI에서 해당 Change를 리베이스하세요:
- Change 페이지 → "Rebase" 클릭
- 또는 로컬에서 리베이스 후 다시 push

### Change-Id 누락 에러

```
remote: ERROR: missing Change-Id in message footer
```

commit-msg hook이 설치되지 않은 경우입니다:
```bash
scp -p -P 29418 localhost:/hooks/commit-msg \
    free5gc_source/{nf}/.git/hooks/
# 기존 커밋 수정
git commit --amend  # Change-Id가 자동 추가됨
```

### Docker 빌드 시 containerd import 실패

```bash
# containerd 상태 확인
sudo systemctl status containerd
# 수동 import
docker save arm-curl:amf | sudo ctr -n k8s.io images import -
```
