"""
Script tự động:
1. Vẽ và tạo file icon 'logo.ico' chuẩn nhận diện thương hiệu SoilFirm.
2. Gọi PyInstaller đóng gói phần mềm thành SoilFirm_Professional.exe kèm icon.
"""
import os
import sys
import subprocess

APP_VERSION = "2026.11"


def verify_source_version(project_dir):
    """Chặn đóng gói nhầm app/splash của bản cũ."""
    if not os.path.isfile(os.path.join(project_dir, 'ui_i18n.py')):
        raise RuntimeError('Thiếu ui_i18n.py. Hãy chép đầy đủ gói mã nguồn mới trước khi build.')
    for module in ('cdm.py', 'alicc.py', 'choice.py', 'chat_dialog.py', 'soilfirm_ai_engine.py', 'geology_statistics.py', 'batch_calculation.py', 'report_pdf.py', 'ai_analysis_data.py', 'ai_analysis_workflow.py', 'batch_hub.py', 'lab_statistics.py', 'geotech_ai_extractor.py', 'geotech_memory.py', 'geotech_memory_ui.py', 'geotech_memory_sync.py'):
        if not os.path.isfile(os.path.join(project_dir, module)):
            raise RuntimeError(f'Thiếu {module}. Hãy chép đầy đủ các tệp của mục CDM và lựa chọn phương án trước khi build.')
    for filename, marker in (
        ('app.py', f'CURRENT_VERSION = "{APP_VERSION}"'),
        ('splash.py', f'text="v{APP_VERSION}"'),
    ):
        path = os.path.join(project_dir, filename)
        if not os.path.isfile(path) or marker not in open(path, encoding='utf-8').read():
            raise RuntimeError(
                f'{filename} chưa phải bản {APP_VERSION}. '
                'Hãy chép app.py và splash.py từ gói mã nguồn mới vào thư mục dự án trước khi build.'
            )

def verify_distribution(exe_file):
    """Verify x64 PE, embedded PKG and required onedir payload before setup."""
    import struct
    import zipfile
    from pathlib import Path
    from PyInstaller.archive.readers import CArchiveReader
    exe = Path(exe_file)
    if not exe.is_file():
        raise RuntimeError(f'Thiếu EXE đã build: {exe}')
    try:
        with exe.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('không phải Windows EXE')
            stream.seek(0x3c)
            pe_offset = struct.unpack('<I', stream.read(4))[0]
            stream.seek(pe_offset)
            if stream.read(4) != b'PE\0\0':
                raise ValueError('PE header không hợp lệ')
            if struct.unpack('<H', stream.read(2))[0] != 0x8664:
                raise ValueError('EXE không phải Windows x64, không khớp bộ cài')
        archive = CArchiveReader(str(exe))
        if 'main' not in archive.toc:
            raise ValueError('PKG thiếu chương trình main')
        # Decompress each member, detecting damaged/truncated PKG entries.
        for name in archive.toc:
            archive.extract(name)
        pyz_names = [name for name in archive.toc if name.lower().endswith('.pyz')]
        if not pyz_names:
            raise ValueError('PKG thiếu PYZ chứa mã ứng dụng')
        bundled = archive.open_embedded_archive(pyz_names[0])
        for module in ('app', 'chat_dialog', 'soilfirm_ai_engine', 'geology_statistics', 'cdm', 'alicc', 'batch_calculation', 'batch_hub', 'lab_statistics', 'mapping_proposer', 'mapping_gate', 'geotech_ai_extractor', 'geotech_memory', 'geotech_memory_ui', 'geotech_memory_sync'):
            if module not in bundled.toc:
                raise ValueError(f'PYZ thiếu mô đun {module}')
            bundled.extract(module)
    except Exception as exc:
        raise RuntimeError(f'EXE/PKG chưa hợp lệ: {exe}. {exc}. Không tạo bộ cài từ tệp này.') from exc
    runtime = exe.parent / '_internal'
    required = ('base_library.zip', 'Data_Import_Mau.xlsx', 'SoilFirm_Gioi_thieu_30s.mp4', 'logo.ico', 'logo.png', 'parameter_registry.json', 'mapping_schema.json', 'geotech_template_catalog.json', 'shared_memory_seed.json')
    for name in required:
        path = runtime / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Bản build thiếu tệp runtime: {path}')
    if not any(path.stat().st_size > 0 for path in runtime.glob('python3*.dll')):
        raise RuntimeError('Bản build thiếu Python DLL trong _internal.')
    with zipfile.ZipFile(runtime / 'base_library.zip') as library:
        bad = library.testzip()
        if bad:
            raise RuntimeError(f'base_library.zip bị hỏng: {bad}')
    print('--> Đã kiểm tra EXE x64, PKG/PYZ và các tệp runtime cần thiết.')
    return str(exe)


