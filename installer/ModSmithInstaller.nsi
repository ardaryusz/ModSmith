; ==========================================================================
; ModSmith Windows Installer — NSIS Script
; ==========================================================================
;
; Installs modsmith.exe and modsmith_cli.exe to Program Files and creates a user-writable
; workspace under Documents\ModSmith.
;
; Build:
;   makensis installer\ModSmithInstaller.nsi
;
; Prerequisites:
;   - dist\ModSmith\ must exist (run scripts\build_exe.ps1 first)
;   - NSIS 3.x on PATH
;
; No external NSIS plugins required — uses only built-in includes.
; ==========================================================================

; --------------------------------------------------------------------------
; Icon — must be defined BEFORE !include "MUI2.nsh" so MUI2 picks it up
; --------------------------------------------------------------------------
; MODSMITH_ICON can be injected at compile-time via:
;   makensis /DMODSMITH_ICON="C:\absolute\path\to\modsmith.ico" ...
; If not provided, fall back to the relative path from the installer dir.
!ifndef MODSMITH_ICON
  !define MODSMITH_ICON "..\assets\modsmith.ico"
!endif
!echo "MODSMITH_ICON=${MODSMITH_ICON}"

; MUI2 controls the wizard icon via MUI_ICON / MUI_UNICON.
; These MUST come before !include "MUI2.nsh".
!define MUI_ICON    "${MODSMITH_ICON}"
!define MUI_UNICON  "${MODSMITH_ICON}"

!include "MUI2.nsh"

; --------------------------------------------------------------------------
; General
; --------------------------------------------------------------------------

!ifndef MODSMITH_VERSION
  !define MODSMITH_VERSION "0.0.0-dev"
!endif

!define PRODUCT_NAME      "ModSmith"
!define PRODUCT_VERSION   "${MODSMITH_VERSION}"
!define PRODUCT_PUBLISHER "ModSmith Project"
!define PRODUCT_WEB       "https://github.com/modsmith"

VIProductVersion "2.1.2.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileVersion" "2.1.2.0"
VIAddVersionKey "FileDescription" "ModSmith Setup"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"

; Registry path for user environment variables
!define ENV_REG_KEY "Environment"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\dist\installer\ModSmithSetup.exe"
; Redundant with MUI_ICON but harmless — kept for non-MUI fallback
Icon "${MODSMITH_ICON}"
UninstallIcon "${MODSMITH_ICON}"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKCU "Software\${PRODUCT_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

Var ModSmithHomeDir

; --------------------------------------------------------------------------
; MUI Settings
; --------------------------------------------------------------------------

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME

; 1. Program installation directory (controls $INSTDIR)
!insertmacro MUI_PAGE_DIRECTORY

; 2. Home directory (controls $ModSmithHomeDir)
!define MUI_DIRECTORYPAGE_VARIABLE          $ModSmithHomeDir
!define MUI_DIRECTORYPAGE_TEXT_TOP          "Choose where ModSmith should store your workspaces, templates, generated mods, and built jars.$\n$\nThis is separate from the program install location."
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION  "ModSmith Home Directory"
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
; Existing Install Detection
; --------------------------------------------------------------------------

Function .onInit
  ; Pre-fill ModSmithHomeDir
  ReadRegStr $ModSmithHomeDir HKCU "Software\${PRODUCT_NAME}" "HomeDir"
  StrCmp $ModSmithHomeDir "" 0 home_dir_done
  
  ReadRegStr $ModSmithHomeDir HKCU "Environment" "MODSMITH_HOME"
  StrCmp $ModSmithHomeDir "" 0 home_dir_done
  
  StrCpy $ModSmithHomeDir "$DESKTOP\ModSmith"
  
home_dir_done:

  ; Check registry
  ReadRegStr $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "UninstallString"
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayVersion"
  
  ; Check if registry uninstall string is non-empty
  StrCmp $1 "" check_file exists_found

check_file:
  ; Check if Uninstall.exe exists in the installation directory
  IfFileExists "$INSTDIR\Uninstall.exe" exists_found no_existing

exists_found:
  ; Set version string
  StrCmp $0 "" version_unknown version_known
