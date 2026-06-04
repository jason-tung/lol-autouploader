.PHONY: run build install release

run:
	python -u main.py

install:
	pip install -r requirements.txt

build:
	pip install pyinstaller -q
	python make_icon.py
	python -m PyInstaller --onefile --name autouploader --noconsole \
		--icon icon.ico \
		--add-data "icon.png;." \
		--hidden-import googleapiclient \
		--hidden-import googleapiclient.discovery \
		--hidden-import googleapiclient.http \
		--hidden-import google_auth_oauthlib \
		--hidden-import google_auth_oauthlib.flow \
		--hidden-import google.auth.transport.requests \
		--hidden-import cachetools.func \
		--hidden-import pystray._win32 \
		--collect-all googleapiclient \
		--collect-all google_auth_oauthlib \
		--collect-all PIL \
		main.py
	-copy config.json dist\config.json
	@echo === Build complete. Copy client_secrets.json into dist\ before running. ===

release:
	@if "$(VERSION)"=="" (echo ERROR: Specify version: make release VERSION=1.2.3 && exit 1)
	python do_release.py $(VERSION) $(NOTES)
