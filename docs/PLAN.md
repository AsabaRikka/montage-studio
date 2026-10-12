# 技术方案与工作方式

1.0.1 增量：thumbnails.py 使用单个后台队列低优先级调用内置 FFmpeg 取帧，按素材内容身份缓存 JPG；widgets.py 统一防止下拉/数字控件滚轮改值并把滚轮传递给外层滚动页面。uitest.py 提供真实 Qt 交互回归，冻结 EXE 同样运行；发布脚本按版本独立目录发布，拒绝覆盖含用户 data 的目录。

更新：2026-10-11。开发已授权并实现，证据见PROGRESS。

| 部分 | 采用方案 | 原因与边界 |
|---|---|---|
| 桌面 | Python3.14/PySide6/PyInstaller | 原生中文界面、播放与字幕编辑；完整文件夹分发 |
| 媒体 | 内置FFmpeg/ffprobe | 规范缓存、拼接/转场、烧录；硬切复用片段，转场重新编码 |
| 字幕 | faster-whisper-small CPU int8 | 离线、不依赖CUDA；需校正 |
| 去音乐 | UVR-MDX-NET-Inst_HQ_3 ONNX CPU | 估计伴奏后残差，不保证游戏音效保留 |
| 数据 | SQLite WAL/SHA256 | 固定任务、事务历史、备份恢复、内容身份 |
| 规则 | 下界流/本地有限语言解析 | 唯一配对、严格均匀/指定次数；无解拒绝 |
| 可选AI | 用户自配兼容接口 | 只发规则文字、结构验证，用户自行决定费用 |

gui.py界面/工作线程；planner.py规则；store.py数据；service.py导入/冻结/调度；media.py缓存/成片；subtitles.py识别/对齐；separation.py分离；runtime.py便携路径。core/editing复用本地媒体基础设施。

assets二进制不入Git，发布包包含工具、字体、模型、许可；不能只复制exe。源码和来源清单供恢复构建。

规划基线、核心、验证、交付分别Git提交/标签。换模型先读AGENTS/HANDOFF/PROGRESS/PRODUCT/PLAN再核对Git和实际证据。分开记录自动验证、观看试听和跨机验证。

本机i5-12400F/16GB/GTX1660SUPER6GB。后台线程/优先级不承诺完全不影响使用。1000×90秒×4Mbps约45GB输出，不含源和缓存，实际取决于码率和时长。
