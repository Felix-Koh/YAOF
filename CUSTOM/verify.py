#!/usr/bin/env python3
"""Reject missing requirements in resolved Kconfig and firmware manifests."""
import argparse
import json
from pathlib import Path

REQUIRED = [
    'luci-app-daed', 'daed', 'luci-app-services-wolplus',
    'ddns-go', 'luci-app-ddns-go', 'luci-i18n-ddns-go-zh-cn',
    'luci-app-upnp', 'miniupnpd-nftables', 'kmod-nft-fullcone',
    'luci-app-einat', 'autocore-x86', 'irqbalance', 'luci-app-irqbalance',
    'luci-app-vlmcsd', 'vlmcsd', 'luci-app-homeproxy',
    'vmlinux-btf', 'kmod-sched-bpf', 'kmod-igc', 'kmod-r8125',
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['config', 'firmware'])
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    config = (args.root / '.config').read_text()
    missing = [name for name in REQUIRED if f'CONFIG_PACKAGE_{name}=y' not in config.splitlines()]
    assert not missing, f'Required packages absent from resolved .config: {missing}'
    assert 'CONFIG_DAED_USE_VMLINUX_BTF=y' in config.splitlines(), 'DAED BTF source missing'
    print('Resolved configuration includes all required packages and DAED BTF support.')
    if args.stage == 'config':
        return
    target = args.root / 'bin/targets/x86/64'
    manifests = list(target.glob('*.manifest'))
    assert manifests, 'No firmware manifest found'
    reports = []
    for manifest in manifests:
        packages = {line.split(' - ', 1)[0]: line.split(' - ', 1)[-1] for line in manifest.read_text().splitlines() if line.strip()}
        missing = [name for name in REQUIRED if name not in packages]
        assert not missing, f'{manifest.name} is missing required packages: {missing}'
        reports.append({'manifest': manifest.name, 'packages': {name: packages[name] for name in REQUIRED}})
    images = list(target.glob('*combined*.img.gz')) + list(target.glob('*combined*.img'))
    assert images, 'No flashable x86 disk images found'
    rootfs_candidates = list((args.root / 'build_dir').glob('target-*/root-x86'))
    assert rootfs_candidates, 'Cannot inspect installed root filesystem'
    installed = rootfs_candidates[0]
    for path in ['usr/bin/daed', 'usr/bin/ddns-go', 'etc/init.d/irqbalance', 'etc/uci-defaults/99-yaof-n150']:
        assert (installed / path).exists(), f'File missing from installed root filesystem: {path}'
    report = {'status': 'passed', 'manifests': reports, 'images': [path.name for path in images], 'rootfs_files_checked': True}
    (target / 'N150-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
