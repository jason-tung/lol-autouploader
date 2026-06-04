.PHONY: run build install

run:
	python -u main.py

install:
	pip install -r requirements.txt

build:
	pip install pyinstaller -q
	python -m PyInstaller --onefile --name autouploader --noconsole \
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
	copy config.json dist\config.json
	@echo.
	@echo === Build complete ===
	@echo Copy client_secrets.json into dist\ then pin dist\autouploader.exe to your taskbar.