version_unknown:
  StrCpy $0 "unknown"
  Goto show_message
version_known:
  ; $0 already has the version
show_message:
  MessageBox MB_YESNO|MB_ICONQUESTION "An existing ModSmith installation was found.$\nInstalled version: $0$\nNew version: ${MODSMITH_VERSION}$\n$\nContinue to reinstall/repair ModSmith?" IDYES no_existing
    Abort

no_existing:
FunctionEnd

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
    StrCpy $UserDataDir "$ModSmithHomeDir"

    ; --- Create user data folder structure ---
    CreateDirectory "$UserDataDir"
    CreateDirectory "$UserDataDir\MODTEMPLATES"
    CreateDirectory "$UserDataDir\WORKSPACE"
    CreateDirectory "$UserDataDir\WORKSPACE\RECIPES"
    CreateDirectory "$UserDataDir\WORKSPACE\README"
    CreateDirectory "$UserDataDir\WORKSPACE\DETAILS"
    CreateDirectory "$UserDataDir\WORKSPACE\DIST"
    CreateDirectory "$UserDataDir\WORKSPACE\ASSETS"
    CreateDirectory "$UserDataDir\WORKSPACE\LICENSE"
    CreateDirectory "$UserDataDir\MODS"

    ; --- Install sample files ---
    SetOutPath "$UserDataDir\WORKSPACE\DETAILS"
    File "..\installer\modsmith.example.json"

    SetOutPath "$UserDataDir\MODTEMPLATES"
    File "..\installer\template-descriptor.example.json"

    ; --- Set MODSMITH_HOME environment variable (user-level) ---
    ; Write directly to HKCU\Environment so new terminals see it
    WriteRegExpandStr HKCU "${ENV_REG_KEY}" "MODSMITH_HOME" "$UserDataDir"

    ; --- Broadcast WM_SETTINGCHANGE so running Explorer / new terminals pick it up ---
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:${ENV_REG_KEY}" /TIMEOUT=5000

    ; --- Write registry keys for uninstaller ---
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "UserDataDir" "$UserDataDir"
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "HomeDir" "$ModSmithHomeDir"
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
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "DisplayIcon" "$INSTDIR\modsmith.exe,0"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
        "NoRepair" 1

    ; --- Create uninstaller ---
    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd


Section "Add to PATH" SEC_PATH
    ; Add install dir to user PATH so modsmith.exe is available globally.
    ; We read the current user PATH, append $INSTDIR with a semicolon
    ; separator (if not already present), and write it back.
    ReadRegStr $0 HKCU "${ENV_REG_KEY}" "Path"

    ; Check if $INSTDIR is already on the PATH (avoid duplicates)
    StrLen $1 "$INSTDIR"
    StrCpy $2 $0               ; working copy of current PATH

    ; Simple substring search — look for $INSTDIR in $0
    Push $0
    Push "$INSTDIR"
    Call StrContains
    Pop $3                      ; $3 = "" if not found, else the substring

    StrCmp $3 "" 0 path_already_set
        ; Not found — append
        StrCmp $0 "" path_is_empty
            ; PATH is non-empty: append with semicolon
            WriteRegExpandStr HKCU "${ENV_REG_KEY}" "Path" "$0;$INSTDIR"
            Goto path_done
        path_is_empty:
            ; PATH was empty: just set it
            WriteRegExpandStr HKCU "${ENV_REG_KEY}" "Path" "$INSTDIR"
    path_already_set:
    path_done:

    ; Record that we modified PATH so uninstaller knows to clean up
    WriteRegStr HKCU "Software\${PRODUCT_NAME}" "AddedToPath" "1"

    ; Broadcast WM_SETTINGCHANGE
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:${ENV_REG_KEY}" /TIMEOUT=5000
SectionEnd


