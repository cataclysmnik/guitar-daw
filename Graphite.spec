# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],  # Your main entry point
    pathex=[],
    binaries=[],
    datas=[
        ('public/', 'public/'),               # Includes all your SVG icons
        ('widgets/', 'widgets/'),             # Includes your custom PySide6 UI files
        ('audio_settings.json', '.'),         # Includes your JSON config in the root
        ('logo.ico', '.'),                     # Includes your main logo in the root
        ('logo.png', '.'),                     # Include PNG logo
        ('splashscreen.png', '.'),             # Include PNG splash screen
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'PySide6.QtSvg',                      # CRITICAL: Since you are using SVGs for icons
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['test_daw.py'],                 # Exclude your test file from the final build
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Graphite',                          # This will be your final executable name
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                            # False hides the command prompt window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements=None,
    icon='logo.ico',                          # (Optional) Windows prefers .ico, but PyInstaller can sometimes convert SVGs if dependencies are met
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Graphite',
)