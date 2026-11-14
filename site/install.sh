#!/bin/sh
# Ushka installer: https://ushka.satela.com.br
#
# Installs the `ushka` command for the current user. No sudo, nothing outside
# your home directory. Read it before running it:
#
#   curl -LsSf https://ushka.satela.com.br/install.sh -o install.sh
#   curl -LsSf https://ushka.satela.com.br/install.sh.sha256 | sha256sum -c -
#   sh install.sh
#
# Options (environment variables):
#   USHKA_EXTRAS=orm        also install extras (orm, postgres, mysql, full)
#   USHKA_VERSION=0.5.0     install a specific version instead of the latest
set -eu

say() { printf '%s\n' "$*"; }
fail() { printf 'ushka-install: %s\n' "$*" >&2; exit 1; }

extras="${USHKA_EXTRAS:-}"
pin="${USHKA_VERSION:-}"
case "$extras" in *[!a-z,]*) fail "USHKA_EXTRAS may only contain letters and commas." ;; esac
case "$pin" in *[!0-9a-z.]*) fail "USHKA_VERSION must look like 0.5.0." ;; esac

spec="ushka"
[ -n "$extras" ] && spec="ushka[$extras]"
[ -n "$pin" ] && spec="$spec==$pin"

if command -v uv >/dev/null 2>&1; then
    say "Installing $spec with uv..."
    uv tool install --upgrade "$spec"
elif command -v pipx >/dev/null 2>&1; then
    say "Installing $spec with pipx..."
    pipx install --force "$spec"
else
    python=$(command -v python3 || true)
    [ -n "$python" ] || fail "Python 3.10+ is required (python3 not found)."
    "$python" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
        || fail "Python 3.10+ is required; found $("$python" -V 2>&1)."
    venv="${XDG_DATA_HOME:-$HOME/.local/share}/ushka/venv"
    say "uv and pipx not found: installing $spec into $venv"
    "$python" -m venv "$venv"
    "$venv/bin/python" -m pip install --quiet --upgrade pip "$spec"
    mkdir -p "$HOME/.local/bin"
    ln -sf "$venv/bin/ushka" "$HOME/.local/bin/ushka"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) say "Add ~/.local/bin to your PATH to use the ushka command." ;;
    esac
fi

say ""
say "Installed: $(ushka --version 2>/dev/null || echo "$spec")"
say "Next:  ushka new myapp && cd myapp && ushka dev"
