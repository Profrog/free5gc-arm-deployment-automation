# APN-Based Traffic Profiles

APN 프로파일 기반 트래픽 제네레이터 + 모니터링 환경.

## 핵심 개념

| 개념 | 역할 | 위치 |
|------|------|------|
| **APN (DNN)** | 네트워크 파이프 정의 — 어떤 UPF를 타고, 어떤 IP pool을 쓰는지 | `profiles/apn/` |
| **Scenario** | 트래픽 패턴 정의 — 그 파이프에 뭘 흘릴지 | `profiles/scenarios/` |

APN을 선택하고, 시나리오를 얹어서 실행합니다.

## 구조

```
traffic-profiles/
├── profiles/
│   ├── apn/                    # 네트워크 정의 (고정)
│   │   ├── internet.yaml       #   Slice1, UPF1, 10.1.0.0/16
│   │   └── streaming.yaml      #   Slice2, UPF2, 10.2.0.0/16
│   └── scenarios/              # 트래픽 시나리오 (교체 가능)
│       ├── upf-stress.yaml     #   4-phase UPF 한계 측정
│       ├── iot-burst.yaml      #   IoT 센서 burst
│       ├── vonr.yaml           #   VoNR 음성
│       └── streaming-dl.yaml   #   DL 스트리밍 부하
├── generator/
│   └── traffic-gen.sh          # 트래픽 생성 엔진
├── monitor/
│   ├── monitor-collector.sh    # CPU/Mem/Loss 수집기
│   ├── monitor-visualize.py    # PNG 차트 생성
│   ├── monitor-detect.py       # 이상 탐지
│   └── app.py                  # Streamlit 대시보드
├── k8s/
│   ├── traffic-job.yaml        # K8s Job manifest
│   └── Dockerfile.traffic-gen
├── run.sh                      # 실행 런처 (APN + Scenario → 배포 → 수집 → 시각화)
├── REFERENCES.md               # 벤치마크 근거 논문
└── references.bib              # BibTeX
```

## 사용법

```bash
cd /home/ubuntu/free5gc-k8s-arm/traffic-profiles

# ── 신규 방식: APN + Scenario 조합 ──
./run.sh --apn profiles/apn/internet.yaml --scenario profiles/scenarios/upf-stress.yaml
./run.sh --apn profiles/apn/streaming.yaml --scenario profiles/scenarios/streaming-dl.yaml
./run.sh --apn profiles/apn/internet.yaml --scenario profiles/scenarios/vonr.yaml

# ── 드라이런 ──
./run.sh --apn profiles/apn/internet.yaml --scenario profiles/scenarios/iot-burst.yaml --dry-run

# ── 레거시 (단일 파일) ──
./run.sh profiles/upf-stress.yaml

# ── 결과 확인 ──
ls monitor-data/               # 수집된 시계열 데이터
ls results/                    # iperf3 JSON 결과

# ── Streamlit 대시보드 ──
# http://152.69.227.31:8501

# ── 정리 ──
./run.sh --clean
```

## APN 프로파일 스키마

각 프로파일은 다음을 정의합니다:
- **apn**: APN 이름 (PDU Session DNN)
- **slice**: S-NSSAI (SST/SD)
- **qos**: 5QI, MBR, GBR
- **traffic_pattern**: 패킷 크기, 전송률, 지속시간, 프로토콜
- **ue_count**: 동시 UE 수

## free5GC DNN/Slice 구성 (현재 배포 기준)

| Slice | DNN | SST | SD | UPF | UPF N3 IP | UE Pool | SMF PFCP |
|-------|-----|-----|----|-----|-----------|---------|----------|
| Slice 1 | internet | 1 | 000001 | UPF1 | 10.10.3.1 | 10.1.0.0/16 | 10.10.4.101 |
| Slice 2 | streaming | 1 | 000002 | UPF2 | 10.10.3.2 | 10.2.0.0/16 | 10.10.4.102 |

- PLMN: MCC=001, MNC=01
- gNB N3: 10.10.3.22 / NGAP(N2): 10.10.2.22
- AMF: 10.10.2.107:38412

## 참고문헌

벤치마크 설계 근거 및 논문 레퍼런스: → [REFERENCES.md](./REFERENCES.md)
