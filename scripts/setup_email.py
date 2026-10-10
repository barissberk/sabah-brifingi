"""Gmail ile kişisel gönderim kurulumu.

Terminal'de çalıştırın (şifre ekranda görünmez, sohbete yazılmaz):
    .venv/bin/python scripts/setup_email.py

Yapılanlar:
  1. Gmail adresinizi ve Google "uygulama şifrenizi" sorar.
  2. .env içindeki e-posta ayarlarını günceller (gönderen = alıcı = sizin adresiniz).
  3. Gmail SMTP sunucusuna giriş yaparak bilgileri doğrular — e-posta GÖNDERMEZ.

Uygulama şifresi: https://myaccount.google.com/apppasswords
(Google hesabınızda 2 adımlı doğrulama açık olmalı; şifre 16 harftir, boşluklar önemsizdir.)
"""
from __future__ import annotations

import getpass
import re
import smtplib
import ssl
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"
EMAIL_RE = re.compile(r"^[^@\s]+@(gmail|googlemail)\.com$", re.I)


def set_env(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    return pattern.sub(lambda _: line, text) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"


def main() -> int:
    if not ENV.exists():
        print("Hata: .env bulunamadı. Önce `make install` çalıştırın.")
        return 1

    current = re.search(r"^SMTP_USER=(\S+)", ENV.read_text(encoding="utf-8"), re.M)
    default = current.group(1) if current else ""
    prompt = f"Gmail adresiniz{f' [{default} — onaylamak için yalnızca Enter]' if default else ''}: "
    address = getpass.getpass(prompt).strip() or default if default else input(prompt).strip()
    if re.fullmatch(r"[a-z]{4}(\s?[a-z]{4}){3}", address, re.I):
        print("Hata: buraya uygulama şifresine benzeyen bir değer girildi (ekrana yazılmadı). Adres sorusunda "
              "yalnızca Enter'a basın; şifreyi bir sonraki soruya yapıştırın.")
        return 1
    if not EMAIL_RE.match(address):
        print("Hata: geçerli bir @gmail.com adresi girin.")
        return 1
    password = re.sub(r"\s+", "", getpass.getpass("Google uygulama şifresi (görünmez): "))
    if len(password) != 16:
        print(f"Uyarı: uygulama şifreleri 16 karakterdir, girilen {len(password)} karakter. Yine de deneniyor…")

    print(f"Adres: {address}")
    print("Gmail'e giriş deneniyor (e-posta gönderilmeyecek)…")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(address, password)
    except smtplib.SMTPAuthenticationError:
        print("Giriş başarısız: adres veya uygulama şifresi hatalı. Normal Gmail şifreniz değil, "
              "https://myaccount.google.com/apppasswords adresinden oluşturduğunuz şifre gerekli. .env değiştirilmedi.")
        return 2
    except OSError as exc:
        print(f"Bağlantı hatası: {exc}. .env değiştirilmedi.")
        return 3

    text = ENV.read_text(encoding="utf-8")
    for key, value in {
        "EMAIL_PROVIDER": "smtp",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USE_TLS": "true",
        "SMTP_USER": address,
        "SMTP_PASSWORD": password,
        "EMAIL_FROM": f"Sabah Brifingi <{address}>",
        "SUBSCRIBERS": address,
    }.items():
        text = set_env(text, key, value)
    ENV.write_text(text, encoding="utf-8")
    ENV.chmod(0o600)  # yalnızca sizin kullanıcınız okuyabilsin
    print(f"Tamam: giriş doğrulandı ve .env güncellendi. Bülten {address} adresine gönderilecek.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
