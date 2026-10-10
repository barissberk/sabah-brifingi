#!/bin/zsh
# Arka plan servisini kaldırır (proje dosyalarına dokunmaz).
LABEL="com.sabahbrifingi.scheduler"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "Servis durduruldu." || echo "Servis zaten çalışmıyordu."
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" && echo "Servis tanımı silindi."
echo "Otomatik uyanmayı da kaldırmak için: sudo pmset repeat cancel"
