#!/bin/sh
# Build the code documentation (rustdoc) and show it in the browser.
#
# The pages are served on http://localhost: opened from disk (file://), Safari
# blocks their style sheets and the pages look plain.
#
#   ./doc.sh          build, serve on port 8765, open the browser
#   ./doc.sh 9000     the same on port 9000
#
# Stop with Ctrl-C.
set -eu
cd "$(dirname "$0")"

PORT="${1:-8765}"
URL="http://localhost:$PORT/shack_core/index.html"

# Only our own crates: remove pages of libraries from an earlier full build.
rm -rf target/doc
cargo doc --no-deps --workspace

echo
echo "Documentation: $URL"
echo "Stop with Ctrl-C."
# Open the browser once the server runs (macOS: open, Linux: xdg-open).
(sleep 1; open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true) &
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory target/doc
