:: start_watcher.bat
@echo off
echo Starting SANParks Availability Watcher...
echo Keep this window open! Closing it will stop the background checks.

:: Open the default browser to the local server address
start "" http://127.0.0.1:5000

:: Run the python application
python app.py
pause