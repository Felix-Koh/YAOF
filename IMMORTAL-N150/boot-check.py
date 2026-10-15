"""Boot a copy-on-write BIOS disk under QEMU and check basic runtime state."""
import gzip
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

output = Path(sys.argv[1]).resolve()
image = next(output.glob('*squashfs-combined.img.gz'))
disk = output.parent / 'boot-check.img'
with gzip.open(image, 'rb') as src, disk.open('wb') as dst:
    while block := src.read(1024 * 1024):
        dst.write(block)
command = ['qemu-system-x86_64', '-machine', 'pc,accel=tcg', '-m', '512', '-smp', '2', '-nographic', '-monitor', 'none', '-no-reboot', '-snapshot', '-drive', f'file={disk},format=raw,if=virtio', '-netdev', 'user,id=net0,restrict=on', '-device', 'e1000e,netdev=net0', '-netdev', 'user,id=net1,restrict=on', '-device', 'e1000e,netdev=net1']
proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
data = bytearray()
sent = False
deadline = time.monotonic() + 240
try:
    while time.monotonic() < deadline and proc.poll() is None:
        if select.select([proc.stdout], [], [], 1)[0]:
            chunk = os.read(proc.stdout.fileno(), 65536)
            data.extend(chunk)
        if not sent and (b'Please press Enter to activate this console' in data or b'login:' in data):
            proc.stdin.write(b'\nroot\n')
            proc.stdin.flush()
            time.sleep(4)
            proc.stdin.write(b"echo CHECK_START; cat /etc/openwrt_release; uci get network.lan.ipaddr; uci get system.@system[0].hostname; /etc/init.d/uhttpd running && echo WEB_OK; /etc/init.d/dnsmasq running && echo DNS_OK; fw4 check >/dev/null 2>&1 && echo FIREWALL_OK; echo CHECK_DONE\n")
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
    (output / 'boot-serial.log').write_bytes(data)
    disk.unlink(missing_ok=True)
text = data.decode(errors='replace')
checks = {key: f'\n{key}\r\n' in text or f'\n{key}\n' in text for key in ['WEB_OK', 'DNS_OK', 'FIREWALL_OK', 'CHECK_DONE']}
checks['version'] = "DISTRIB_RELEASE='25.12.2'" in text
checks['address'] = '\n192.168.1.1\r\n' in text
checks['hostname'] = '\nImmortalWrt-N150\r\n' in text
(output / 'boot-validation.json').write_text(json.dumps({'method': 'QEMU BIOS disk boot, two emulated e1000e NICs, isolated user networking', 'checks': checks, 'physical_n150_tested': False}, indent=2) + '\n')
assert all(checks.values()), f'Runtime checks failed: {checks}; inspect boot-serial.log'
print(checks)
