# 混剪工坊

Windows 本机批量前贴与游戏广告组合工具。已授权开发，当前状态、验证证据和接手入口见 [HANDOFF.md](HANDOFF.md) 与 [docs/PROGRESS.md](docs/PROGRESS.md)。用户使用请读 [使用说明](docs/使用说明.md)。

开发入口 `python main.py`；环境为 Python 3.14，安装 `requirements.txt`。assets 下的 FFmpeg、字体及离线模型必须按 docs/THIRD_PARTY.md 准备，并以 docs/ASSETS_MANIFEST.json 校验。二进制资源不入 Git，发布便携包内完整附带。

```powershell
python -m pytest -q
python main.py --self-test test_results/new_selftest
python -m PyInstaller --noconfirm MontageStudio.spec
python scripts/package_release.py prepare
python scripts/verify_portable.py release/混剪工坊_1.0.1/MontageStudio/MontageStudio.exe test_results/portable_v101
python scripts/package_release.py zip
```

扩展验证需先在目标目录的“演示素材”中复制发布示例；压力测试使用新的空目录。测试产物不写入Git。发布包附有独立证据摘要和完整文件夹，不能只复制EXE。

GPL-3.0。第三方许可及来源见LICENSE、docs/THIRD_PARTY.md及发布包内许可原文。
