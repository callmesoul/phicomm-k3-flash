#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简 TFTP 服务器（RFC 1350，仅支持 RRQ/octet），用于 K3 CFE 刷机。

K3 进入 CFE 后用浏览器执行 do.htm 命令，CFE 的 tftp 客户端会向本机拉取固件：
    http://192.168.2.1/do.htm?cmd=flash+-noheader+192.168.2.22:k3.trx+nflash0.trx
本脚本监听 UDP 69，服务脚本所在目录下的文件。
"""

import os
import socket
import struct
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 3.0
MAX_RETRIES = 10
DATA_BLOCK = 512


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def err_pkt(code, msg):
    return b"\x00\x05" + struct.pack("!H", code) + msg.encode("ascii", "replace") + b"\x00"


class Transfer(threading.Thread):
    def __init__(self, rrq, addr):
        super().__init__(daemon=True)
        self.addr = addr
        parts = rrq.split(b"\x00")
        self.filename = parts[0].decode("latin-1") if parts else ""
        rest = [p.decode("latin-1") for p in parts[2:-1]]
        self.opts = {}
        for i in range(0, len(rest) - 1, 2):
            self.opts[rest[i].lower()] = rest[i + 1]

    def run(self):
        path = os.path.join(ROOT, os.path.basename(self.filename))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("", 0))
        s.settimeout(TIMEOUT)
        if not os.path.isfile(path):
            log("RRQ %r from %s -> 文件不存在" % (self.filename, self.addr[0]))
            s.sendto(err_pkt(1, "File not found"), self.addr)
            s.close()
            return
        data = open(path, "rb").read()
        log("RRQ %r from %s（%d 字节，opts=%s）" % (self.filename, self.addr[0], len(data), self.opts))

        block_size = DATA_BLOCK
        dest = self.addr
        # 客户端带选项时回 OACK 等 ACK0；不支持则退回 512 字节块
        if self.opts:
            oack = b"\x00\x06" + b"".join(
                k.encode() + b"\x00" + v.encode() + b"\x00" for k, v in self.opts.items()
            )
            if "blksize" in self.opts:
                try:
                    block_size = max(512, min(int(self.opts["blksize"]), 1468))
                except ValueError:
                    pass
            s.sendto(oack, self.addr)
            try:
                pkt, dest = s.recvfrom(4096)
            except socket.timeout:
                block_size = DATA_BLOCK
                dest = self.addr
            else:
                if not (pkt[:2] == b"\x00\x04" and struct.unpack("!H", pkt[2:4])[0] == 0):
                    dest = self.addr

        block = 1
        offset = 0
        fails = 0
        while offset < len(data):
            chunk = data[offset : offset + block_size]
            pkt = b"\x00\x03" + struct.pack("!H", block) + chunk
            s.sendto(pkt, dest)
            acked = False
            while not acked:
                try:
                    recv, peer = s.recvfrom(4096)
                except socket.timeout:
                    fails += 1
                    if fails >= MAX_RETRIES:
                        log("第 %d 块重传 %d 次仍无 ACK，放弃" % (block, fails))
                        s.close()
                        return
                    s.sendto(pkt, dest)
                    continue
                # 只认同一台机器的 ACK（客户端可能换源端口，即 TID）
                if recv[:2] != b"\x00\x04" or peer[0] != self.addr[0]:
                    continue
                if struct.unpack("!H", recv[2:4])[0] == block:
                    acked = True
                    fails = 0
                    dest = peer
            offset += block_size
            if block % 500 == 0:
                log("  已发送 %d/%d 字节" % (min(offset, len(data)), len(data)))
            block += 1
        # RFC 1350：文件大小恰为块大小整数倍时，补发 0 字节结束块，
        # 否则客户端（如 K3 的 CFE）会一直等下一块直到超时
        s.sendto(b"\x00\x03" + struct.pack("!H", block) + b"", dest)
        try:
            s.recvfrom(4096)
        except socket.timeout:
            pass
        log("完成！%s -> %s，共 %d 字节（%d 块）" % (self.filename, self.addr[0], len(data), block))
        s.close()


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", 69))
    except OSError as e:
        log("绑定 UDP 69 失败：%s" % e)
        return 1
    log("TFTP 服务器已就绪：监听 UDP 69，服务目录 %s" % ROOT)
    while True:
        pkt, addr = s.recvfrom(65536)
        if pkt[:2] == b"\x00\x01":
            Transfer(pkt[2:], addr).start()
        else:
            log("忽略未知包 %r，来自 %s" % (pkt[:4], addr))


if __name__ == "__main__":
    sys.exit(main())
