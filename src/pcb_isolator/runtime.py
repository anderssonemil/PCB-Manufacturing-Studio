"""Bundled read-only assets and persistent per-user settings."""
import os
from pathlib import Path
import shutil
import sys


def asset_root():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]


def settings_root():
    override=os.environ.get('PCB_ISOLATOR_HOME')
    if override:return Path(override).resolve()
    if getattr(sys,'frozen',False):
        return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'PCB Isolator'
    return asset_root()


def machining_path():
    root=settings_root();root.mkdir(parents=True,exist_ok=True)
    destination=root/'machining.toml'
    if not destination.exists():shutil.copyfile(asset_root()/'machining.toml',destination)
    return destination
