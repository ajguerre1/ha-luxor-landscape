#!/bin/sh
# Run before every push.
#
# The site-data guard only works on a machine that holds the denylist, and the denylist lives
# outside the repository on purpose -- so CI cannot catch a leak of site data. This is the only
# gate there is, which means it has to actually block.
#
# It exists because on 2026-09-09 a real theme name from the reference controller reached this
# public repository. The guard caught it. The push happened anyway, because the test run and the
# push were chained in one command instead of the push being gated on the result.
set -e
cd "$(dirname "$0")/.."
python -m ruff check .
python -m ruff format --check .
python -m pytest tests/ -q
diff custom_components/luxor/strings.json custom_components/luxor/translations/en.json
echo
echo "preflight OK -- safe to push"
