#!/usr/bin/env bash
# K3 SSH helper: k3ssh.sh <host> <command...>
# OpenWrt 19.07 dropbear only offers ssh-rsa; root has empty password.
HOST="${1:-192.168.1.1}"; shift
printf '\n' | /c/Windows/System32/OpenSSH/ssh.exe \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL \
  -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa \
  -o PreferredAuthentications=password -o PubkeyAuthentication=no \
  -o ConnectTimeout=8 root@"$HOST" "$@"
