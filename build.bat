@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building exe...
pyinstaller --onefile --name autouploader ^
  --hidden-import googleapiclient ^
  --hidden-import google_auth_oauthlib ^
  --hidden-import google.auth.transport.requests ^
  main.py

echo.
echo Done! Exe is at dist\autouploader.exe
echo Copy config.json and client_secrets.json next to the exe before running.
pause
