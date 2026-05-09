@echo off
echo Installing Vera dependencies...
cd /d "%~dp0"
venv\Scripts\python.exe -m pip install SpeechRecognition pyaudio pystray pillow --quiet
echo.
echo Creating desktop shortcut...
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%USERPROFILE%\Desktop\Vera.lnk'); $SC.TargetPath = '%~dp0Vera.bat'; $SC.IconLocation = '%~dp0icon.ico'; $SC.WorkingDirectory = '%~dp0'; $SC.Save()"
echo.
echo Done! You can now launch Vera from your desktop.
pause
