# PyInstaller recipe for the Windows build.   Build with:   pyinstaller WhackAMole.spec
# Output: dist/WhackAMole/WhackAMole.exe  (+ the files it needs, in the same folder)
#
# The team's game file is loaded at run time (play_with_sensors.py imports it by
# path), so PyInstaller can't see its imports by itself - they are listed in
# hiddenimports, and the .py file is shipped as data next to the program.

block_cipher = None

a = Analysis(
    ["whack_a_mole_app.py"],
    pathex=["."],
    binaries=[],
    datas=[("whack_a_moleV2.py", ".")],
    hiddenimports=[
        "pygame", "pythonosc", "pythonosc.dispatcher", "pythonosc.osc_server",
        "pythonosc.udp_client", "ctypes", "ctypes.util", "platform", "array",
        "math", "random", "json",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhackAMole",
    console=False,          # no black console window; output goes to whack_log.txt
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="WhackAMole")
