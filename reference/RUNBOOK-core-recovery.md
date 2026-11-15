# free5GC 코어 복구 런북 (DiskPressure 연쇄 장애)

> 2026-11-15 실제 복구 기록. 단일 노드 ARM64(Neoverse-N1, 4 vCPU, K8s v1.32.3,
> containerd 2.2.1, Calico + Multus/ipvlan). observer-effect 실험을 위해 UPF 데이터패스를
> 되살리는 과정에서 겪은 전체 장애 체인과 해결책.

## 증상
- `kubectl get pods -n free5gc`에 Running이 **0개**, Evicted/Init:ContainerStatusUnknown
  파드가 **4,800개 이상** 누적.
- 모든 코어 파드가 `FailedScheduling ... untolerated taint {node.kubernetes.io/disk-pressure}`.
- UPF 없음 → `upfgtp` GTP 터널 디바이스 없음 → 데이터패스 불능.

## 근본 원인 (연쇄)
1. 디스크 사용률 88% 도달 → kubelet이 **DiskPressure=True** 선언.
2. kubelet이 노드에 `node.kubernetes.io/disk-pressure:NoSchedule` **taint** 부착.
3. free5GC 파드가 이 taint를 toleration하지 않아 **스케줄 거부** + 기존 파드 **Evict**.
4. Deployment가 새 레플리카를 계속 생성 → 또 스케줄 실패 → **4,800+ 유령 파드 누적**
   (유령 파드 메타데이터/로그가 디스크를 더 먹는 **악순환**).
5. 디스크 압박 중 kubelet이 **컨테이너 이미지 GC** → `arm-curl:*` 로컬 이미지 전부 삭제됨
   (`imagePullPolicy: Never`라 재획득 불가 → `ErrImageNeverPull`).
6. 유령 파드들이 **Calico IPAM 풀(/26, 64개) 고갈** + **host-local ipvlan IP 예약 누수**.
7. Multus 데몬/`dynamic-networks-controller` 손상 → 신규 파드 sandbox 생성 실패.

## 복구 절차 (순서 중요)

### 1. 디스크 확보 (DiskPressure 해제가 최우선)
```bash
# journal 로그 정리 (보통 가장 큰 즉효)
sudo journalctl --vacuum-size=200M          # 예: 2.7G 회수

# 유령 파드 대량 삭제 (Deployment는 보존되므로 레플리카는 1개씩 재생성됨)
kubectl delete pods -n free5gc --field-selector=status.phase=Failed    --force --grace-period=0
kubectl delete pods -n free5gc --field-selector=status.phase=Succeeded --force --grace-period=0
kubectl delete pods -n free5gc --field-selector=status.phase!=Running  --force --grace-period=0
kubectl delete pods -n openebs --field-selector=status.phase!=Running  --force --grace-period=0

# 오래된 kubeadm etcd 백업 (안전) + docker 미사용 이미지
sudo rm -rf /etc/kubernetes/tmp/*           # 과거 kubeadm-backup-etcd-* (2.1G)
sudo docker image prune -af                 # active 이미지는 보존
```
목표: 사용률을 **80% 이하**로. (kubelet eviction 임계가 ~85%라 84~85%에서 flapping함.)

### 2. DiskPressure taint 해제
```bash
# transition period(기본 5분) 기다리거나, kubelet 재시작으로 즉시 재평가
sudo systemctl restart kubelet
kubectl describe node | grep -iE "Taints:|DiskPressure"   # False / <none> 확인
```

### 3. GC된 컨테이너 이미지 재주입 (빌드 불필요 — docker에 남아있음)
```bash
sudo docker images | grep arm-curl         # docker 저장소엔 보통 남아있음
for tag in curl nrf amf ausf pcf udr udm nssf smf upf; do
  sudo docker save arm-curl:$tag | sudo ctr -n k8s.io images import -
done
sudo ctr -n k8s.io images ls -q | grep arm-curl   # 확인
```
docker에도 없으면: `arm_docker/core_images/setup.sh build && ... import`.

### 4. Multus / dynamic-networks-controller 복구
```bash
kubectl delete pod -n kube-system -l app=multus --force --grace-period=0
kubectl delete pod -n kube-system <dynamic-networks-controller-...> --force --grace-period=0
kubectl get pods -n kube-system | grep -iE "multus|network-controller"   # 1/1 Running
```

