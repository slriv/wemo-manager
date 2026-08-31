#!/usr/bin/env bash
# Build everything from a clean tree and rebuild the deployment container.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${WEMO_MANAGER_DEPLOY_DIR:-./wemo-manager-deploy}"

mkdir -p "$DEPLOY/data"

need_cmd() { command -v "$1" >/dev/null 2>&1; }
BREW=""
need_cmd brew && BREW=brew

# Checks a command is on PATH, offering to install it via Homebrew when missing.
require_cmd() {
    local cmd="$1" brew_pkg="$2" label="$3"
    need_cmd "$cmd" && return 0
    echo "Missing dependency: $label ($cmd not found)." >&2
    if [[ -n "$BREW" ]]; then
        read -r -p "Install with 'brew install $brew_pkg'? [y/N] " reply
        if [[ "$reply" =~ ^[Yy]$ ]]; then
            brew install $brew_pkg
            need_cmd "$cmd" && return 0
        fi
    fi
    echo "Install $label manually, then re-run this script." >&2
    exit 1
}

check_build_env() {
    require_cmd docker docker "Docker"
    docker compose version >/dev/null 2>&1 || {
        echo "Missing dependency: Docker Compose v2 plugin." >&2
        exit 1
    }
    require_cmd npx node "Node.js"

    if ! need_cmd java \
       && [[ -z "$(/usr/libexec/java_home -v 21 2>/dev/null)" ]] \
       && [[ ! -d /opt/homebrew/opt/openjdk@21 ]]; then
        echo "Missing dependency: JDK 21 (needed to build the Android app)." >&2
        if [[ -n "$BREW" ]]; then
            read -r -p "Install with 'brew install openjdk@21'? [y/N] " reply
            [[ "$reply" =~ ^[Yy]$ ]] && brew install openjdk@21
        else
            echo "Install JDK 21 manually, then re-run this script." >&2
            exit 1
        fi
    fi

    if [[ -z "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" ]] \
       && [[ ! -d "$HOME/Library/Android/sdk" ]] && [[ ! -d "$HOME/Android/Sdk" ]] \
       && [[ ! -d /usr/lib/android-sdk ]] && [[ ! -d /opt/android-sdk ]]; then
        echo "Missing dependency: Android SDK (needed to build the Android app)." >&2
        if [[ -n "$BREW" ]]; then
            read -r -p "Install with 'brew install --cask android-commandlinetools'? [y/N] " reply
            [[ "$reply" =~ ^[Yy]$ ]] && brew install --cask android-commandlinetools
        else
            echo "Install the Android SDK manually, then re-run this script." >&2
            exit 1
        fi
    fi

    if [[ ! -x "$SRC/.venv/bin/pytest" ]]; then
        echo "Missing dependency: Python virtualenv (.venv) with dev dependencies." >&2
        read -r -p "Run 'make install' now? [y/N] " reply
        if [[ "$reply" =~ ^[Yy]$ ]]; then
            make -C "$SRC" install
        else
            echo "Run 'make install' first, then re-run this script." >&2
            exit 1
        fi
    fi
}

check_build_env

# Discard build outputs so a failed build cannot ship a stale one.
rm -f "$SRC/app/static/wemo-manager.apk"
rm -rf "$SRC/mobile/android/app/build" "$SRC/mobile/android/build" \
       "$SRC/.pytest_cache" "$SRC"/*.egg-info
find "$SRC/app" "$SRC/tests" -type d -name __pycache__ -prune -exec rm -rf {} +

"$SRC/.venv/bin/pytest" -q
make -C "$SRC" apk

# The APK is served from the data volume, not the image.
rsync -a --delete --delete-excluded --exclude __pycache__ --exclude '*.apk' \
      "$SRC/app/" "$DEPLOY/app/"
rsync -a "$SRC/Dockerfile" "$SRC/.dockerignore" "$SRC/docker-compose.yml" \
         "$SRC/pyproject.toml" "$SRC/README.md" "$DEPLOY/"
cp -f "$SRC/app/static/wemo-manager.apk" "$DEPLOY/data/wemo-manager.apk"

cd "$DEPLOY"
docker compose up -d --build wemo-manager

for _ in $(seq 30); do
    health="$(docker inspect -f '{{.State.Health.Status}}' wemo-manager 2>/dev/null || echo unknown)"
    if [[ "$health" == "healthy" ]]; then
        break
    fi
    sleep 2
done
echo "wemo-manager: $health"
