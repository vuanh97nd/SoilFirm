"""Build and verify SOILFIRM PRO Windows x64 before compiling Inno Setup."""
from build_app import build_executable, verify_distribution, configure_build_output


def run_build():
    return build_executable()


if __name__ == '__main__':
    configure_build_output()
    import argparse
    parser = argparse.ArgumentParser(description='Build/kiểm tra SOILFIRM PRO trước khi tạo Setup.')
    parser.add_argument('--verify-exe', help='Chỉ kiểm tra EXE cùng thư mục _internal, không build lại.')
    args = parser.parse_args()
    if args.verify_exe:
        verify_distribution(args.verify_exe)
    else:
        run_build()