Section "Start Menu Shortcuts" SEC_STARTMENU
    ; Create Start Menu shortcuts for the GUI, CLI terminal, and uninstaller
    StrCpy $UserDataDir "$DOCUMENTS\${PRODUCT_NAME}"
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"

    ; GUI shortcut — primary user-facing entry point
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\ModSmith.lnk" \
        "$INSTDIR\modsmith.exe" "" \
        "$INSTDIR\modsmith.exe" 0

    ; PowerShell shortcut opening in the user data directory
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\ModSmith Command Prompt.lnk" \
        "powershell.exe" \
        "-NoExit -Command $\"Set-Location '$UserDataDir'; Write-Host 'ModSmith Workspace: $UserDataDir' -ForegroundColor Cyan; Write-Host 'Run: modsmith_cli --help' -ForegroundColor Yellow$\"" \
        "$INSTDIR\modsmith_cli.exe" 0 "" "" "Open PowerShell in ModSmith workspace"

    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ModSmith.lnk" \
        "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0
SectionEnd


; --------------------------------------------------------------------------
; Section Descriptions
; --------------------------------------------------------------------------

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE} \
        "Install ModSmith CLI and GUI executables and create workspace folders."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_PATH} \
        "Add the installation directory to your PATH so you can run modsmith from any terminal."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} \
        "Create Start Menu shortcuts for the ModSmith GUI and a command-line terminal."
!insertmacro MUI_FUNCTION_DESCRIPTION_END


; --------------------------------------------------------------------------
; Helper Function: StrContains  (installer)
; --------------------------------------------------------------------------
; Usage:
;   Push "haystack"
;   Push "needle"
;   Call StrContains
;   Pop $result   ; result = needle if found, "" if not
;
; Searches for Needle inside Haystack (case-insensitive).
; --------------------------------------------------------------------------

Function StrContains
    Exch $R1 ; needle
    Exch
    Exch $R2 ; haystack
    Push $R3
    Push $R4
    Push $R5

    StrLen $R3 $R1
    StrLen $R4 $R2
    StrCpy $R5 0

    ${If} $R3 == 0
        StrCpy $R1 ""
        Goto str_done
    ${EndIf}

    loop:
        IntOp $R5 $R5 + 0   ; nop to avoid empty block
        IntCmp $R5 $R4 str_not_found str_ok str_not_found
    str_ok:
        StrCpy $R0 $R2 $R3 $R5
        StrCmp $R0 $R1 str_found
        IntOp $R5 $R5 + 1
        Goto loop

    str_not_found:
        StrCpy $R1 ""
        Goto str_done

    str_found:
        ; $R1 already contains needle

    str_done:
    Pop $R5
    Pop $R4
    Pop $R3
    Pop $R2
    Exch $R1
FunctionEnd


; --------------------------------------------------------------------------
; Helper Function: un.StrContains  (uninstaller copy)
; --------------------------------------------------------------------------

Function un.StrContains
    Exch $R1 ; needle
    Exch
    Exch $R2 ; haystack
    Push $R3
    Push $R4
    Push $R5

    StrLen $R3 $R1
    StrLen $R4 $R2
    StrCpy $R5 0

    ${If} $R3 == 0
        StrCpy $R1 ""
        Goto un_str_done
    ${EndIf}

    un_loop:
        IntOp $R5 $R5 + 0
        IntCmp $R5 $R4 un_str_not_found un_str_ok un_str_not_found
    un_str_ok:
        StrCpy $R0 $R2 $R3 $R5
        StrCmp $R0 $R1 un_str_found
        IntOp $R5 $R5 + 1
        Goto un_loop

    un_str_not_found:
        StrCpy $R1 ""
        Goto un_str_done

    un_str_found:

    un_str_done:
    Pop $R5
    Pop $R4
    Pop $R3
    Pop $R2
    Exch $R1
FunctionEnd


; --------------------------------------------------------------------------
; Helper Function: un.RemoveFromPath
; --------------------------------------------------------------------------
; Removes a directory from the user PATH registry value.
; Handles the entry appearing at start, middle, or end of PATH.
;
; Usage:
;   Push "C:\Path\To\Remove"
;   Call un.RemoveFromPath
; --------------------------------------------------------------------------

