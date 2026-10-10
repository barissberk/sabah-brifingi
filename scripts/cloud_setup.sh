#!/bin/zsh
# Projeyi GitHub'a yükler ve bulutta (GitHub Actions) çalışacak şekilde kurar.
#   1. Herkese açık depo oluşturur ve kodu yükler (.env, output/ ve diğer yerel dosyalar YÜKLENMEZ)
#   2. Anahtarları .env'den okuyup GitHub Secrets'a aktarır (ekrana yazılmaz)
#   3. İlk "hemen-gonder" çalışmasını tetikler (e-posta adresinize gelir) ve GitHub Pages'i açar
#
# Önkoşul: GitHub CLI (gh) kurulu ve `gh auth login` ile giriş yapılmış olmalı.
# Kullanım: scripts/cloud_setup.sh [depo-adı]      (varsayılan: sabah-brifingi)
set -euo pipefail

REPO_NAME="${1:-sabah-brifingi}"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT"

command -v gh > /dev/null || { echo "Hata: GitHub CLI (gh) bulunamadı."; exit 1; }
gh auth status > /dev/null 2>&1 || { echo "Önce giriş yapın: gh auth login"; exit 1; }
[[ -f .env ]] || { echo "Hata: .env bulunamadı."; exit 1; }

env_value() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//' ; }

# --- 1. Depo + ilk yükleme ---
OWNER="$(gh api user --jq .login)"
if [[ ! -d .git ]]; then
  git init -q -b main
fi
# Git kimliği tanımlı değilse GitHub'ın gizli (noreply) adresi kullanılır; gerçek e-posta depoya yazılmaz
if ! git config user.email > /dev/null; then
  git config user.name "$OWNER"
  git config user.email "$(gh api user --jq .id)+$OWNER@users.noreply.github.com"
fi
git add -A
if git ls-files --error-unmatch .env > /dev/null 2>&1; then
  echo "Hata: .env git'e eklenmiş görünüyor; durduruldu."; exit 1
fi
git diff --cached --quiet || git commit -q -m "Sabah Finans Brifingi"

if ! gh repo view "$OWNER/$REPO_NAME" > /dev/null 2>&1; then
  gh repo create "$REPO_NAME" --public --source . --remote origin --push \
    --description "4 ajanlı sabah finans brifingi (GitHub Actions ile her iş günü 08:15)"
else
  git remote get-url origin > /dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$REPO_NAME.git"
  git push -q -u origin main
fi
echo "✓ Kod yüklendi: https://github.com/$OWNER/$REPO_NAME"

# --- 2. Secrets (.env'den, ekrana yazılmadan) ---
for key in GEMINI_API_KEY SMTP_USER SMTP_PASSWORD; do
  value="$(env_value "$key")"
  [[ -n "$value" ]] || { echo "Hata: .env içinde $key boş."; exit 1; }
  printf '%s' "$value" | gh secret set "$key" --repo "$OWNER/$REPO_NAME" > /dev/null
  echo "✓ Secret ayarlandı: $key"
done
subs="$(env_value SUBSCRIBERS)"
if [[ -n "$subs" ]]; then
  printf '%s' "$subs" | gh secret set SUBSCRIBERS --repo "$OWNER/$REPO_NAME" > /dev/null
  echo "✓ Secret ayarlandı: SUBSCRIBERS"
fi

# --- 3. İlk çalışma + GitHub Pages ---
echo "İlk test çalışması başlatılıyor (yaklaşık 3-4 dakika, e-posta adresinize gelecek)…"
gh workflow run sabah-brifingi.yml --repo "$OWNER/$REPO_NAME" -f mode=hemen-gonder
sleep 8
RUN_ID="$(gh run list --repo "$OWNER/$REPO_NAME" --workflow sabah-brifingi.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$RUN_ID" --repo "$OWNER/$REPO_NAME" --exit-status || {
  echo "✗ İlk çalışma başarısız. Ayrıntı: gh run view $RUN_ID --repo $OWNER/$REPO_NAME --log-failed"; exit 1; }

if ! gh api "repos/$OWNER/$REPO_NAME/pages" > /dev/null 2>&1; then
  gh api -X POST "repos/$OWNER/$REPO_NAME/pages" -f "source[branch]=gh-pages" -f "source[path]=/" > /dev/null
fi
echo "✓ GitHub Pages açıldı: https://$(echo "$OWNER" | tr '[:upper:]' '[:lower:]').github.io/$REPO_NAME/"
echo "  (İlk yayın 1-2 dakika sürebilir; ilk e-postadaki 'Dinle' bağlantısı ondan sonra açılır.)"
echo
echo "Kurulum tamam. Bundan sonra bülten her iş günü 08:15'te buluttan gelir; Mac'in açık olması gerekmez."
echo "Mac'teki yerel zamanlayıcı kuruluysa iki kez e-posta gelmemesi için kaldırın: make schedule-uninstall"
