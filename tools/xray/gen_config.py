#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate xray config.json from the subscription node list.

Usage: python gen_config.py <subscription-file> <output-config> [main-node-index]
                            [--domain=javdb.com=6] [--test-ports]

Also importable from auto_select.py: parse_nodes() / build_config().

Design (verified working on K3, 2026-11-23/24):
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
  - Domain rules (--domain=...): emitted BEFORE the geoip rule, so a domain
    like javdb.com can be pinned to a specific node (e.g. a Singapore node)
    regardless of its IP. tun-in sniffs SNI; http-in/socks-in also sniff so
    explicit-proxy users get the same split.
  - sniffing routeOnly: true is REQUIRED. Without it, destOverride rewrites
    the connection target to the sniffed domain, and the geoip:cn rule then
    resolves that domain to get IPs -- Huawei IoT devices connect to CN IPs
    with SNI of hwcloudtest.cn domains that are NXDOMAIN on public DNS, so
    the geoip match got no IPs and the traffic fell through to the proxy
    (overseas IP -> Huawei cloud refuses -> devices offline, 2026-11-24).
    routeOnly keeps the original IP as the target; the sniffed domain is
    still used for the domain rules.
  - Test ports (--test-ports): one HTTP inbound per subscription node on
    0.0.0.0:17900+i with routing test-in-XX -> node-XX. Lets auto_select.py
    benchmark every node through one deployed config (no per-node restarts);
    Clash-style url-test selection lives in auto_select.py.

Deprecated-but-working quirks of v26 the config must keep (do not "fix"):
  - vmess+ws with headers.host (deprecated warnings but functional)
  - loadbalancer protocol no longer exists in v26 -> node switching is done
    by regenerating the config (see auto_select.py / update_k3.sh)
"""
import base64
import json
import socket
import sys

TEST_PORT_BASE = 17900


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


def parse_nodes(sub_path):
    """Return the vmess node dicts in subscription order (skips non-vmess)."""
    body = decode_body(sub_path)
    nodes = []
    for line in (l.strip() for l in body.splitlines() if l.strip()):
        if line.startswith('vmess://'):
            nodes.append(json.loads(base64.b64decode(line[8:] + '===').decode()))
    return nodes


def build_config(nodes, main_idx, domain_rules=None, test_ports=False):
    """Build the full xray config dict.

    nodes: list of vmess dicts (subscription order, index = node id)
    main_idx: index of the node that becomes the default 'proxy' outbound
    domain_rules: {domain: node_index} routed before the geoip rule
    test_ports: add per-node HTTP test inbounds on 17900+i
    """
    domain_rules = domain_rules or {}
    outbounds, hosts = [], {}
    for i, d in enumerate(nodes):
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
    main = outbounds.pop(min(main_idx, len(outbounds) - 1))
    main['tag'] = 'proxy'
    main['mux'] = {'enabled': True}
    # mark 1: xray's own outbound sockets bypass policy routing into the TUN
    main.setdefault('streamSettings', {})['sockopt'] = {'mark': 1}
    outbounds = [main] + outbounds

    def tag_of(idx):
        return 'proxy' if idx == main_idx else 'node-%02d' % idx

    # domain-rule targets need mark 1 as well (their sockets must also
    # bypass policy routing into the TUN)
    for idx in domain_rules.values():
        for ob in outbounds:
            if ob['tag'] == tag_of(idx):
                ob.setdefault('streamSettings', {})['sockopt'] = {'mark': 1}

    outbounds.append({"tag": "direct", "protocol": "freedom"})
    outbounds.append({"tag": "dns-out", "protocol": "dns",
                      "streamSettings": {"sockopt": {"mark": 1}}})

    inbounds = [
        {"tag": "tun-in", "protocol": "tun",
         "settings": {"name": "tun0", "mtu": 1500,
                      "gateway": ["10.0.0.1/16"]},
         "sniffing": {"enabled": True, "destOverride": ["http", "tls"],
                      "routeOnly": True}},
        {"tag": "http-in", "listen": "0.0.0.0", "port": 7890,
         "protocol": "http",
         "sniffing": {"enabled": True, "destOverride": ["http", "tls"],
                      "routeOnly": True}},
        {"tag": "socks-in", "listen": "0.0.0.0", "port": 7891,
         "protocol": "socks", "settings": {"auth": "noauth", "udp": True},
         "sniffing": {"enabled": True, "destOverride": ["http", "tls"],
                      "routeOnly": True}},
        # legacy REDIRECT target (unused by the TUN design, kept for parity)
        {"tag": "transparent", "listen": "0.0.0.0", "port": 12345,
         "protocol": "dokodemo-door",
         "settings": {"network": "tcp", "followRedirect": True},
         "sniffing": {"enabled": True, "destOverride": ["http", "tls"],
                      "routeOnly": True}},
    ]

    rules = [
        # DNS queries arriving via the TUN gateway go to the DNS module
        {"type": "field", "inboundTag": ["tun-in"], "port": 53,
         "outboundTag": "dns-out"},
        # DNS module's upstream connections: CN resolvers direct...
        {"type": "field", "inboundTag": ["dns_inbound"],
         "ip": ["geoip:cn"], "outboundTag": "direct"},
        # ...foreign resolvers via the proxy
        {"type": "field", "inboundTag": ["dns_inbound"],
         "outboundTag": "proxy"},
    ]

    if test_ports:
        for i in range(len(nodes)):
            inbounds.append({
                "tag": "test-in-%02d" % i,
                "listen": "0.0.0.0", "port": TEST_PORT_BASE + i,
                "protocol": "http",
            })
            rules.append({"type": "field", "inboundTag": ["test-in-%02d" % i],
                          "outboundTag": tag_of(i)})

    # per-domain split rules (e.g. javdb.com -> Singapore node)
    for domain, idx in domain_rules.items():
        rules.append({"type": "field", "domain": ["domain:" + domain],
                      "outboundTag": tag_of(idx)})

    # client traffic split
    rules.append({"type": "field", "ip": ["geoip:cn", "geoip:private"],
                  "outboundTag": "direct"})

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {"rules": rules},
        "dns": {
            "hosts": hosts,
            "servers": [
                {"address": "223.5.5.5", "expectIPs": ["geoip:cn"]},
                {"address": "8.8.8.8"},
            ],
            "tag": "dns_inbound",
        },
    }
    return config


def main(argv):
    sub, out = argv[1], argv[2]
    main_idx = int(argv[3]) if len(argv) > 3 else 0
    domain_rules = {}
    test_ports = False
    for a in argv[4:]:
        if a == '--test-ports':
            test_ports = True
        elif a.startswith('--domain='):
            dom, idx = a[len('--domain='):].split('=')
            domain_rules[dom] = int(idx)
    nodes = parse_nodes(sub)
    config = build_config(nodes, main_idx, domain_rules, test_ports)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print('nodes: %d, hosts: %d -> %s'
          % (len(nodes), len(config['dns']['hosts']), out))


if __name__ == '__main__':
    main(sys.argv)
