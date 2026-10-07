# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('G:/My Drive/Dev/SoilFirm_Pro_2026.11/logo.png', '.'), ('G:/My Drive/Dev/SoilFirm_Pro_2026.11/SoilFirm_Gioi_thieu_30s.mp4', '.'), ('G:/My Drive/Dev/SoilFirm_Pro_2026.11/Data_Import_Mau.xlsx', '.'), ('G:/My Drive/Dev/SoilFirm_Pro_2026.11/logo.ico', '.')]
datas += [('G:/My Drive/Dev/SoilFirm_Pro_2026.11/parameter_registry.json', '.'), ('G:/My Drive/Dev/SoilFirm_Pro_2026.11/mapping_schema.json', '.')]
datas += [('G:/My Drive/Dev/SoilFirm_Pro_2026.11/geotech_template_catalog.json', '.'), ('G:/My Drive/Dev/SoilFirm_Pro_2026.11/shared_memory_seed.json', '.')]
datas += [('G:/My Drive/Dev/SoilFirm_Pro_2026.11/soilfirm_agent', 'soilfirm_agent')]
binaries = []
hiddenimports = ['xlrd', 'geotech_ai_extractor', 'geotech_memory', 'geotech_memory_ui', 'geotech_memory_sync', 'sqlite3', 'soilfirm_agent', 'soilfirm_agent.app_bridge', 'soilfirm_agent.documents', 'soilfirm_agent.table_python', 'jsonschema', 'pdfplumber']
for package in ('pandas','pydantic','pydantic_core','g4f','ddgs','soilfirm_agent','jsonschema','pdfplumber'):
    collected=collect_all(package)
    datas += collected[0]; binaries += collected[1]; hiddenimports += collected[2]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pypdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('clr_loader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SoilFirm_Professional',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['G:/My Drive/Dev/SoilFirm_Pro_2026.11/logo.ico'],
    contents_directory='_internal',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SoilFirm_Professional',
)
