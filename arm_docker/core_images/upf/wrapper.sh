#!/bin/bash
# UPF 시작 전 네트워크 규칙 설정
iptables -A FORWARD -j ACCEPT
iptables -t nat -A POSTROUTING -s 10.1.0.0/16 -o eth0 -j MASQUERADE

exec /free5gc/upf --config /free5gc/config/upfcfg.yaml