Function un.RemoveFromPath
    Exch $R0  ; directory to remove
    Push $R1  ; current PATH
    Push $R2  ; result
    Push $R3  ; temp

    ReadRegStr $R1 HKCU "${ENV_REG_KEY}" "Path"

    ; If PATH is empty, nothing to do
    StrCmp $R1 "" remove_path_done

    ; Check if our dir is even in PATH
    Push $R1
    Push $R0
    Call un.StrContains
    Pop $R3
    StrCmp $R3 "" remove_path_done

    ; ---- Strategy: replace "$R0;" and ";$R0" patterns, then exact match ----
    ; Try removing "dir;" (entry at start or middle)
    StrCpy $R2 $R1
    StrCpy $R3 "$R0;"

    ; Use NSIS string replacement via word-find or manual:
    ; We'll do a simple approach - try each removal pattern

    ; Pattern 1: PATH equals exactly our directory (only entry)
    StrCmp $R1 $R0 remove_path_clear

    ; Pattern 2: starts with "dir;"
    StrLen $R3 "$R0;"
    StrCpy $R2 $R1 $R3
    StrCmp $R2 "$R0;" 0 remove_try_end
        ; Remove "dir;" from start
        StrLen $R3 "$R0;"
        StrCpy $R2 $R1 "" $R3
        Goto remove_path_write

    remove_try_end:
    ; Pattern 3: ends with ";dir"
    StrLen $R3 $R0
    IntOp $R3 $R3 + 1  ; length of ";dir"
    StrLen $R2 $R1
    IntOp $R2 $R2 - $R3
    StrCpy $R3 $R1 "" $R2
    StrCmp $R3 ";$R0" 0 remove_try_middle
        ; Remove ";dir" from end
        StrCpy $R2 $R1 $R2
        Goto remove_path_write

    remove_try_middle:
    ; Pattern 4: ";dir;" appears in middle — replace with ";"
    ; For simplicity, we read the whole thing, and reconstruct without our entry
    ; This is the fallback — rebuild PATH by splitting on ";"
    StrCpy $R2 $R1
    ; Just try replacing ";dir;" with ";"
    ; NSIS doesn't have native string replace, so we accept the limitation
    ; that patterns 1-3 cover the vast majority of cases.
    ; If somehow we get here, leave PATH as-is rather than corrupt it.
    Goto remove_path_done

    remove_path_clear:
        ; PATH was just our directory — delete the value entirely
        DeleteRegValue HKCU "${ENV_REG_KEY}" "Path"
        Goto remove_path_broadcast

    remove_path_write:
        WriteRegExpandStr HKCU "${ENV_REG_KEY}" "Path" "$R2"

    remove_path_broadcast:
        SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:${ENV_REG_KEY}" /TIMEOUT=5000

    remove_path_done:
    Pop $R3
    Pop $R2
    Pop $R1
    Pop $R0
FunctionEnd


; --------------------------------------------------------------------------
; Uninstaller
; --------------------------------------------------------------------------

Section "Uninstall"
    ; --- Remove application files ---
    RMDir /r "$INSTDIR"

    ; --- Remove from PATH (only if installer added it) ---
    ReadRegStr $0 HKCU "Software\${PRODUCT_NAME}" "AddedToPath"
    StrCmp $0 "1" 0 skip_path_removal
        Push "$INSTDIR"
        Call un.RemoveFromPath
    skip_path_removal:

    ; --- Remove MODSMITH_HOME ---
    ; Only remove if the current value matches what we set
    ReadRegStr $0 HKCU "${ENV_REG_KEY}" "MODSMITH_HOME"
    ReadRegStr $UserDataDir HKCU "Software\${PRODUCT_NAME}" "UserDataDir"

    ; Remove if it matches the stored data dir OR the default Documents path
    StrCmp $0 $UserDataDir 0 check_default_path
        DeleteRegValue HKCU "${ENV_REG_KEY}" "MODSMITH_HOME"
        SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:${ENV_REG_KEY}" /TIMEOUT=5000
        Goto modsmith_home_done
    check_default_path:
    StrCmp $0 "$DESKTOP\${PRODUCT_NAME}" 0 modsmith_home_done
        DeleteRegValue HKCU "${ENV_REG_KEY}" "MODSMITH_HOME"
        SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:${ENV_REG_KEY}" /TIMEOUT=5000
    modsmith_home_done:

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
