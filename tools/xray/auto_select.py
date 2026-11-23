#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clash-style auto node selection for the K3 xray (url-test equivalent).

Flow:
  1. fetch the subscription (via the K3 proxy, like update_k3.sh)
  2. deploy a config where every node has its own HTTP test inbound
     (127.0.0.1-visible ports 17900+i) -> benchmark all nodes without
     restarting xray per node
  3. benchmark: RTT (google 204, parallel) + throughput (2MB CF download,
     sequential so nodes do not fight over the shared CDN)
  4. winners: default 'proxy' = fastest node overall (throughput first,
     RTT tiebreak within the top band); javdb.com = fastest Singapore node
     (subscription indices 6/7/8) via a domain rule
  5. deploy the final config and verify (google + javdb exit + page)

Re-run anytime (e.g. after the airport gets congested) with:
    python C:\\Users\\54743\\k3-proxy\\auto_select.py
"""
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from gen_config import build_config, parse_nodes, TEST_PORT_BASE  # noqa: E402

K3 = 'root@192.168.2.1'
SERVE_DIR = os.path.join(BASE, 'serve')
CONF_PATH = os.path.join(SERVE_DIR, 'xray-config.json')
SUB_TMP = os.path.join(os.environ.get('TEMP', BASE), 'sub_auto.txt')
ASKPASS = r'C:\Users\54743\.ssh\k3-askpass.bat'
GOOGLE_204 = 'https://www.google.com/generate_204'
CF_DOWN = 'https://speed.cloudflare.com/__down?bytes=2097152'
JAVDB = 'javdb.com'
SG = [6, 7, 8]      # subscription indices of the Singapore nodes
SKIP = {0, 1, 2}    # fake lines: traffic quota / expiry / load-balance
RTT_TRIES = 2

SSH_ENV = dict(os.environ, SSH_ASKPASS=ASKPASS, SSH_ASKPASS_REQUIRE='force')
SSH = [r'C:\Windows\System32\OpenSSH\ssh.exe',
       '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL',
       '-o', 'HostKeyAlgorithms=+ssh-rsa', '-o', 'PubkeyAcceptedKeyTypes=+ssh-rsa',
       '-o', 'PreferredAuthentications=password', '-o', 'PubkeyAuthentication=no',
       '-q']


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def sub_url():
    txt = open(os.path.join(BASE, 'update_k3.sh'), encoding='utf-8').read()
    m = re.search(r'SUB_URL="([^"]+)"', txt)
    if not m:
        raise SystemExit('SUB_URL not found in update_k3.sh')
    return m.group(1)


def pc_ip():
    out = subprocess.run(['ipconfig'], capture_output=True, text=True,
                         errors='ignore').stdout
    m = re.search(r'IPv4[^\n]*:\s*(192\.168\.2\.\d+)', out)
    if not m:
        raise SystemExit('PC is not on 192.168.2.x, cannot serve the config')
    return m.group(1)


def deploy():
    """Serve the config briefly and let K3 pull/validate/restart it."""
    ip = pc_ip()
    srv = subprocess.Popen(['python', '-m', 'http.server', '8000', '--bind', ip],
                           cwd=SERVE_DIR, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    time.sleep(2)
    try:
        cmd = ("wget -q -O /etc/xray/config.json "
               "'http://%s:8000/xray-config.json' "
               "&& XRAY_LOCATION_ASSET=/usr/share/xray /usr/bin/xray run -test "
               "-config /etc/xray/config.json "
               "&& /etc/init.d/xray restart && sleep 3 "
               "&& sh /etc/xray-tun-routes.sh") % ip
        r = subprocess.run(SSH + [K3, cmd], env=SSH_ENV,
                           capture_output=True, text=True, timeout=90)
        if r.returncode != 0:
            log('DEPLOY FAILED: %s %s' % (r.stdout.strip(), r.stderr.strip()))
            sys.exit(1)
    finally:
        srv.terminate()
    log('deployed OK')


def write_config(cfg):
    with open(CONF_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def curl_proxy(port, url, timeout, measure_speed=False):
    """Return (http_code, seconds, bytes_per_sec)."""
    fmt = '%{http_code}' + (' %{speed_download}' if measure_speed else '')
    t0 = time.time()
    try:
        r = subprocess.run(
            ['curl', '-s', '-o', os.devnull, '--max-time', str(timeout),
             '-x', 'http://192.168.2.1:%d' % port, '-w', fmt, url],
            capture_output=True, text=True, timeout=timeout + 5)
        parts = r.stdout.strip().split()
        code = parts[0] if parts else '000'
        speed = float(parts[1]) if measure_speed and len(parts) > 1 else 0.0
        return code, time.time() - t0, speed
    except Exception:
        return 'ERR', timeout, 0.0


def measure_rtt(i):
    port = TEST_PORT_BASE + i
    best = None
    for _ in range(RTT_TRIES):
        code, t, _ = curl_proxy(port, GOOGLE_204, 10)
        if code == '204' and (best is None or t < best):
            best = t
    return i, best


def measure_throughput(i):
    port = TEST_PORT_BASE + i
    code, t, speed = curl_proxy(port, CF_DOWN, 20, measure_speed=True)
    mbps = speed / 125000.0 if code == '200' else 0.0
    return i, code, mbps


def benchmark(nodes):
    live = [i for i in range(len(nodes)) if i not in SKIP]
    log('RTT sweep: %d nodes (parallel)' % len(live))
    rtt = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, t in ex.map(measure_rtt, live):
            rtt[i] = t
    log('throughput sweep (sequential, 2MB each)')
    res = {}
    for i in live:
        _, code, mbps = measure_throughput(i)
        res[i] = {'rtt': rtt.get(i), 'mbps': mbps, 'code': code,
                  'name': nodes[i].get('ps', '?')}
        rtt_s = '%.2fs' % rtt[i] if rtt[i] is not None else 'FAIL'
        log('node %2d  %-16s rtt %6s  %6.2fMbps (%s)'
            % (i, res[i]['name'][:16], rtt_s, mbps, code))
    return res


def pick(res, indices=None):
    """Fastest by throughput; among the top band, lowest RTT wins."""
    pool = [k for k in res if (indices is None or k in indices)
            and res[k]['mbps'] >= 0.05]
    if not pool:
        # nothing passed throughput; fall back to best RTT among the group
        pool = [k for k in res if (indices is None or k in indices)
                and res[k]['rtt'] is not None]
    if not pool:
        return None
    best = max(res[k]['mbps'] for k in pool)
    top = [k for k in pool if res[k]['mbps'] >= best * 0.75]
    return min(top, key=lambda k: res[k]['rtt'] or 999)


def verify(main_win, sg_win):
    def curl(extra, url):
        return subprocess.run(
            ['curl', '-s', '--max-time', '20'] + extra + [url],
            capture_output=True, text=True).stdout.strip()

    g = curl(['-o', os.devnull, '-w', '%{http_code}',
              '-x', 'http://192.168.2.1:7890'], GOOGLE_204)
    trace = curl(['-x', 'http://192.168.2.1:7890'],
                 'https://%s/cdn-cgi/trace' % JAVDB)
    page = subprocess.run(
        ['curl', '-s', '--max-time', '25', '-x', 'http://192.168.2.1:7890',
         'https://%s/' % JAVDB], capture_output=True, text=True).stdout
    ok = 'JavDB' in page or 'javdb' in page.lower() or '數據' in page
    print()
    log('verify: google via 7890 -> %s' % g)
    for line in trace.splitlines():
        if line.startswith(('ip=', 'loc=')):
            print('        javdb trace %s' % line)
    log('verify: javdb page OK' if ok else 'verify: javdb page NOT ok')
    return g == '204' and ok


def main():
    log('fetch subscription')
    subprocess.run(['curl', '-s', '--max-time', '60',
                    '-x', 'http://192.168.2.1:7890', sub_url(), '-o', SUB_TMP],
                   check=True)
    nodes = parse_nodes(SUB_TMP)
    log('%d nodes in subscription' % len(nodes))

    log('deploy benchmark config (test ports %d-%d)'
        % (TEST_PORT_BASE, TEST_PORT_BASE + len(nodes) - 1))
    write_config(build_config(nodes, 6, {}, test_ports=True))
    deploy()

    res = benchmark(nodes)
    main_win = pick(res)
    sg_win = pick(res, SG)
    if main_win is None:
        log('no live node at all, aborting')
        sys.exit(1)
    log('winner main: node %d %s (%.2fMbps, %.2fs)'
        % (main_win, res[main_win]['name'][:16],
           res[main_win]['mbps'], res[main_win]['rtt'] or -1))
    if sg_win is None:
        log('no live Singapore node, javdb falls back to main node')
        rules = {}
    else:
        log('winner SG  : node %d %s (%.2fMbps, %.2fs)'
            % (sg_win, res[sg_win]['name'][:16],
               res[sg_win]['mbps'], res[sg_win]['rtt'] or -1))
        rules = {JAVDB: sg_win}

    log('deploy final config')
    write_config(build_config(nodes, main_win, rules, test_ports=True))
    deploy()

    if verify(main_win, sg_win):
        log('ALL OK')
    else:
        log('verification incomplete, check manually')
        sys.exit(2)


if __name__ == '__main__':
    main()
