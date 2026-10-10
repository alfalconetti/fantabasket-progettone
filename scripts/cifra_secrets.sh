#!/usr/bin/env bash
# Cifra la cartella secrets/ in secrets/cifrati/secrets.tar.gpg (AES256, passphrase).
# Il bot main allega SOLO questo file cifrato a ogni backup: i secrets in chiaro non
# escono mai dal server. Da rilanciare ogni volta che cambi un file in secrets/.
# La passphrase sta nel password manager (non sul server). Ripristino: docs/RECOVERY.md
set -euo pipefail
cd "$(dirname "$0")/.."

command -v gpg >/dev/null || { echo "❌ gpg non installato: sudo apt install gnupg"; exit 1; }
[ -d secrets ] || { echo "❌ cartella secrets/ non trovata"; exit 1; }
mkdir -p secrets/cifrati
[ -w secrets/cifrati ] || { echo "❌ secrets/cifrati non scrivibile (creata da docker come root?): sudo chown $USER: secrets/cifrati"; exit 1; }

export GPG_TTY=$(tty)
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
tar -czf "$tmp" --exclude='./cifrati' -C secrets .

echo "🔐 Passphrase per cifrare i secrets (due volte):"
gpg --symmetric --cipher-algo AES256 --no-symkey-cache --yes \
    --output secrets/cifrati/secrets.tar.gpg "$tmp"

echo "🔎 Verifica: inserisci di nuovo la passphrase per controllare che si decifri."
gpg --decrypt --no-symkey-cache --quiet secrets/cifrati/secrets.tar.gpg | tar -tz | sed 's/^/   /'
echo "✅ secrets/cifrati/secrets.tar.gpg pronto: sarà nel prossimo backup."
