"""One-click setup and launch. Uses only Python's standard library."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def required_versions(path):
    return dict(line.strip().split('==', 1) for line in path.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#'))

def missing_packages(python, requirements):
    script = '''import importlib.metadata as m,json,sys
required=json.loads(sys.argv[1]);missing=[]
for name,version in required.items():
 try: installed=m.version(name)
 except m.PackageNotFoundError: installed=None
 if installed!=version: missing.append(name)
print(json.dumps(missing))'''
    result = subprocess.run([str(python), '-c', script, json.dumps(requirements)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Cannot check this environment. Rename .venv and start again.')
    return json.loads(result.stdout)

def main():
    parser = argparse.ArgumentParser(description='CrediBell automatic setup and startup')
    parser.add_argument('--setup', action='store_true', help='Install/check dependencies without starting')
    parser.add_argument('--check', action='store_true', help='Check installation without changing files')
    parser.add_argument('--port', type=int, default=8502)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error('Install Python 3.12 or 3.13, then reopen this launcher.')
    python = ROOT / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.exists():
        if args.check:
            print('Setup needed: virtual environment has not been created.'); return 1
        print('Creating the CrediBell Python environment...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
    requirements = required_versions(ROOT / 'requirements.txt')
    missing = missing_packages(python, requirements)
    if missing:
        if args.check:
            print('Setup needed: ' + ', '.join(missing)); return 1
        print('Installing dependencies. Needed on first setup or after an update.', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(ROOT / 'requirements.txt')], cwd=ROOT, check=True)
        if missing_packages(python, requirements):
            raise RuntimeError('Dependencies did not finish installing. Check the installer output above.')
    print('CrediBell is ready. Dependencies are already installed.', flush=True)
    if args.setup or args.check: return 0
    command = [str(python), str(ROOT / 'run.py'), '--port', str(args.port)]
    if not args.no_browser: command.append('--open')
    return subprocess.call(command, cwd=ROOT)

if __name__ == '__main__':
    try: sys.exit(main())
    except KeyboardInterrupt: sys.exit(0)
    except (subprocess.CalledProcessError, RuntimeError, OSError) as error:
        print(f'Could not start CrediBell: {error}', file=sys.stderr); sys.exit(1)
