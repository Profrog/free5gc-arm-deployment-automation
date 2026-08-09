# NWDAF — AnLF (Analytics Logical Function)

3GPP TS 23.288 기반 NWDAF AnLF. 온라인 추론 + 전환 실행.

## 역할

1. **수집** — UPF KPI 읽기 (throughput, pps, loss, cpu)
2. **판단** — 학습된 모델로 최적 인터페이스 추론 (ipvlan vs macvlan)
3. **조치** — 판단 결과 ≠ 현재 상태이면 전환 실행

## 사용법

```bash
# 엔진 실행 (실시간 수집 → 추론 → 전환)
python3 nwdaf-engine.py

# dry-run (판단만, 전환 안 함)
python3 nwdaf-engine.py --dry-run

# 수동 전환
./nwdaf-switch.sh ipvlan
./nwdaf-switch.sh macvlan
./nwdaf-switch.sh status
```

## 전환 메커니즘

Pod/프로세스 재시작 없이, 커널 수준 IP 이동으로 무중단 전환:

```
ip -batch - <<EOF
addr del 10.10.3.1/24 dev n3     # macvlan에서 IP 제거
addr add 10.10.3.1/24 dev n3i    # ipvlan에 IP 부여
EOF
```

전환 시간: ~140ms (kubectl exec 포함), 커널 내부 gap: 수 μs

## 파일

| 파일 | 역할 |
|------|------|
| `nwdaf-engine.py` | 메인 엔진 (수집→추론→전환 루프) |
| `nwdaf-switch.sh` | 전환 실행 스크립트 |
| `model/nwdaf-classifier.pkl` | 학습된 모델 (ml-training에서 생성) |
