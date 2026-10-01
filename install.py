#!/usr/bin/env python3
"""Install the companion for the current user without touching OneDrive."""
import argparse
import os
from pathlib import Path
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--no-autostart', action='store_true')
args = parser.parse_args()
source = Path(__file__).resolve().parent
data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
target = data / 'onedrive-status'
target.mkdir(parents=True, exist_ok=True)
for name in ['status.py', 'run.sh', 'README.md', 'LICENSE']:
    shutil.copy2(source / name, target / name)
(target / 'run.sh').chmod(0o755)
# Desktop Exec quoting also needs escaping at the desktop-entry value layer.
path = str(target / 'run.sh')
quoted = '"' + ''.join('\\' + c if c in '\\"`$' else c for c in path) + '"'
quoted = quoted.replace('\\', '\\\\').replace('%', '%%')
desktop = (source / 'onedrive-status.desktop').read_text().replace('Exec=onedrive-status', 'Exec=' + quoted)
for directory in [data / 'applications'] + ([] if args.no_autostart else [config / 'autostart']):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'onedrive-status.desktop').write_text(desktop)
print('Installed. Open OneDrive Status from your application menu.')
