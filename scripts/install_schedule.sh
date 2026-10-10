#!/bin/zsh
# Sabah brifingini Mac'te arka plan servisi (launchd) olarak kurar.
# Servis oturum açıkken sürekli çalışır; hafta içi 07:30'da boru hattını başlatır, 08:15'te gönderir,
# KAP kopyasını 18:30 ve 23:50'de alır. Kaldırmak için: scripts/uninstall_schedule.sh
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.sabahbrifingi.scheduler"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$PROJECT/.venv/bin/python"

[[ -x "$PYTHON" ]] || { echo "Hata: $PYTHON yok. Önce 'make install' çalıştırın."; exit 1; }
mkdir -p "$PROJECT/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$PROJECT/main.py</string>
    <string>--schedule</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$PROJECT/logs/scheduler.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/logs/scheduler.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 3

if launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -q "state = running"; then
  echo "✓ Servis çalışıyor. Kayıt: $PROJECT/logs/scheduler.log"
  tail -n 3 "$PROJECT/logs/scheduler.log" 2>/dev/null || true
else
  echo "✗ Servis başlamadı. Son kayıtlar:"
  tail -n 20 "$PROJECT/logs/scheduler.log" 2>/dev/null || true
  echo "'Operation not permitted' görüyorsanız: Sistem Ayarları → Gizlilik ve Güvenlik → Tam Disk Erişimi'ne"
  echo "  $PYTHON dosyasını ekleyin veya projeyi Masaüstü dışındaki bir klasöre taşıyın."
fi
echo
echo "Mac'in hafta içi 07:25'te uyanması için (yönetici şifresi ister):"
echo "  sudo pmset repeat wakeorpoweron MTWRF 07:25:00"
