#!/usr/bin/env bash
# Secret scan with the gitleaks CLI (CI fast gate, a step of the PR gate since
# CI-COST round 2). Rules in .gitleaks.toml, .gitleaksignore honoured.
#
# The CLI, not gitleaks/gitleaks-action: the action demands a paid license key
# once the repo belongs to an organization ("[foundryx-sdn-bhd] is an
# organization. License key is required.", 10 Oct 2026). The binary is pinned
# and its sha256 checked against the release's checksums file. Log opts match
# what the action passed (`--no-merges --first-parent`).
#
# Env: RANGE (git range to scan, e.g. base..head); needs full history.
set -euo pipefail
GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.30.1}"
dir="${RUNNER_TEMP:-$(mktemp -d)}"
# linux_x64 on GitHub-hosted, linux_arm64 on the Mac mini runners (sorento-mac).
case "$(uname -m)" in
  aarch64|arm64) arch=linux_arm64 ;;
  *) arch=linux_x64 ;;
esac
tarball="gitleaks_${GITLEAKS_VERSION}_${arch}.tar.gz"
sums="gitleaks_${GITLEAKS_VERSION}_checksums.txt"
base="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}"
# GITLEAKS_CACHE_DIR: where actions/cache restores (and saves) the tarball and
# checksums file. Optional; unset means always download. A leading ~ (as the
# workflow writes it) is expanded here, the shell does not do it for an env value.
cache="${GITLEAKS_CACHE_DIR:-}"
cache="${cache/#\~/$HOME}"

verify() {
  grep " ${tarball}\$" "$sums" | sha256sum -c -
}

# github.com release-download URLs flapped 504 for every run from 08:46Z on
# 8 Nov 2026 (run 42464184985) while the API asset endpoint stayed up: retry,
# then fall back to `gh release download` (the API path, needs GH_TOKEN) only
# when the direct download still fails.
fetch() {
  local opts=(-sSfL --retry 5 --retry-all-errors --retry-delay 15 --connect-timeout 20)
  if curl "${opts[@]}" -O "$base/$tarball" && curl "${opts[@]}" -O "$base/$sums"; then
    return 0
  fi
  echo "::warning::gitleaks direct download failed; falling back to gh release download"
  gh release download "v${GITLEAKS_VERSION}" -R gitleaks/gitleaks -p "$tarball" -p "$sums" -D . --clobber
}

(
  cd "$dir"
  rm -f "$tarball" "$sums"
  # The checksum is checked on every path: cache, direct and fallback.
  if [ -n "$cache" ] && [ -f "$cache/$tarball" ] && [ -f "$cache/$sums" ]; then
    cp "$cache/$tarball" "$cache/$sums" .
    if verify; then
      echo "Using the cached gitleaks ${GITLEAKS_VERSION} tarball"
    else
      echo "::warning::cached gitleaks tarball failed its checksum; downloading again"
      rm -f "$tarball" "$sums"
    fi
  fi
  if [ ! -f "$tarball" ]; then
    fetch
    verify
    if [ -n "$cache" ]; then
      mkdir -p "$cache"
      cp "$tarball" "$sums" "$cache/"
    fi
  fi
  tar -xzf "$tarball" gitleaks
)
range="${RANGE:?RANGE is required}"
echo "Scanning $range"
# gitleaks reports "no leaks found" and exits 0 when git cannot resolve the
# range (e.g. a force-pushed base), so check it.
git rev-list --count "$range" >/dev/null
"$dir/gitleaks" git --no-banner -v --redact \
  --config .gitleaks.toml --gitleaks-ignore-path . \
  --log-opts="--no-merges --first-parent $range" .
