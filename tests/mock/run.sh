#!/usr/bin/env bash
# End-to-end test of the collection against the mock panel.
#
# Part 1 (play.yml, through the role) asserts, in order:
#   1. check mode on a fresh panel predicts changes without applying any;
#   2. the first real run applies everything;
#   3. the second run is a no-op (idempotency);
#   4. a modified desired state applies exactly the delta;
#   5. the delta run is idempotent too;
#   6. check mode on a converged panel predicts no changes.
#
# Part 2 (cascade.yml) exercises the node -> linked hosts cascade and
# asserts its own expectations inline.
#
# Requires the collection to be reachable via ANSIBLE_COLLECTIONS_PATH,
# e.g.  tests/mock/run.sh  from a checkout symlinked as
# <path>/ansible_collections/kenyawest/remnawave.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${MOCK_PORT:-18443}"

MOCK_TOKEN=test-token MOCK_API_KEY=sekret python3 "$HERE/mock_panel.py" "$PORT" &
MOCK_PID=$!
trap 'kill "$MOCK_PID" 2>/dev/null || true' EXIT
sleep 1

run() {
    ANSIBLE_STDOUT_CALLBACK=ansible.builtin.default \
    ansible-playbook -i localhost, "$1" -e "mock_port=$PORT" "${@:2}" 2>&1
}

changed_count() {
    grep -oE 'changed=[0-9]+' <<<"$1" | head -1 | cut -d= -f2
}

assert_changed() {
    local label="$1" expected="$2" output="$3"
    local actual
    actual="$(changed_count "$output")"
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $label: expected changed=$expected, got changed=$actual"
        echo "$output" | tail -40
        exit 1
    fi
    echo "PASS: $label (changed=$actual)"
}

PLAY="$HERE/play.yml"
out="$(run "$PLAY" --check --diff)";       assert_changed "check mode on fresh panel"    7 "$out"
out="$(run "$PLAY")";                      assert_changed "first apply"                  7 "$out"
out="$(run "$PLAY")";                      assert_changed "second apply is a no-op"      0 "$out"
out="$(run "$PLAY" -e alice_traffic=50GB -e node_state=disabled)"
                                           assert_changed "delta apply"                  2 "$out"
out="$(run "$PLAY" -e alice_traffic=50GB -e node_state=disabled)"
                                           assert_changed "delta apply is a no-op"       0 "$out"
out="$(run "$PLAY" -e alice_traffic=50GB -e node_state=disabled --check --diff)"
                                           assert_changed "check mode on converged panel" 0 "$out"

if out="$(run "$HERE/cascade.yml")"; then
    echo "PASS: node to linked-hosts cascade scenarios"
else
    echo "FAIL: node to linked-hosts cascade scenarios"
    echo "$out" | tail -60
    exit 1
fi

echo "All mock integration checks passed."
