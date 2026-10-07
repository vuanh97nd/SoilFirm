; =====================================================================
; BẢNG CẤU HÌNH INNO SETUP - SOILFIRM PRO
; Đã bổ sung cơ chế copy logo vào {app} và gán icon chuẩn cho shortcut/gỡ cài đặt
; =====================================================================

#define MyAppName "SoilFirm Pro"
#define MyAppVersion "2026.11"
#define MyAppPublisher "Vũ Ngọc Ánh"
#define MyAppURL "https://github.com/vuanh97nd/SoilFirm"
#define MyAppExeName "SoilFirm_Professional.exe"
#define MyIconName "SoilFirm_Pro_2026_11.ico"

; Đường dẫn thư mục dist sau khi chạy PyInstaller
#define BuildDir "dist\SoilFirm_Professional"
#define MyAppExeSource AddBackslash(SourcePath) + BuildDir + "\" + MyAppExeName
#define RuntimeDir AddBackslash(SourcePath) + BuildDir + "\_internal"
#define BaseLibrarySource RuntimeDir + "\base_library.zip"
#define TemplateSource RuntimeDir + "\Data_Import_Mau.xlsx"
#define IntroSource RuntimeDir + "\SoilFirm_Gioi_thieu_30s.mp4"
; Chỉ đóng gói bản onedir do build_app.py tạo, không dùng EXE rời cũ.
#define MyIconSource AddBackslash(SourcePath) + "logo.ico"

; Chặn bản build thiếu EXE/runtime trước khi compile setup
#if !FileExists(MyAppExeSource)
  #error "Khong tim thay file .exe trong thu muc dist. Vui long chay PyInstaller truoc khi build Setup."
#endif

#if !FileExists(MyIconSource)
  #error "Khong tim thay file logo.ico o cung thu muc voi file .iss nay."
#endif

#if !FileExists(BaseLibrarySource)
  #error "Thieu _internal\base_library.zip. Hay chay python build_for_setup.py de build day du."
#endif
#if !FileExists(TemplateSource)
  #error "Thieu _internal\Data_Import_Mau.xlsx. Khong tao Setup tu ban build nay."
#endif
#if !FileExists(IntroSource)
  #error "Thieu _internal\SoilFirm_Gioi_thieu_30s.mp4. Khong tao Setup tu ban build nay."
#endif

[Setup]
; AppId cố định duy nhất cho ứng dụng
AppId={{E68A9F32-841D-4B72-9E11-37E4C0657FEA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
PrivilegesRequired=admin
DefaultDirName={autopf}\{#MyAppName}
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}

; Đóng ứng dụng cũ nếu đang chạy trước khi cài đặt/cập nhật
CloseApplications=yes
RestartApplications=no

; Tương thích nền tảng 64-bit hiện đại
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; === CẤU HÌNH ICON BỘ CÀI & HỆ THỐNG ===
; 1. Icon cho file bộ cài Setup
SetupIconFile={#MyIconSource}
; 2. Icon hiển thị trong Control Panel (Add/Remove Programs) - trỏ thẳng vào logo đã copy
UninstallDisplayIcon={app}\{#MyIconName}

OutputBaseFilename=SoilFirm_Professional_Setup_v{#MyAppVersion}
OutputDir=Output_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 1. Toàn bộ các file và thư mục con sinh ra từ PyInstaller
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 2. COPY TRỰC TIẾP FILE LOGO VÀO THƯ MỤC CÀI ĐẶT {app}
; Giúp mã nguồn Python luôn đọc được icon mới khi cửa sổ khởi chạy
Source: "{#MyIconSource}"; DestDir: "{app}"; DestName: "{#MyIconName}"; Flags: ignoreversion
; Nếu bạn có dùng cả file logo.png cho giao diện, dòng dưới sẽ tự copy nếu file tồn tại:
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Shortcut Start Menu: Ép Windows lấy trực tiếp từ file logo.ico để tránh cache cũ
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyIconName}"; IconIndex: 0; WorkingDir: "{app}"; AppUserModelID: "SoilFirm.Professional"

Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#MyIconName}"; WorkingDir: "{app}"

; Shortcut Desktop (nếu người dùng tích chọn)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyIconName}"; IconIndex: 0; WorkingDir: "{app}"; AppUserModelID: "SoilFirm.Professional"; Tasks: desktopicon

[Run]
; Tùy chọn chạy ngay phần mềm sau khi cài đặt xong
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
procedure SHChangeNotify(wEventId: Integer; uFlags: Cardinal; dwItem1, dwItem2: Integer);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SHChangeNotify($08000000, 0, 0, 0);
end;
