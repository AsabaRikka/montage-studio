# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root=Path(SPECPATH)
datas=[(str(root/'assets'),'assets')]
binaries=[]
hiddenimports=['scipy._external.array_api_compat.numpy.fft',
               'scipy._external.array_api_compat.numpy.linalg']
for package in ['faster_whisper','ctranslate2','onnxruntime','tokenizers','av','huggingface_hub']:
    d,b,h=collect_all(package)
    datas+=d;binaries+=b;hiddenimports+=h
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    excludes=['torch','tensorflow','matplotlib','pandas','IPython','PyQt5','PyQt6','pytest'],noarchive=False,optimize=0)
# Qt on Windows uses the OS ICU ABI (unversioned symbols). An unrelated
# Poppler directory on the build PATH has ICU 78 with suffixed exports;
# collecting that same-named DLL prevents Qt from starting. Use Windows ICU.
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower()
            not in {'icuuc.dll','icudt78.dll'}]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='MontageStudio',icon=str(root/'assets/ui/MontageStudio.ico'),debug=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='MontageStudio')
