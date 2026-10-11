# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root=Path(SPECPATH)
datas=[(str(root/'assets'),'assets')]
binaries=[]
hiddenimports=[]
for package in ['faster_whisper','ctranslate2','onnxruntime','tokenizers','av','huggingface_hub']:
    d,b,h=collect_all(package)
    datas+=d;binaries+=b;hiddenimports+=h
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    excludes=['torch','tensorflow','matplotlib','pandas','IPython','PyQt5','PyQt6','pytest'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='MontageStudio',debug=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='MontageStudio')
