PY ?= .venv/bin/python

.PHONY: install test mock run schedule terminal terminal-build email-setup schedule-install schedule-uninstall send-test media-server cloud-setup

install:
	python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt
	@test -f .env || cp .env.example .env

test:            ## Birim + entegrasyon testleri (dış servis çağrısı yok)
	$(PY) -m pytest -q

mock:            ## Sahte veriyle uçtan uca boru hattı (e-posta yerine .eml yazar)
	$(PY) main.py --mock --no-wait

run:             ## Gerçek veriyle şimdi çalıştır, 08:15'te gönder
	$(PY) main.py --now

schedule:        ## Hafta içi 07:30 zamanlayıcısı
	$(PY) main.py --schedule

NODE ?= $(HOME)/.local/node/bin
terminal:        ## AURA TERMINAL geliştirme sunucusu (http://localhost:5173)
	cd terminal && PATH=$(NODE):$$PATH npm install --silent && PATH=$(NODE):$$PATH npm run dev

terminal-build:  ## AURA TERMINAL üretim derlemesi → terminal/dist (statik, herhangi bir web sunucusunda çalışır)
	cd terminal && PATH=$(NODE):$$PATH npm run build

email-setup:     ## Gmail gönderim kurulumu (uygulama şifresi gizli girilir, giriş doğrulanır)
	$(PY) scripts/setup_email.py

send-test:       ## Gerçek veriyle hemen çalıştır ve bülteni kendi adresinize GÖNDER
	$(PY) main.py --now --no-wait

schedule-install:   ## Mac'te arka plan servisi kur (hafta içi 07:30 / 08:15)
	./scripts/install_schedule.sh

schedule-uninstall: ## Arka plan servisini kaldır
	./scripts/uninstall_schedule.sh

media-server:    ## E-postadaki "Dinle" bağlantıları için yerel medya sunucusu (zamanlayıcı kurulu değilse)
	$(PY) -m agents.media_server

cloud-setup:     ## GitHub'a yükle + Secrets + ilk bulut çalışması + GitHub Pages (gh CLI gerekir)
	./scripts/cloud_setup.sh
