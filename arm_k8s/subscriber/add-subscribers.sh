#!/bin/bash
# MongoDB에 free5GC subscriber 데이터 투입
# 실행: ./add-subscribers.sh [add|delete|list]
set -e

NAMESPACE="free5gc"
MONGO_SVC="mongodb-service"
MONGO_PORT="27017"
DB="free5gc"

log() { echo "[$(date '+%H:%M:%S')] $1"; }
ok()  { echo "[OK] $1"; }

# MongoDB pod 이름 조회
mongo_pod() {
    kubectl get pod -n "$NAMESPACE" -l app=mongodb -o jsonpath='{.items[0].metadata.name}'
}

# ────────────────────────────────────────────
# subscriber 데이터 정의
# IMSI, key, opc, slice 정보를 여기서 관리
# ────────────────────────────────────────────
SUBSCRIBERS=(
    "imsi-001010000000001 465B5CE8B199B49FAA5F0A2EE238A6BC E8ED289DEBA952E4283B54E88E6183CA 1 000001"
    "imsi-001010000000002 465B5CE8B199B49FAA5F0A2EE238A6BC E8ED289DEBA952E4283B54E88E6183CA 1 000002"
)
# 형식: "imsi key opc sst sd"

# ────────────────────────────────────────────
# subscriber 1건 추가 (mongosh)
# ────────────────────────────────────────────
add_one() {
    local imsi="$1" key="$2" opc="$3" sst="$4" sd="$5"
    local pod
    pod=$(mongo_pod) || { echo "ERROR: mongodb pod not found"; return 1; }

    log "Adding $imsi ..."
    kubectl exec -n "$NAMESPACE" "$pod" -- mongosh "$DB" --quiet --eval "
db.subscribers.updateOne(
  { ueId: '$imsi', plmnID: '00101' },
  { \$set: {
      ueId: '$imsi',
      plmnID: '00101',
      authenticationSubscription: {
        authenticationMethod: '5G_AKA',
        permanentKey: { permanentKeyValue: '$key', encryptionKey: 0, encryptionAlgorithm: 0 },
        sequenceNumber: '000000000023',
        authenticationManagementField: '8000',
        milenage: { op: { opValue: '', encryptionKey: 0, encryptionAlgorithm: 0 } },
        opc: { opcValue: '$opc', encryptionKey: 0, encryptionAlgorithm: 0 }
      },
      accessAndMobilitySubscriptionData: {
        gprsSubscriptionData: null,
        nssai: {
          defaultSingleNssais: [{ sst: $sst, sd: '$sd' }],
          singleNssais: []
        },
        subscribedUeAmbr: { uplink: '1 Gbps', downlink: '2 Gbps' }
      },
      sessionManagementSubscriptionData: [{
        singleNssai: { sst: $sst, sd: '$sd' },
        dnnConfigurations: {
          internet: {
            pduSessionTypes: { defaultSessionType: 'IPV4', allowedSessionTypes: ['IPV4'] },
            sscModes: { defaultSscMode: 'SSC_MODE_1', allowedSscModes: ['SSC_MODE_2','SSC_MODE_3'] },
            '5gQosProfile': { '5qi': 9, arp: { priorityLevel: 8 }, priorityLevel: 8 },
            sessionAmbr: { uplink: '1000 Mbps', downlink: '1000 Mbps' }
          }
        }
      }],
      smfSelectionSubscriptionData: {
        subscribedSnssaiInfos: { '0${sst}${sd}': { dnnInfos: [{ dnn: 'internet' }] } }
      },
      amPolicyData: { subscCats: ['free5gc'] },
      smPolicyData: { smPolicySnssaiData: { '0${sst}${sd}': { snssai: { sst: $sst, sd: '$sd' }, smPolicyDnnData: { internet: { dnn: 'internet' } } } } },
      flowRules: []
  }},
  { upsert: true }
);
print('done');
"
    ok "$imsi added"
}

add_all() {
    log "=== Adding subscribers ==="
    for entry in "${SUBSCRIBERS[@]}"; do
        read -r imsi key opc sst sd <<< "$entry"
        add_one "$imsi" "$key" "$opc" "$sst" "$sd"
    done
    ok "All subscribers added"
}

delete_all() {
    local pod
    pod=$(mongo_pod) || { echo "ERROR: mongodb pod not found"; exit 1; }
    log "=== Deleting all subscribers ==="
    kubectl exec -n "$NAMESPACE" "$pod" -- mongosh "$DB" --quiet --eval \
        "db.subscribers.deleteMany({}); print('deleted: ' + db.subscribers.countDocuments());"
}

list_all() {
    local pod
    pod=$(mongo_pod) || { echo "ERROR: mongodb pod not found"; exit 1; }
    log "=== Subscriber list ==="
    kubectl exec -n "$NAMESPACE" "$pod" -- mongosh "$DB" --quiet --eval \
        "db.subscribers.find({},{ueId:1,plmnID:1,_id:0}).forEach(d=>print(JSON.stringify(d)));"
}

case "${1:-add}" in
    add)    add_all ;;
    delete) delete_all ;;
    list)   list_all ;;
    *)
        echo "Usage: $0 [add|delete|list]"
        echo "  add    - SUBSCRIBERS 배열의 모든 UE 등록 (upsert)"
        echo "  delete - 전체 subscriber 삭제"
        echo "  list   - 등록된 subscriber 목록 출력"
        ;;
esac
