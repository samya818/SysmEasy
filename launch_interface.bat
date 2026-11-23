@echo off
title SysmEasy - Plateforme SysML v2 (ENSAM Meknes)
echo ========================================================
echo  Lancement de SysmEasy : Studio SysML v2 & Invariants
echo  Projet de Fin d'Etudes - ENSAM Meknes
echo ========================================================
cd /d "%~dp0"
start http://localhost:8000
python server.py
pause
