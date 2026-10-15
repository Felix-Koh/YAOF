"""Boot copy-on-write BIOS and UEFI disks; check actual basic services."""
import gzip
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time

output = Path(sys.argv[1]).resolve()
reports = []
for mode, suffix in [('bios', '*squashfs-combined.img.gz'), ('uefi', '*squashfs-combined-efi.img.gz')]:
    image = next(output.glob(suffix))
    disk = output.parent / f'boot-check-{mode}.img'
    with gzip.open(image, 'rb') as src, disk.open('wb') as dst:
        while block := src.read(1024 * 1024):
            dst.write(block)
    command = ['qemu-system-x86_64', '-machine', 'pc,accel=tcg', '-m', '512', '-smp', '2', '-cpu', 'max', '-nographic', '-monitor', 'none', '-no-reboot', '-snapshot', '-drive', f'file={disk},format=raw,if=virtio', '-netdev', 'user,id=net0,restrict=on', '-device', 'e1000e,netdev=net0', '-netdev', 'user,id=net1,restrict=on', '-device', 'e1000e,netdev=net1']
    if mode == 'uefi':
        firmware = Path('/usr/share/OVMF/OVMF_CODE_4M.fd')
        assert firmware.exists(), 'OVMF UEFI firmware missing'
        vars_disk = output.parent / 'OVMF_VARS_4M.fd'
        vars_disk.write_bytes(Path('/usr/share/OVMF/OVMF_VARS_4M.fd').read_bytes())
        command += ['-drive', f'if=pflash,format=raw,readonly=on,file={firmware}', '-drive', f'if=pflash,format=raw,file={vars_disk}']
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    data = bytearray()
    sent = False
    deadline = time.monotonic() + 240
    try:
        while time.monotonic() < deadline and proc.poll() is None:
            if select.select([proc.stdout], [], [], 1)[0]:
                data.extend(os.read(proc.stdout.fileno(), 65536))
            if not sent and (b'Please press Enter to activate this console' in data or b'login:' in data):
                proc.stdin.write(b'\nroot\n')
                proc.stdin.flush()
                time.sleep(15)
                commands = [
                    "for n in $(seq 1 60); do /etc/init.d/uhttpd running && /etc/init.d/dnsmasq running && break; sleep 1; done",
                    "echo CHECK_START",
                    "cat /etc/openwrt_release",
                    "uci get network.lan.ipaddr",
                    "uci get system.@system[0].hostname",
                    "/etc/init.d/uhttpd running && echo WEB_OK",
                    "for n in 1 2 3; do uclient-fetch -T 30 -O /tmp/test-page http://127.0.0.1/cgi-bin/luci/ && test -s /tmp/test-page && grep -qi html /tmp/test-page && { echo HTTP_OK; break; }; sleep 2; done",
                    "test -s /tmp/test-page && head -c 200 /tmp/test-page; echo",
                    "logread | tail -15",
                    "/etc/init.d/dnsmasq running && echo DNS_OK",
                    "nslookup localhost 127.0.0.1 >/dev/null 2>&1 && echo DNS_QUERY_OK",
                    "fw4 check >/dev/null 2>&1 && nft list table inet fw4 >/dev/null 2>&1 && echo FIREWALL_OK",
                    "grep -q https://downloads.immortalwrt.org /etc/apk/repositories.d/distfeeds.list && ! grep -q mirrors.vsean.net /etc/apk/repositories.d/distfeeds.list && echo FEED_OK",
                    "echo CHECK_DONE",
                ]
                assert all(len(line) < 400 for line in commands)
                proc.stdin.write(('\n'.join(commands) + '\n').encode())
                proc.stdin.flush()
                sent = True
            if b'\r\nCHECK_DONE\r\n' in data or b'\nCHECK_DONE\n' in data:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        (output / f'boot-{mode}-serial.log').write_bytes(data)
        disk.unlink(missing_ok=True)
    text = data.decode(errors='replace')
    checks = {key: bool(re.search(r'\n' + key + r'\r?\n', text)) for key in ['WEB_OK', 'HTTP_OK', 'DNS_OK', 'DNS_QUERY_OK', 'FIREWALL_OK', 'FEED_OK', 'CHECK_DONE']}
    checks['version'] = "DISTRIB_RELEASE='25.12.2'" in text
    checks['address'] = bool(re.search(r'\n192\.168\.1\.1\r?\n', text))
    checks['hostname'] = bool(re.search(r'\nImmortalWrt-N150\r?\n', text))
    reports.append({'mode': mode, 'checks': checks, 'passed': all(checks.values())})
(output / 'boot-validation.json').write_text(json.dumps({'method': 'QEMU disk boot with two emulated e1000e NICs and isolated user networking', 'boots': reports, 'physical_n150_tested': False}, indent=2) + '\n')
assert all(r['passed'] for r in reports), f'Runtime checks failed: {reports}; inspect serial logs'
print(reports)
