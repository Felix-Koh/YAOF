#!/usr/bin/env bash
set -euo pipefail
recipe_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=${1:?Usage: build.sh WORK_DIRECTORY}
mkdir -p "$work_dir"
cd "$work_dir"
version=25.12.2
archive="immortalwrt-imagebuilder-${version}-x86-64.Linux-x86_64.tar.zst"
base="https://downloads.immortalwrt.org/releases/${version}/targets/x86/64"
curl -fL --retry 4 "$base/$archive" -o "$archive"
printf '%s  %s\n' b9b290f5ef60a22bccd5bdca9c1e7523b8fc84e60462afbf550e20db94acf2c6 "$archive" | sha256sum -c -
tar --zstd -xf "$archive"
cd "${archive%.tar.zst}"
python3 - <<'PY'
from pathlib import Path
p = Path('.config')
s = p.read_text()
for option in ['ISO_IMAGES', 'QCOW2_IMAGES', 'VDI_IMAGES', 'VMDK_IMAGES', 'VHDX_IMAGES']:
    s = s.replace(f'CONFIG_{option}=y', f'# CONFIG_{option} is not set')
p.write_text(s.replace('CONFIG_TARGET_ROOTFS_PARTSIZE=300', 'CONFIG_TARGET_ROOTFS_PARTSIZE=1024'))
PY
chmod 0755 "$recipe_dir/files/etc/uci-defaults/99-n150-minimal"
packages=$(tr '\n' ' ' < "$recipe_dir/packages.txt")
make image PROFILE=generic PACKAGES="$packages" FILES="$recipe_dir/files" ROOTFS_PARTSIZE=1024 EXTRA_IMAGE_NAME=n150-minimal -j2
mkdir -p ../output
cp bin/targets/x86/64/*combined*.img.gz ../output/
cp bin/targets/x86/64/*.manifest ../output/
cp .config ../output/build.config
cp "$recipe_dir/packages.txt" ../output/requested-packages.txt
cp "$recipe_dir/使用说明.md" ../output/
python3 "$recipe_dir/verify.py" "$PWD" ../output
python3 "$recipe_dir/boot-check.py" ../output
cd ../output
sha256sum *.img.gz > SHA256SUMS
