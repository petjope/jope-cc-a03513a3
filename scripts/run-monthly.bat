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
REM
REM Regle posee par Jeremy le 04/09/2026 : une page part DANS TOUS LES CAS.
REM Si l'agent ne produit rien, on publie une page de statut qui dit ou est
REM le probleme, et le run est retente le lendemain.

setlocal enabledelayedexpansion
set "PROJ=%USERPROFILE%\OneDrive\Documents\Jope\Claude Code\Projects\jope-cc-dashboard-starter"
cd /d "%PROJ%" || exit /b 1

for /f %%i in ('powershell -NoProfile -Command "(Get-Date).Day"') do set DAY=%%i
for /f usebackq %%i in (`powershell -NoProfile -Command "(Get-Date).AddMonths(-1).ToString('yyyy-MM')"`) do set MONTH=%%i
for /f usebackq %%i in (`powershell -NoProfile -Command "(Get-Date).AddMonths(-1).ToString('MMMM yyyy',[Globalization.CultureInfo]::GetCultureInfo('en-US'))"`) do set MLABEL=%%i
for /f usebackq %%i in (`powershell -NoProfile -Command "(Get-Date).AddMonths(-1).ToString('MMMM',[Globalization.CultureInfo]::GetCultureInfo('en-US'))"`) do set MNAME=%%i
for /f usebackq %%i in (`powershell -NoProfile -Command "(Get-Date).AddMonths(-1).Year"`) do set MYEAR=%%i
set "MLABEL=%MNAME% %MYEAR%"

echo ==== %DATE% %TIME% : reveil, jour %DAY%, mois cible %MONTH% ==== >> run.log

REM Jour de livraison : le 5, sauf quand le 5 tombe un week-end. Dans ce cas on
REM prend le jour ouvre le plus proche du 5 (regle de Jeremy du 4 septembre 2026) :
REM   samedi 5  -> vendredi 4
REM   dimanche 5 -> lundi 6
REM Cette regle remplace et generalise l exception ponctuelle de septembre 2026,
REM qui etait codee en dur sur le mois cible 2026-08 : le 5 septembre 2026 tombant
REM un samedi, la regle rend 4 toute seule. Verifie sur 14 mois : le jour retenu
REM n est jamais un samedi ni un dimanche.
REM Le rattrapage reste actif : si le PC est eteint le jour J, la tache retente
REM le lendemain et les jours suivants, le marqueur .done empechant tout doublon.
for /f usebackq %%i in (`powershell -NoProfile -Command "$d5 = Get-Date -Day 5; switch ($d5.DayOfWeek) { 'Saturday' { 4 } 'Sunday' { 6 } default { 5 } }"`) do set MINDAY=%%i
if not defined MINDAY set MINDAY=5
echo      jour de livraison retenu ce mois-ci : le %MINDAY% >> run.log

if %DAY% LSS %MINDAY% (
  echo      rien a faire avant le %MINDAY% >> run.log
  goto :fin
)
if exist "data\.done-%MONTH%" (
  echo      %MONTH% deja livre, rien a faire >> run.log
  goto :fin
)
if "%CC_PASSPHRASE%"=="" (
  echo ==== %DATE% %TIME% : ECHEC %MONTH% - CC_PASSPHRASE absente, rien publie ==== >> run.log
  goto :fin
)

echo      generation du dashboard %MONTH% >> run.log

