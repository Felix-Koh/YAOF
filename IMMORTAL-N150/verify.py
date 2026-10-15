"""Inspect actual package manifests, disk images and installed filesystem."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root, output = map(Path, sys.argv[1:])
manifests = list(output.glob('*.manifest'))
assert manifests, 'Missing package manifest'
required = {'luci-base', 'luci-app-package-manager', 'luci-i18n-base-zh-cn', 'firewall4', 'dnsmasq-full', 'ppp-mod-pppoe', 'kmod-igc', 'kmod-r8125', 'apk-openssl'}
packages = {}
for manifest in manifests:
    packages.update(line.split(' - ', 1) for line in manifest.read_text().splitlines() if ' - ' in line)
assert not required - packages.keys(), f'Missing packages: {required - packages.keys()}'
for name in packages:
    assert not any(term in name for term in ['daed', 'homeproxy', 'passwall', 'openclash', 'ddns-go', 'vlmcsd']), name
images = sorted(output.glob('*combined*.img.gz'))
assert len(images) == 4, f'Expected four UEFI/BIOS squashfs/ext4 images, got {len(images)}'
image_report = []
for image in images:
    size = 0
    with gzip.open(image, 'rb') as f:
        sector = f.read(512)
        assert sector[510:512] == b'\x55\xaa', f'Invalid MBR: {image}'
        size += len(sector)
        while chunk := f.read(1024 * 1024):
            size += len(chunk)
    assert size > 1024 * 1024 * 1024, f'Unexpected disk size: {size}'
    image_report.append({'name': image.name, 'compressed_bytes': image.stat().st_size, 'disk_bytes': size, 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()})
roots = list((root / 'build_dir').glob('target-*/root-x86'))
assert roots, 'No installed root filesystem'
fs = roots[0]
for path in ['usr/sbin/uhttpd', 'usr/sbin/dnsmasq', 'usr/share/ucode/luci/runtime.uc', 'etc/apk/repositories.d/distfeeds.list', 'etc/uci-defaults/99-n150-minimal']:
    assert (fs / path).exists(), f'Missing installed file: {path}'
assert '25.12.2' in (fs / 'etc/openwrt_release').read_text()
report = {'status': 'passed', 'build_method': 'Official ImmortalWrt 25.12.2 ImageBuilder; precompiled official kernel and packages', 'package_count': len(packages), 'packages': packages, 'images': image_report, 'installed_rootfs_checked': True, 'physical_n150_tested': False}
(output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'packages'}, indent=2))
