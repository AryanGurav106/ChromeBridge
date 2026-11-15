#!/bin/sh
# PREREG Amendment 5's restore, as a script rather than three things to
# remember. Run from anywhere in the repo AFTER the last run and BEFORE
# publishing any number.
#
# It does NOT reload the extension and cannot: the flag is a module-scope
# const, so the service worker must restart to pick it up, and #47 measured
# that it does not restart while the bridge holds it alive. A flag restored on
# disk is NOT a flag restored in the browser. The last line says so.
#
# No check here asserts a CHECK COUNT. The count has drifted four times in this
# project and a hardcoded one would fail for the wrong reason; what matters is
# that the suite exits 0 and does not report the gate as off, because a suite
# that passes while reporting "not-applicable (gate off)" proved nothing.
set -e
cd "$(git rev-parse --show-toplevel)"
fail() { echo "FAILED: $1" >&2; exit 1; }

echo "1/3  source reads false"
sed -i '' 's/^const ALLOW_ALL_ORIGINS = true;.*$/const ALLOW_ALL_ORIGINS = false;/' \
    extension/background.js
grep -q '^const ALLOW_ALL_ORIGINS = false;$' extension/background.js \
  || fail "the flag is not a bare 'false' on its own line"
if grep -q 'ALLOW_ALL_ORIGINS *= *true' extension/background.js; then
  fail "a 'true' assignment survives somewhere in the file"
fi
echo "     ok"

echo "2/3  background.js matches HEAD"
if ! git diff --quiet -- extension/background.js; then
  git diff --stat -- extension/background.js
  fail "background.js still differs from HEAD"
fi
echo "     ok"

echo "3/3  test_permissions passes with the gate ARMED"
out=$(node tools/test_permissions.js 2>&1) || { echo "$out"; fail "suite exited non-zero"; }
echo "$out" | tail -2 | sed 's/^/     /'
if echo "$out" | grep -qi 'not-applicable\|gate off'; then
  fail "the suite ran with the gate OFF, so it proved nothing"
fi
echo "     ok"

echo
echo "DISK IS RESTORED. THE BROWSER IS NOT, until you reload the extension at"
echo "chrome://extensions and confirm an op on a known-ungranted origin is"
echo "REFUSED. #47 measured a restore silently not taking for several minutes."
