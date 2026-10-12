# 技术方案与工作方式

1.0.4：共用Player使用原生QSlider键盘/无障碍接口，SeekSlider按现有浅深token绘制细轨道并支持任意位置点击。播放回报更新时阻止反向seek，拖动期间不回写滑块；松手才提交目标并恢复原播放状态。--player-test仅使用合成媒体且默认隔离数据；ZIP新增最终播放器五组及EXE哈希门禁。

1.0.3：cloud.py封装内置官方lark-cli 1.0.96独立Windows程序，无需Node安装；用户身份只读解析链接、按视图投影目录/分页、专用附件下载。CLI负责本机凭据，不读取或复制密钥到软件会话/发布包。cloud_ui.py提供原生云端库、后台同步/取消、搜索和连接检查/授权链接+二维码。新电脑允许用户填写公司应用至独立montage-studio连接，登录自身有表格及下载权限的用户。下载临时文件先大小/媒体检查，再原子入缓存；缓存含SHA256素材身份，重用时核对，云端键含Base/表/记录/附件。云端目录和视频保存在data/cloud，移出A不删缓存；手动刷新不处理未选视频。停止或单条失败保留已完成下载，重试复用。诊断--cloud-test默认隔离且仅供明确云端验证，常规便携验证离线不访问公司表。

1.0.2：theme.py集中Qt浅深色与Tabler MIT图标；gallery.py用QListWidget IconMode及委托绘制自适应网格，不创建500套复杂子控件。原生CheckState与selection同步，普通点击累加、Shift区间、空格切换；保留既有selectedItems业务接口。assets/ui保存原创PNG/多尺寸ICO与图标许可，spec设置EXE图标。新缩略图-v2缓存提高分辨率；高DPI按目标矩形绘制。main.py媒体/UI/扩展/压力/截图诊断默认MONTAGE_DATA_DIR隔离，显式环境变量优先。升级只用合成测试数据副本，ZIP核对便携、升级/图标、截图隔离报告的EXE哈希；事件及边界见HANDOFF。

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
