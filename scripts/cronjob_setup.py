"""cron-job.org ile dakikası dakikasına tetikleme kurulumu.

GitHub'ın kendi zamanlayıcısı yoğunlukta işleri saatlerce geciktirebiliyor. Bu betik cron-job.org'da üç görev
oluşturur; her biri belirtilen saatte GitHub iş akışını "workflow_dispatch" ile başlatır:

    Hafta içi 07:15  → mode=sabah-zamanlamasi  (bülten; gönderim 08:15)
    Her gün   18:30  → mode=kap-kopyasi
    Her gün   23:50  → mode=kap-kopyasi

Terminal'de çalıştırın (anahtarlar ekranda görünmez, sohbete yazılmaz):
    .venv/bin/python scripts/cronjob_setup.py

Gerekenler:
  1. cron-job.org hesabı → Console → Settings → API anahtarı
  2. GitHub "fine-grained" erişim anahtarı: yalnızca bu depo, izin: Actions = Read and write
"""
from __future__ import annotations

import getpass
import json
import subprocess
import sys
import time

import requests

API = "https://api.cron-job.org"
TZ = "Europe/Istanbul"
WORKFLOW = "sabah-brifingi.yml"
JOBS = [
    # (başlık, mode, saat, dakika, haftanın günleri [0=Pazar])
    ("Sabah Brifingi · bülten 07:15", "sabah-zamanlamasi", 7, 15, [1, 2, 3, 4, 5]),
    ("Sabah Brifingi · KAP kopyası 18:30", "kap-kopyasi", 18, 30, [-1]),
    ("Sabah Brifingi · KAP kopyası 23:50", "kap-kopyasi", 23, 50, [-1]),
]


def repo_name() -> str:
    try:
        out = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
                             capture_output=True, text=True, check=True, timeout=30)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return input("GitHub deposu (kullanıcı/depo): ").strip()


def github_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
            "User-Agent": "sabah-brifingi-cron"}


def main() -> int:
    repo = repo_name()
    dispatch_url = f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches"
    print(f"Depo: {repo}")

    gh_token = getpass.getpass("GitHub erişim anahtarı (fine-grained, görünmez): ").strip()
    cron_key = getpass.getpass("cron-job.org API anahtarı (görünmez): ").strip()
    if not gh_token or not cron_key:
        print("Hata: iki anahtar da gerekli.")
        return 1

    # 1) GitHub anahtarını gerçek bir tetiklemeyle doğrula (deneme modu: e-posta göndermez)
    print("GitHub anahtarı doğrulanıyor (e-posta göndermeyen bir deneme çalışması başlatılacak)…")
    r = requests.post(dispatch_url, headers=github_headers(gh_token),
                      json={"ref": "main", "inputs": {"mode": "deneme"}}, timeout=30)
    if r.status_code != 204:
        print(f"✗ GitHub tetiklemesi başarısız (HTTP {r.status_code}): {r.text[:200]}")
        print("  Anahtarın bu depoya erişimi ve 'Actions: Read and write' izni olmalı.")
        return 2
    print("✓ GitHub anahtarı çalışıyor")

    # 2) Mevcut görevleri listele (aynı başlıklı görevler tekrar oluşturulmaz)
    cron_headers = {"Authorization": f"Bearer {cron_key}", "Content-Type": "application/json"}
    r = requests.get(f"{API}/jobs", headers=cron_headers, timeout=30)
    if r.status_code != 200:
        print(f"✗ cron-job.org API'sine erişilemedi (HTTP {r.status_code}). API anahtarını kontrol edin.")
        return 3
    existing = {j.get("title") for j in r.json().get("jobs", [])}

    # 3) Görevleri oluştur
    for title, mode, hour, minute, wdays in JOBS:
        if title in existing:
            print(f"• Zaten var, atlandı: {title}")
            continue
        job = {
            "url": dispatch_url,
            "enabled": True,
            "title": title,
            "saveResponses": False,
            "requestMethod": 1,                    # POST
            "requestTimeout": 30,
            "extendedData": {
                "headers": github_headers(gh_token),
                "body": json.dumps({"ref": "main", "inputs": {"mode": mode}}),
            },
            "schedule": {"timezone": TZ, "expiresAt": 0, "hours": [hour], "minutes": [minute],
                         "mdays": [-1], "months": [-1], "wdays": wdays},
        }
        r = requests.put(f"{API}/jobs", headers=cron_headers, json={"job": job}, timeout=30)
        if r.status_code != 200:
            print(f"✗ Oluşturulamadı: {title} (HTTP {r.status_code}): {r.text[:200]}")
            return 4
        print(f"✓ Oluşturuldu: {title} (görev no {r.json().get('jobId')})")
        time.sleep(1.5)                            # API sınırı: saniyede 1, dakikada 5 oluşturma

    print("\nKurulum tamam. Bülten hafta içi 07:15'te dakikası dakikasına tetiklenecek (gönderim 08:15).")
    print("GitHub'ın kendi zamanlayıcısı yedek olarak kalır; o gün bülten gönderildiyse ikinci kez göndermez.")
    print("Not: GitHub erişim anahtarının bitiş tarihi geldiğinde yenileyip bu betiği tekrar çalıştırın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
