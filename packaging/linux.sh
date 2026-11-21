#!/usr/bin/env bash
# Builds CardBrowser-<version>-linux.tar.gz: the app files, its pure-Python packages in vendor/ and run.sh, which starts
# it with the system python3 (GTK 3 + WebKit2GTK 4.1 come from the system). Usage: packaging/linux.sh (PYTHON=python3)
set -euo pipefail
cd "$(dirname "$0")/.."
py=${PYTHON:-python3}
v=$("$py" -I launch.py --version)
stage=build/linux
out=$stage/CardBrowser
rm -rf "$stage"
mkdir -p "$out"
"$py" -m pip install --quiet --disable-pip-version-check --no-compile --no-deps --target "$out/vendor" \
  -c constraints.txt pywebview bottle proxy_tools typing_extensions
rm -rf "$out/vendor/bin" "$out/vendor/webview/lib" "$out/vendor/webview/__pyinstaller"
find "$out/vendor/webview/platforms" -mindepth 1 -maxdepth 1 ! -name gtk.py ! -name __init__.py -exec rm -rf {} +
find "$out/vendor" -name __pycache__ -type d -prune -exec rm -rf {} +
cp cardbrowser.py guards.py actions.py selftest.py launch.py inject.js LICENSE "$out/"
"$py" -I packaging/notices.py --path "$out/vendor" --no-runtime "$out/THIRD-PARTY-NOTICES.txt"
cat > "$out/run.sh" <<'EOF'
#!/bin/sh
# Starts CardBrowser with a system Python 3.10+ that has GTK 3 and WebKit2GTK 4.1.
here=$(cd "$(dirname "$0")" && pwd)
for py in /usr/bin/python3 python3; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -I -c 'import sys, gi; assert sys.version_info >= (3, 10)
gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1")' 2>/dev/null; then
    exec "$py" -I "$here/launch.py" "$@"
  fi
done
echo "CardBrowser needs Python 3.10 or newer with GTK 3 and WebKit2GTK 4.1. Install them, then run ./run.sh again:" >&2
echo "  Debian/Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1" >&2
echo "  Fedora: sudo dnf install python3-gobject webkit2gtk4.1" >&2
exit 1
EOF
chmod +x "$out/run.sh"
tar -C "$stage" -czf "CardBrowser-$v-linux.tar.gz" CardBrowser
ls -l "CardBrowser-$v-linux.tar.gz"
