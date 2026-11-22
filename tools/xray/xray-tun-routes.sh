#!/bin/sh
# Policy routing for xray TUN (run at boot; waits for tun0)
i=0
while [ $i -lt 30 ] && ! ip link show tun0 >/dev/null 2>&1; do
	sleep 1; i=$((i+1))
done
[ -d /sys/class/net/tun0 ] || { echo "tun0 not up"; exit 1; }
# Xray re-injected traffic (mark 1) must bypass the TUN to avoid loops
ip rule add fwmark 0x1 lookup main pref 10 2>/dev/null
# Only traffic explicitly marked 2 (LAN clients, see /etc/firewall.user) enters the TUN.
# Router-local output stays unmarked -> main table -> never loops into the TUN.
ip route replace default dev tun0 table 100
ip rule add fwmark 0x2 lookup 100 pref 100 2>/dev/null
echo "xray tun routes: up"