### 5. Calico IPAM 풀 고갈 회수
```bash
# calicoctl(노드 버전 일치) 다운로드
CALICO_VER=$(kubectl get pod -n kube-system -l k8s-app=calico-node \
  -o jsonpath='{.items[0].spec.containers[0].image}' | grep -oE 'v[0-9.]+')
curl -sL -o /tmp/calicoctl \
  "https://github.com/projectcalico/calico/releases/download/${CALICO_VER}/calicoctl-linux-arm64"
chmod +x /tmp/calicoctl
export DATASTORE_TYPE=kubernetes KUBECONFIG=/etc/kubernetes/admin.conf

sudo -E /tmp/calicoctl ipam show                              # 64/64 100% 확인
sudo -E /tmp/calicoctl ipam check -o /tmp/ipam-report.json
sudo -E /tmp/calicoctl ipam release --from-report=/tmp/ipam-report.json --force
# update conflict가 나면 check→release 재실행 (리포트 최신화)
```

### 6. host-local ipvlan IP 예약 누수 정리
```bash
# 현재 활성 free5GC 파드가 없을 때만 안전
for n in n2network n3network n4network n3network-ipvlan n4network-ipvlan; do
  sudo find /var/lib/cni/networks/$n/ -maxdepth 1 -name '10.*' -delete
  sudo rm -f /var/lib/cni/networks/$n/last_reserved_ip.0
done
```

### 7. ★핵심 버그: NAD rangeStart vs UPF 고정 IP 불일치
UPF는 N3=`10.10.3.1/24`, N4=`10.10.4.1/24` **고정 IP**를 요구(파드 annotation).
그런데 적용된 NAD(`network-attachments-ipvlan.yaml`)의 `rangeStart`가 **`.10`**이라
`.1`이 **범위 밖 → host-local이 할당 거부** → `failed to allocate all requested IPs: 10.10.3.1`
→ sandbox 생성 영구 실패.

- 과거 작동하던 `ipvlan-networks.yaml`은 rangeStart=`.1`이었음 (두 파일 불일치가 원인).
- **수정**: n3/n4 NAD의 rangeStart를 `.1`로. gateway는 `.254`라 `.1`과 충돌 없음.

라이브 수정:
```bash
for net in n3network:10.10.3.1 n4network:10.10.4.1; do
  name=${net%%:*}; start=${net##*:}
  kubectl get net-attach-def $name -n free5gc -o json | python3 -c "
import sys,json
d=json.load(sys.stdin); c=json.loads(d['spec']['config'])
c['ipam']['rangeStart']='$start'; d['spec']['config']=json.dumps(c)
print(json.dumps({'spec':{'config':d['spec']['config']}}))" \
  | kubectl patch net-attach-def $name -n free5gc --type=merge -p "$(cat -)"
done
```
영속화: `arm_k8s/networks5g/network-attachments-ipvlan.yaml`의 n3/n4 rangeStart를 `.1`로,
그리고 `arm_k8s/setup.sh`의 `update_nad_subnet`이 n3/n4에 대해 rangeStart=`.1`,
gateway=`.254`를 쓰도록 수정 완료(2026-11-15).

### 8. 멈춘 NF 재생성 → 의존성 체인 기동
```bash
kubectl delete pods -n free5gc --field-selector=status.phase!=Running --force --grace-period=0
# 의존성 순서: mongodb → nrf → amf → ausf/... → smf → upf
watch kubectl get pods -n free5gc
```

## 데이터패스 작동 검증 (복구 성공 기준)
```bash
UPF=$(kubectl get pod -n free5gc -l nf=upf -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n free5gc $UPF -- ip -brief addr      # upfgtp / n3=10.10.3.1 / n4=10.10.4.1
kubectl logs $UPF -n free5gc --tail=5 | grep PFCP   # handleHeartbeatRequest (N4 세션 live)
lsmod | grep gtp5g                                  # UE PDU 세션 생기면 refcount>0
```

## 예방
- 디스크 모니터링/알람 80% 선에서. journal `SystemMaxUse` 제한 설정 권장.
- `imagePullPolicy: Never` + 로컬 이미지 조합은 이미지 GC에 취약 → 레지스트리 미러 또는
  이미지 백업(`docker save`) 상시 보관.
- 유령 파드 누적 방지: Deployment 레벨에서 스케줄 실패가 무한 재생성되지 않도록 모니터링.

## 환경 사실 (실험 전제)
- aarch64 Neoverse-N1, 4 vCPU, 커널 6.8.0-1058-oracle.
- gtp5g 모듈 로드됨, BTF 존재(`/sys/kernel/btf/vmlinux`) → eBPF CO-RE 가능, perf 가용.
- UPF 고정 IP: N3=10.10.3.1, N4=10.10.4.1 (subnet /24).
