# 测试分级

小改动按风险运行必要检查，不把每次源码修改都当作发布门禁。规则或缓存纯逻辑修改运行对应的 pytest 文件；素材页、一键流程或历史缓存按钮修改，运行对应的 Qt 验证和相关单元测试；媒体引擎、数据库迁移、云端访问、PyInstaller 或发布文件修改，才运行隔离的媒体/便携验证与 ZIP 门禁。

例如一键流程和缓存改动的快速检查：

```powershell
$env:MONTAGE_DATA_DIR = "$pwd/test_results/fast_data"
python -m pytest tests/test_safety.py tests/test_rules.py tests/test_workflow.py -q
```

快速检查不能证明最终 EXE、真实长视频、云端接口或第二台电脑可用。准备发布版本时仍须使用独立数据目录运行相应的源码验证、冻结 EXE 验证和交付包审计；项目根目录 `data` 不用于测试。
