@echo off
REM Example launcher. Edit SEMANTIC_DB to your holographic fact store.
if "%SEMANTIC_DB%"=="" set SEMANTIC_DB=%USERPROFILE%\.hermes\memory_store.db
if "%SEMANTIC_MODEL%"=="" set SEMANTIC_MODEL=%~dp0models\bge-m3
if "%SEMANTIC_PORT%"=="" set SEMANTIC_PORT=8791
python "%~dp0server.py"