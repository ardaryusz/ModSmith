; ==========================================================================
; ModSmith Windows Installer — NSIS Script
; ==========================================================================
;
; Installs modsmith.exe to Program Files and creates a user-writable
; workspace under Documents\ModSmith.
;
; Build:
;   makensis installer\ModSmithInstaller.nsi
;
; Prerequisites:
;   - dist\ModSmith\ must exist (run scripts\build_exe.ps1 first)
;   - NSIS 3.x on PATH
; ==========================================================================

!include "MUI2.nsh"
!include "EnvVarUpdate.nsh"

; --------------------------------------------------------------------------
; General
; --------------------------------------------------------------------------

!define PRODUCT_NAME      "ModSmith"
!define PRODUCT_VERSION   "1.0.0"
!define PRODUCT_PUBLISHER "ModSmith Project"
!define PRODUCT_WEB       "https://github.com/modsmith"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\dist\installer\ModSmithSetup.exe"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKCU "Software\${PRODUCT_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; --------------------------------------------------------------------------
; MUI Settings
; --------------------------------------------------------------------------

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; --------------------------------------------------------------------------
; Variables
; --------------------------------------------------------------------------

Var UserDataDir

; --------------------------------------------------------------------------
; Installer Sections
; --------------------------------------------------------------------------

Section "!ModSmith Core (required)" SEC_CORE
    SectionIn RO

    ; --- Application files to Program Files ---
    SetOutPath "$INSTDIR"
    File /r "..\dist\ModSmith\*.*"
    File "..\README.md"

    ; --- Determine user data directory ---
    ; Use $DOCUMENTS which resolves to the current user's Documents folder
    StrCpy $UserDataDir "$DOCUMENTS\${PRODUCT_NAME}"

    ; --- Create user data folder structure ---
    CreateDirectory "$UserDataDir"
    CreateDirectory "$UserDataDir\MODTEMPLATES"
    CreateDirectory "$UserDataDir\WORKSPACE"
    CreateDirectory "$UserDataDir\WORKSPACE\RECIPES"
    CreateDirectory "$UserDataDir\WORKSPACE\README"
    CreateDirectory "$UserDataDir\WORKSPACE\DETAILS"
    CreateDirectory "$UserDataDir\WORKSPACE\DIST"
    CreateDirectory "$UserDataDir\MODS"

    ; --- Install sample files ---
    SetOutPath "$UserDataDir\WORKSPACE\DETAILS"
    File "..\installer\modsmith.example.json"

    SetOutPath "$UserDataDir\MODTEMPLATES"
    File "..\installer\template-descriptor.example.json"

    ; --- Set MODSMITH_HOME environment variable (user-level) ---
    ; This makes modsmith.exe automatically find the user's workspace
    ${EnvVarUpdate} $0 "MODSMITH_HOME" "A" "HKCU" "$UserDataDir"

    ; --- Write registry keys for uninstaller ---
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "UserDataDir" "$UserDataDir"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "InstallLocation" "$INSTDIR"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "NoRepair" 1

    ; --- Create uninstaller ---
    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd


Section "Add to PATH" SEC_PATH
    ; Add install dir to user PATH so modsmith.exe is available globally
    ${EnvVarUpdate} $0 "PATH" "A" "HKCU" "$INSTDIR"
SectionEnd


Section "Start Menu Shortcut" SEC_STARTMENU
    ; Create a "ModSmith Command Prompt" shortcut that opens PowerShell
    ; in the user's workspace directory
    StrCpy $UserDataDir "$DOCUMENTS\${PRODUCT_NAME}"
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"

    ; PowerShell shortcut opening in the user data directory
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\ModSmith Command Prompt.lnk" \
        "powershell.exe" \
        "-NoExit -Command $\"Set-Location '$UserDataDir'; Write-Host 'ModSmith Workspace: $UserDataDir' -ForegroundColor Cyan; Write-Host 'Run: modsmith --help' -ForegroundColor Yellow$\"" \
        "" "" "" "" "Open PowerShell in ModSmith workspace"

    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ModSmith.lnk" \
        "$INSTDIR\Uninstall.exe"
SectionEnd


; --------------------------------------------------------------------------
; Section Descriptions
; --------------------------------------------------------------------------

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE} \
        "Install ModSmith executable and create workspace folders under Documents."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_PATH} \
        "Add the installation directory to your PATH so you can run modsmith from any terminal."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} \
        "Create a Start Menu shortcut that opens PowerShell in your ModSmith workspace."
!insertmacro MUI_FUNCTION_DESCRIPTION_END


; --------------------------------------------------------------------------
; Uninstaller
; --------------------------------------------------------------------------

Section "Uninstall"
    ; --- Remove application files ---
    RMDir /r "$INSTDIR"

    ; --- Remove from PATH ---
    ${un.EnvVarUpdate} $0 "PATH" "R" "HKCU" "$INSTDIR"

    ; --- Remove MODSMITH_HOME ---
    ; Read the stored user data dir before removing registry keys
    ReadRegStr $UserDataDir HKCU "Software\${PRODUCT_NAME}" "UserDataDir"
    ${un.EnvVarUpdate} $0 "MODSMITH_HOME" "R" "HKCU" "$UserDataDir"

    ; --- Remove Start Menu shortcuts ---
    RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"

    ; --- Remove registry keys ---
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
    DeleteRegKey HKCU "Software\${PRODUCT_NAME}"

    ; --- User data: do NOT delete by default ---
    ; The Documents\ModSmith folder contains user templates, recipes,
    ; generated mods, and built JARs.  We intentionally leave it intact.
    ;
    ; To offer optional removal, uncomment the following:
    ; MessageBox MB_YESNO "Remove your ModSmith user data folder?$\n$\n$UserDataDir$\n$\nThis will delete all templates, recipes, generated mods, and built JARs." IDNO +2
    ;     RMDir /r "$UserDataDir"
SectionEnd
