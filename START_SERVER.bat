@echo off
title AuraCare Hospital System - Starting Server...
color 0A
echo.
echo  ============================================
echo    AuraCare Smart Hospital Appointment System
echo  ============================================
echo.
echo  [*] Starting Flask web server...
echo  [*] Please wait a few seconds...
echo.

if not exist "C:\Users\bhara\.local\bin\uv.exe" (
    echo  [ERROR] uv.exe not found.
    pause
    exit
)

echo  [OK] uv found. Launching Flask server...
echo.
echo  ============================================
echo   Website URL: http://127.0.0.1:5000
echo   Admin Login: admin@hospital.com / admin123
echo   Doctor Login: doctor1@hospital.com / doctor123
echo  ============================================
echo.
echo  DO NOT CLOSE THIS WINDOW while using the website.
echo.

C:\Users\bhara\.local\bin\uv.exe run --with werkzeug --with flask app.py

pause