# 1. TỰ ĐỘNG TẠO FILE LOGO.ICO BẰNG PILLOW
def generate_soilfirm_ico(force=False):
    existing_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')
    if os.path.isfile(existing_icon) and not force:
        return existing_icon
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Đang cài đặt thư viện Pillow...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
        from PIL import Image, ImageDraw, ImageFont

    png_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.png')
    if os.path.isfile(png_file):
        with Image.open(png_file) as source:
            source.convert('RGBA').save(existing_icon, format='ICO',
                sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
        return existing_icon

    print("--> Đang khởi tạo logo biểu tượng kỹ thuật SOILFIRM PRO...")
    size = (256, 256)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Nền bo góc xanh Navy nhận diện SoilFirm (#1E293B)
    draw.rounded_rectangle([8, 8, 248, 248], radius=48, fill="#1E293B", outline="#0C6175", width=6)

    # Thân nền đường đắp hình thang (#17384D viền xanh cyan #0284C7)
    trap_pts = [(45, 175), (85, 95), (171, 95), (211, 175)]
    draw.polygon(trap_pts, fill="#17384D", outline="#0284C7", width=4)

    # Mũi kim bấc thấm / cọc cát thẳng đứng màu cam (#E5A642)
    for x in [75, 105, 128, 151, 181]:
        draw.line([(x, 175), (x, 222)], fill="#E5A642", width=4)
        draw.polygon([(x - 4, 222), (x + 4, 222), (x, 230)], fill="#E5A642")

    # Khối chữ lồng "SF" màu trắng ở giữa
    def brand_font(size):
        for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "timesbd.ttf"):
            try:return ImageFont.truetype(name,size)
            except OSError:pass
        try:return ImageFont.load_default(size=size)
        except TypeError:return ImageFont.load_default()
    font = brand_font(64)

    draw.text((128, 134), "SF", fill="#FFFFFF", font=font, anchor="mm")
    draw.text((128, 56), "AI", fill="#0284C7", font=brand_font(36), anchor="mm")

    # Xuất ra đầy đủ các độ phân giải icon của Windows
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    img.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png"))
    print(f"--> Đã tạo thành công file: {ico_path}")
    return ico_path


# 2. GỌI PYINSTALLER BUILD EXE
def build_executable():
    import struct
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise RuntimeError('Bộ cài Windows x64 phải được build bằng Python 64-bit trên Windows.')
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_file = os.path.join(project_dir, 'main.py')
    if not os.path.isfile(main_file):
        raise FileNotFoundError(f'Không tìm thấy {main_file}. Hãy đặt build_app.py cùng thư mục với main.py.')
    verify_source_version(project_dir)
    for dependency,requirement in (('pandas','pandas>=2,<4'),('pydantic','pydantic>=2.7,<3'),('g4f','g4f==8.6.5'),('ddgs','ddgs>=9,<10')):
        try:
            module=__import__(dependency)
            if dependency=='pydantic' and int(module.__version__.split('.')[0])<2:raise ImportError('Cần Pydantic 2')
        except ImportError:
            subprocess.check_call([sys.executable,'-m','pip','install',requirement])
    try:
        import webview
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pywebview>=5,<7'])
    try:
        import pypdf
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pypdf>=5'])
    try:
        import xlrd
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'xlrd>=2.0.1'])
    template_file = os.path.join(project_dir, 'Data_Import_Mau.xlsx')
    if not os.path.isfile(template_file):
        raise FileNotFoundError('Thiếu Data_Import_Mau.xlsx để đóng gói file mẫu import.')
    for name in ('parameter_registry.json','mapping_schema.json','geotech_template_catalog.json','shared_memory_seed.json'):
        if not os.path.isfile(os.path.join(project_dir,name)):
            raise FileNotFoundError(f'Thiếu {name} để đóng gói cổng kiểm tra AI.')
    intro_video = os.path.join(project_dir, 'SoilFirm_Gioi_thieu_30s.mp4')
    if not os.path.isfile(intro_video):
        raise FileNotFoundError('Thiếu SoilFirm_Gioi_thieu_30s.mp4 để đóng gói video giới thiệu.')
    ico_file = generate_soilfirm_ico(force=True)
    
    # Kiểm tra cài đặt PyInstaller
    try:
        import PyInstaller
        if int(PyInstaller.__version__.split('.')[0]) < 6:
            raise ImportError('Cần PyInstaller 6 trở lên cho cấu trúc _internal.')
    except ImportError:
        print("Đang cài đặt PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller>=6,<7"])

    print("\n--> Đang bắt đầu quá trình đóng gói SoilFirm_Professional.exe...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--hidden-import=geotech_memory",
        "--hidden-import=geotech_memory_ui",
        "--hidden-import=geotech_memory_sync",
        "--hidden-import=sqlite3",
        "--collect-all=pandas",
        "--collect-all=pydantic",
        "--collect-all=pydantic_core",
        "--collect-all=g4f",
        "--collect-all=ddgs",
        "--collect-all=soilfirm_agent",
        "--collect-all=jsonschema",
        "--collect-all=pdfplumber",
        f"--add-data={os.path.join(project_dir, 'soilfirm_agent')}{os.pathsep}soilfirm_agent",
        "--collect-all=webview",
        f"--add-data={intro_video}{os.pathsep}.",
        "--collect-all=pypdf",
        "--collect-all=fitz",
        "--collect-all=xlrd",
        "--collect-all=ezdxf",
        f"--add-data={template_file}{os.pathsep}.",
        f"--add-data={os.path.join(project_dir, 'parameter_registry.json')}{os.pathsep}.",
        f"--add-data={os.path.join(project_dir, 'mapping_schema.json')}{os.pathsep}.",
        f"--add-data={os.path.join(project_dir, 'geotech_template_catalog.json')}{os.pathsep}.",
        f"--add-data={os.path.join(project_dir, 'shared_memory_seed.json')}{os.pathsep}.",
        "--collect-all=pythonnet",
        "--collect-all=clr_loader",
        "--onedir",
        "--contents-directory=_internal",
        "--noconfirm",
        f"--distpath={os.path.join(project_dir, 'dist')}",
        f"--workpath={os.path.join(project_dir, 'build')}",
        f"--specpath={project_dir}",
        f"--add-data={ico_file}{os.pathsep}.",
        f"--add-data={os.path.join(project_dir, 'logo.png')}{os.pathsep}.",
        "--clean",
        f"--icon={ico_file}",
        "--name=SoilFirm_Professional",
        "main.py"
    ]
    
    result = subprocess.run(cmd, cwd=project_dir)
    exe_file = os.path.join(project_dir, 'dist', 'SoilFirm_Professional', 'SoilFirm_Professional.exe')
    if result.returncode == 0 and os.path.isfile(exe_file):
        verify_distribution(exe_file)
        import shutil
        shutil.copy2(ico_file, os.path.dirname(exe_file))
        optional_logo = os.path.join(project_dir, 'logo.png')
        if os.path.isfile(optional_logo):
            shutil.copy2(optional_logo, os.path.dirname(exe_file))
        print("\n" + "="*60)
        print(" CHÚC MỪNG: ĐÓNG GÓI EXE HOÀN TẤT THÀNH CÔNG!")
        print(f" File chạy của bạn: {exe_file}")
        print(" Bây giờ mở SoilFirm_Professional.iss để tạo bộ cài.")
        print("="*60)
        return exe_file
    else:
        raise RuntimeError('Build EXE thất bại hoặc không tìm thấy tệp dist/SoilFirm_Professional/SoilFirm_Professional.exe.')

if __name__ == "__main__":
    build_executable()
