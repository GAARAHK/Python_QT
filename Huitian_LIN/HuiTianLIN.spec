# -*- mode: python ; coding: utf-8 -*-
# HuiTian LIN Upper-Computer v2.4 -- PyInstaller spec
from PyInstaller.utils.hooks import collect_all, collect_submodules

# 收集 qfluentwidgets 全部文件（含图标、QSS、_rc 资源）
_qfw_datas, _qfw_bins, _qfw_hidden = collect_all('qfluentwidgets')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_qfw_bins,
    datas=_qfw_datas,
    hiddenimports=(
        _qfw_hidden
        + collect_submodules('qfluentwidgets')
        + [
            'PyQt5.sip',
            'PyQt5.QtSvg',
            'PyQt5.QtXml',
            'PyQt5.QtNetwork',
            'PyQt5.QtPrintSupport',
            'serial',
            'serial.tools',
            'serial.tools.list_ports',
            'serial.tools.list_ports_windows',
            'sqlite3',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL', 'Pillow', 'cv2', 'tkinter', 'wx',
        'IPython', 'notebook', 'jupyter',
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HuiTianLIN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # 不显示黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',        # 如需自定义图标，取消注释并提供 .ico 文件
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HuiTianLIN',
)
