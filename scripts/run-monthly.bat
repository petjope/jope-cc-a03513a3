@echo off
REM ============================================================
REM Jope CC Dashboard - run mensuel avec rattrapage automatique
REM ============================================================
REM Le Planificateur de taches lance ce script TOUS LES JOURS a 9h00.
REM Le script ne fait quelque chose que si :
REM   - on est au moins le 5 du mois, ET
REM   - le dashboard du mois precedent n'a pas deja ete livre.
REM Donc si le PC est eteint le 5, la tache retente le 6, le 7, etc.
REM jusqu'a ce qu'elle passe. Aucun doublon possible.
REM Log : run.log a la racine du projet.

setlocal enabledelayedexpansion
set "PROJ=%USERPROFILE%\OneDrive\Documents\Jope\Claude Code\Projects\jope-cc-dashboard-starter"
cd /d "%PROJ%" || exit /b 1

for /f %%i in ('powershell -NoProfile -Command "(Get-Date).Day"') do set DAY=%%i
for /f usebackq %%i in (`powershell -NoProfile -Command "(Get-Date).AddMonths(-1).ToString('yyyy-MM')"`) do set MONTH=%%i

echo ==== %DATE% %TIME% : reveil, jour %DAY%, mois cible %MONTH% ==== >> run.log

if %DAY% LSS 5 (
  echo      rien a faire avant le 5 >> run.log
  exit /b 0
)
if exist "data\.done-%MONTH%" (
  echo      %MONTH% deja livre, rien a faire >> run.log
  exit /b 0
)

echo      generation du dashboard %MONTH% >> run.log

claude -p "/cc-monthly" --permission-mode acceptEdits --allowedTools "mcp__claude_ai_Gorgias_connector__get_gaia_instructions,mcp__claude_ai_Gorgias_connector__query,mcp__claude_ai_Gorgias_connector__get_tables,mcp__claude_ai_Gorgias_connector__get_table_metadata,mcp__claude_ai_Shopify__graphql_query,mcp__claude_ai_Shopify__run-analytics-query,mcp__claude_ai_Gmail__send_message,Read,Write,Edit,Glob,Grep,Bash(git *),Bash(python *),Bash(node *)" >> run.log 2>&1

REM Preuve de succes : l'archive du mois doit exister ET avoir ete ecrite aujourd'hui.
REM (verifier la seule existence ne suffit pas : une archive d'un run precedent
REM  ferait passer un echec pour un succes)
set RES=KO
for /f usebackq %%i in (`powershell -NoProfile -Command "$f='docs\archive\%MONTH%.html'; if ((Test-Path $f) -and ((Get-Item $f).LastWriteTime.Date -eq (Get-Date).Date)) {'OK'} else {'KO'}"`) do set RES=%%i

if "!RES!"=="OK" (
  echo done > "data\.done-%MONTH%"
  echo ==== %DATE% %TIME% : OK %MONTH% livre ==== >> run.log
) else (
  echo ==== %DATE% %TIME% : ECHEC %MONTH% - nouvelle tentative demain 9h00 ==== >> run.log
)
endlocal
