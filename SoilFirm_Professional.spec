# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

from pathlib import Path
project_dir = Path(SPECPATH)
core_assets = ('logo.png', 'logo.ico', 'parameter_registry.json',
               'mapping_schema.json', 'geotech_template_catalog.json')
datas = [(str(project_dir / name), '.') for name in core_assets]
for name in ('Data_Import_Mau.xlsx', 'shared_memory_seed.json'):
    if (project_dir / name).is_file():
        datas.append((str(project_dir / name), '.'))
datas.append((str(project_dir / 'soilfirm_agent'), 'soilfirm_agent'))
binaries = []
hiddenimports = ['xlrd', 'geotech_ai_extractor', 'geotech_memory', 'geotech_memory_ui', 'geotech_memory_sync', 'sqlite3', 'soilfirm_agent', 'soilfirm_agent.app_bridge', 'soilfirm_agent.documents', 'soilfirm_agent.table_python', 'jsonschema', 'pdfplumber']
for package in ('pydantic','pydantic_core','g4f','ddgs','soilfirm_agent','pdfplumber'):
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
    [str(project_dir / 'main.py')],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas.tests', 'jsonschema.tests', 'jsonschema.benchmarks', 'g4f.local'],
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
    icon=[str(project_dir / 'logo.ico')],
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
