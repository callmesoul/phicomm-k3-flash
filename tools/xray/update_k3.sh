#!/usr/bin/env bash
# Refresh the K3 xray config from the subscription.
# Usage: ./update_k3.sh [node-index]   (node-index = which subscription node
#        becomes the main "proxy" outbound, default 0)
# Steps: fetch sub (via K3 proxy) -> regenerate config -> serve on LAN briefly
#        -> K3 pulls it -> validate -> xray restarts -> TUN routes restored.
#
# Configure SUB_URL and the askpass path below before first use.
set -e

NODE_INDEX="${1:-0}"
SUB_URL="https://<your-sub-domain>/api/v1/client/subscribe?token=<YOUR_TOKEN>"
K3="root@192.168.2.1"
SERVE_DIR="$(cd "$(dirname "$0")" && pwd)/serve"
PC_IP="$(ipconfig | tr -d '\r' | sed -n 's/.*IPv4.*: \(192\.168\.2\.[0-9]*\).*/\1/p' | head -1)"

# dropbear needs a TTY-less password: feed it via askpass (k3-askpass.bat reads
# ~/.ssh/k3-pass.txt). Empty-password stdin piping no longer works.
SSH_CMD=(/c/Windows/System32/OpenSSH/ssh.exe
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL
  -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa
  -o PreferredAuthentications=password -o PubkeyAuthentication=no)
export SSH_ASKPASS="$USERPROFILE\.ssh\k3-askpass.bat"
export SSH_ASKPASS_REQUIRE=force

echo "== fetching subscription via K3 proxy =="
curl -s --max-time 60 -x "http://192.168.2.1:7890" "$SUB_URL" -o /tmp/sub_new.yaml
wc -c /tmp/sub_new.yaml

echo "== generating config (main node index $NODE_INDEX) =="
python "$(dirname "$0")/gen_config.py" "$(cygpath -w /tmp/sub_new.yaml)" "$(cygpath -w "$SERVE_DIR/xray-config.json")" "$NODE_INDEX"

echo "== serving config on $PC_IP:8000 (briefly) =="
( cd "$SERVE_DIR" && python -m http.server 8000 --bind "$PC_IP" >/dev/null 2>&1 ) &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT
sleep 2

echo "== pulling into K3, validating and restarting xray =="
MSYS_NO_PATHCONV=1 "${SSH_CMD[@]}" "$K3" "wget -q -O /etc/xray/config.json 'http://$PC_IP:8000/xray-config.json' \
  && XRAY_LOCATION_ASSET=/usr/share/xray /usr/bin/xray run -test -config /etc/xray/config.json \
  && /etc/init.d/xray restart \
  && sleep 3 && sh /etc/xray-tun-routes.sh"

echo "== done =="
curl -s -o /dev/null -w "google via K3: %{http_code}\n" --max-time 30 \
  -x http://192.168.2.1:7890 https://www.google.com/generate_204
