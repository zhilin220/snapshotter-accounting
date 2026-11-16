@echo off
title SnapShotter
cd /d "%~dp0"
py snapshotter.py
if errorlevel 1 pause
