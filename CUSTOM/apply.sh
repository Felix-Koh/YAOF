#!/bin/bash
set -euo pipefail

# Run from the OpenWrt buildroot after YAOF's package preparation.
test -d ../CUSTOM/packages
mkdir -p package/custom
for name in ddns-go luci-app-ddns-go; do
    if find package feeds -name Makefile -exec grep -l "^PKG_NAME:=$name$" {} + 2>/dev/null | grep -q .; then
        echo "Duplicate definition for $name; refusing ambiguous package selection" >&2
        exit 1
    fi
    cp -R "../CUSTOM/packages/$name" package/custom/
done
cp -R ../CUSTOM/files/. files/
chmod 0755 files/etc/uci-defaults/99-yaof-n150
./scripts/feeds update -i
./scripts/feeds install -a