REM IMPORTANT : "call". Sur PATH, claude se resout en claude.cmd. Appeler un .cmd
REM depuis un .bat SANS call transfere le controle definitivement et ce script ne
REM reprend jamais la main : c'est ce qui a fait echouer le run du 04/09/2026 en
REM silence, sans ligne OK ni ECHEC et sans marqueur .done. Ne pas retirer le call.
call claude -p "/cc-monthly" --permission-mode acceptEdits --allowedTools "mcp__claude_ai_Gorgias_connector__get_gaia_instructions,mcp__claude_ai_Gorgias_connector__query,mcp__claude_ai_Gorgias_connector__get_tables,mcp__claude_ai_Gorgias_connector__get_table_metadata,mcp__claude_ai_Shopify__graphql_query,mcp__claude_ai_Shopify__run-analytics-query,mcp__claude_ai_Google_Drive__search_files,mcp__claude_ai_Google_Drive__get_file_metadata,mcp__claude_ai_Google_Drive__read_file_content,mcp__claude_ai_Google_Drive__download_file_content,mcp__claude_ai_Windsor_ai__get_data,mcp__claude_ai_Windsor_ai__get_fields,mcp__claude_ai_Gmail__send_message,Read,Write,Edit,Glob,Grep,Bash(git *),Bash(python *),Bash(node *)" >> run.log 2>&1
set CLAUDE_RC=%ERRORLEVEL%
echo      claude termine, code %CLAUDE_RC% >> run.log

REM Preuve de succes : l'archive du mois doit exister ET avoir ete ecrite aujourd'hui.
REM (verifier la seule existence ne suffit pas : une archive d'un run precedent
REM  ferait passer un echec pour un succes)
set RES=KO
for /f usebackq %%i in (`powershell -NoProfile -Command "$f='docs\archive\%MONTH%.html'; if ((Test-Path $f) -and ((Get-Item $f).LastWriteTime.Date -eq (Get-Date).Date)) {'OK'} else {'KO'}"`) do set RES=%%i

if "!RES!"=="OK" (
  echo done > "data\.done-%MONTH%"
  echo ==== %DATE% %TIME% : OK %MONTH% livre ==== >> run.log
  goto :fin
)

REM ---- Echec : on publie quand meme une page qui dit ou est le probleme ----
echo      echec de generation, publication de la page de statut >> run.log
node scripts\build_status_page.js "%MONTH%" "%MLABEL%" "%TEMP%\cc-status-%MONTH%.html" "run.log" >> run.log 2>&1
if errorlevel 1 (
  echo ==== %DATE% %TIME% : ECHEC %MONTH% - page de statut non generee ==== >> run.log
  goto :fin
)
node scripts\encrypt_page.js "%TEMP%\cc-status-%MONTH%.html" "docs\index.html" "%MLABEL%" >> run.log 2>&1
if errorlevel 1 (
  echo ==== %DATE% %TIME% : ECHEC %MONTH% - chiffrement de la page de statut impossible ==== >> run.log
  goto :fin
)
del "%TEMP%\cc-status-%MONTH%.html" >nul 2>&1

REM On ne touche jamais a docs\archive : une archive publiee n'est pas ecrasee,
REM et une archive de statut ferait croire que le mois a ete livre.
git add -A >> run.log 2>&1
git commit -m "CC dashboard %MONTH% : echec de generation, page de statut" >> run.log 2>&1
git push >> run.log 2>&1
echo ==== %DATE% %TIME% : ECHEC %MONTH% - page de statut publiee, nouvelle tentative demain 9h00 ==== >> run.log

REM Prevenir Jeremy. C'est le silence de l'echec du 04/09/2026 qui a coute une
REM journee : une page de statut ne sert a rien si personne ne va la regarder.
REM Passe par le connecteur Gmail de la session claude, donc sans identifiants
REM SMTP a stocker. Si claude est lui-meme en cause, l'envoi echoue aussi et la
REM page de statut reste le seul signal : c'est accepte, pas une regression.
call claude -p "Envoie un email court en anglais a jeremy@petjope.com, et a personne d'autre. Objet : 'Jope CC Dashboard %MONTH% - generation failed'. Dis que le run mensuel du dashboard %MONTH% a echoue ce matin, qu'une page de statut nommant l'etape fautive a ete publiee a la place sur %PAGES_URL%, et que la tache retentera automatiquement demain a 9h00. N'ecris aucune phrase de passe. N'ajoute rien d'autre." --permission-mode acceptEdits --allowedTools "mcp__claude_ai_Gmail__send_message" >> run.log 2>&1
echo      notification d'echec envoyee (code %ERRORLEVEL%) >> run.log

:fin
endlocal
