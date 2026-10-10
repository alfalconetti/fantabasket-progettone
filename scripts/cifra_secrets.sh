#!/usr/bin/env bash
# Cifra la cartella secrets/ in secrets/cifrati/secrets.tar.gpg (AES256, passphrase).
# Il bot main allega SOLO questo file cifrato a ogni backup: i secrets in chiaro non
# escono mai dal server. Da rilanciare ogni volta che cambi un file in secrets/.
# La passphrase sta nel password manager (non sul server). Ripristino: docs/RECOVERY.md
#
# La passphrase la legge lo script e la passa a gpg da un descrittore di file
# (--pinentry-mode loopback): niente gpg-agent né pinentry, che via SSH possono
# fallire ("problem with the agent: A locale function failed").
set -euo pipefail
cd "$(dirname "$0")/.."

command -v gpg >/dev/null || { echo "❌ gpg non installato: sudo apt install gnupg"; exit 1; }
[ -d secrets ] || { echo "❌ cartella secrets/ non trovata"; exit 1; }
mkdir -p secrets/cifrati
[ -w secrets/cifrati ] || { echo "❌ secrets/cifrati non scrivibile (creata da docker come root?): sudo chown $USER: secrets/cifrati"; exit 1; }

read -rsp "🔐 Passphrase: " pw1; echo
read -rsp "🔐 Ripeti la passphrase: " pw2; echo
[ -n "$pw1" ] || { echo "❌ Passphrase vuota"; exit 1; }
[ "$pw1" = "$pw2" ] || { echo "❌ Le due passphrase non coincidono"; exit 1; }
[ ${#pw1} -ge 16 ] || echo "⚠️  Passphrase corta (${#pw1} caratteri): meglio almeno 16"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
tar -czf "$tmp" --exclude='./cifrati' -C secrets .

gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo AES256 \
    --output secrets/cifrati/secrets.tar.gpg "$tmp" 3<<<"$pw1"

echo "🔎 Verifica: decifro il file appena creato con la stessa passphrase..."
gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 \
    --decrypt secrets/cifrati/secrets.tar.gpg 3<<<"$pw1" | tar -tz | sed 's/^/   /'
unset pw1 pw2
echo "✅ secrets/cifrati/secrets.tar.gpg pronto: sarà nel prossimo backup."
