#define AppVersion "0.2.0"
#define AppName "AION 2 Graphics Studio"

[Setup]
AppId={{8D9B3F4A-60E2-49B0-B8DA-720F0FF6A5C1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Darkeys14
AppPublisherURL=https://github.com/Darkeys14/AION2-Graphics-Studio
AppSupportURL=https://github.com/Darkeys14/AION2-Graphics-Studio/issues
AppUpdatesURL=https://github.com/Darkeys14/AION2-Graphics-Studio/releases
DefaultDirName={localappdata}\Programs\AION2GraphicsStudio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern dark
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\AION2GraphicsStudio.exe
AppMutex=Local\AION2GraphicsStudio
OutputDir=..\release
OutputBaseFilename=AION2-Graphics-Studio-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=Установка AION 2 Graphics Studio
VersionInfoProductName={#AppName}
UninstallDisplayName={#AppName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "..\dist\AION2GraphicsStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "Инструкция.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\AION2GraphicsStudio.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AION2GraphicsStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AION2GraphicsStudio.exe"; Description: "Запустить AION 2 Graphics Studio"; Flags: nowait postinstall skipifsilent

; No UninstallDelete rules: configuration backups live outside {app} and survive uninstall.
