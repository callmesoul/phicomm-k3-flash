#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate xray config.json from the subscription node list.

Usage: python gen_config.py <subscription-file> <output-config> [main-node-index]

Design (verified working on K3, 2026-11-23):
  - TUN inbound (tun0, 10.0.0.1/16): LAN clients are marked 2 in mangle and
    policy-routed into the TUN (see /etc/firewall.user + /etc/xray-tun-routes.sh).
  - DNS: dnsmasq forwards everything to 10.0.0.2:53 -> tun-in:53 -> dns-out ->
    built-in DNS module: CN answers via 223.5.5.5 (expectIPs geoip:cn), foreign
    fall through to 8.8.8.8 via the proxy. NOTE: no skipFallback on 8.8.8.8 -
    with skipFallback the server never joins the fallback chain (v26 behavior)
    and foreign domains break.
  - hosts: node domains are static-mapped to IPs so resolving the proxy's own
    address never depends on the proxied DNS (bootstrap loop).
  - Routing: dns module connections to CN resolvers go direct, the rest via
    proxy; client traffic splits on geoip:cn/private -> direct, else proxy.
"""
import base64
import json
import socket
import sys

SUB = sys.argv[1]
OUT = sys.argv[2]
MAIN_NODE = int(sys.argv[3]) if len(sys.argv) > 3 else 0


def decode_body(path):
    raw = open(path, encoding='utf-8', errors='replace').read().strip()
    try:
        return base64.b64decode(raw + '===').decode('utf-8', 'replace')
    except Exception:
        return raw  # already plain


def resolve_host(addr):
    """Return addr -> IP mapping for the hosts table (None if not a domain)."""
    if not addr or ':' in addr:
        return None  # empty or IPv6 literal
    if addr.replace('.', '').isdigit():
        return None  # already an IPv4 literal
    try:
        return {addr: socket.gethostbyname(addr)}
    except Exception:
        print('WARN: cannot resolve %s, leaving it out of hosts (proxy may '
              'fail to bootstrap)' % addr, file=sys.stderr)
        return None


def main():
    body = decode_body(SUB)
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    outbounds, hosts = [], {}
    for i, l in enumerate(lines):
        if not l.startswith('vmess://'):
            continue
        d = json.loads(base64.b64decode(l[8:] + '===').decode())
        tag = 'node-%02d' % i
        settings = {"vnext": [{
            "address": d.get('add'), "port": int(d.get('port', 0)),
            "users": [{"id": d.get('id'), "alterId": int(d.get('aid', 0)),
                       "security": d.get('scy') or 'auto'}],
        }]}
        h = resolve_host(d.get('add'))
        if h:
            hosts.update(h)
        net = d.get('net', 'tcp')
        stream = None
        if net == 'ws':
            stream = {"network": "ws", "wsSettings": {
                "path": d.get('path', '/'),
                "headers": {"Host": d.get('host')} if d.get('host') else {},
            }}
            if d.get('tls') == 'tls':
                stream['security'] = 'tls'
                if d.get('host'):
                    stream['tlsSettings'] = {"serverName": d.get('host')}
        elif net == 'grpc':
            stream = {"network": "grpc", "grpcSettings": {
                "serviceName": d.get('path', '').strip('/') or 'GunService',
            }}
        ob = {"tag": tag, "protocol": "vmess", "settings": settings}
        if stream:
            ob["streamSettings"] = stream
        outbounds.append(ob)

    # xray routes unmatched traffic to the FIRST outbound -> the main node
    # doubles as the default "proxy" outbound and must lead the list.
    # (v26 removed the loadbalancer protocol; node switching = regenerate config)
    if not outbounds:
        raise SystemExit('no vmess nodes in subscription')
    main = outbounds.pop(min(MAIN_NODE, len(outbounds) - 1))
    main['tag'] = 'proxy'
    main['mux'] = {'enabled': True}
    # mark 1: xray's own outbound sockets bypass policy routing into the TUN
    main.setdefault('streamSettings', {})['sockopt'] = {'mark': 1}
    outbounds = [main] + outbounds
    outbounds.append({"tag": "direct", "protocol": "freedom"})
    outbounds.append({"tag": "dns-out", "protocol": "dns",
                      "streamSettings": {"sockopt": {"mark": 1}}})

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "tun-in", "protocol": "tun",
             "settings": {"name": "tun0", "mtu": 1500,
                          "gateway": ["10.0.0.1/16"]},
             "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}},
            {"tag": "http-in", "listen": "0.0.0.0", "port": 7890,
             "protocol": "http"},
            {"tag": "socks-in", "listen": "0.0.0.0", "port": 7891,
             "protocol": "socks", "settings": {"auth": "noauth", "udp": True}},
            # legacy REDIRECT target (unused by the TUN design, kept for parity)
            {"tag": "transparent", "listen": "0.0.0.0", "port": 12345,
             "protocol": "dokodemo-door",
             "settings": {"network": "tcp", "followRedirect": True},
             "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}},
        ],
        "outbounds": outbounds,
        "routing": {"rules": [
            # DNS queries arriving via the TUN gateway go to the DNS module
            {"type": "field", "inboundTag": ["tun-in"], "port": 53,
             "outboundTag": "dns-out"},
            # DNS module's upstream connections: CN resolvers direct...
            {"type": "field", "inboundTag": ["dns_inbound"],
             "ip": ["geoip:cn"], "outboundTag": "direct"},
            # ...foreign resolvers via the proxy
            {"type": "field", "inboundTag": ["dns_inbound"],
             "outboundTag": "proxy"},
            # client traffic split
            {"type": "field", "ip": ["geoip:cn", "geoip:private"],
             "outboundTag": "direct"},
        ]},
        "dns": {
            "hosts": hosts,
            "servers": [
                {"address": "223.5.5.5", "expectIPs": ["geoip:cn"]},
                {"address": "8.8.8.8"},
            ],
            "tag": "dns_inbound",
        },
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print('nodes: %d, hosts: %d -> %s' % (len(outbounds) - 2, len(hosts), OUT))


if __name__ == '__main__':
    main()
