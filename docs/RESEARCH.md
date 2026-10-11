# 调研记录与采用边界

整理：2026-10-11。方法项目资料来自此前对话的2026-10-09调研记录，并非本次重新查询；星数是当时近似快照，可能变化。没有安装以下框架。高星只能作为关注度线索，不能证明方法适用于本项目。

## AI编程方法

| 项目 | 此前星数约值 | 值得借鉴 | 需避免照搬 |
|---|---:|---|---|
| [Superpowers](https://github.com/obra/superpowers) | 29.7万 | 先讨论设计，再拆任务、验证结果。 | 所有工作强制TDD、极细任务与大量代理可能增加成本；按风险使用。 |
| [GitHub Spec Kit](https://github.com/github/spec-kit) | 14.1万 | 需求、计划、任务、实现之间保持可追踪关系。 | 文档不能消除需求与代码偏差，必须检查实际行为。 |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) | 7.1万 | 每次变更明确目的、方案和验收；文件可跨工具交接。 | README的模型建议、竞品比较不能作为当前最优方案的证据。 |
| [GSD 原项目](https://github.com/gsd-build/get-shit-done) / [GSD Core](https://github.com/open-gsd/gsd-core) | 原约6.4万；Core约1万 | 工作状态落盘、阶段执行、交接后继续。 | 原项目已说明迁移；通用上下文退化说法和长上下文效果承诺不能直接视为普遍事实。 |
| [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) | 5.4万 | 分别从产品、架构、使用体验和验证角度审视项目。 | 本项目不需要先建立庞大虚拟团队和流程。 |
| [Aider](https://github.com/Aider-AI/aider) | 4.9万 | 理解仓库、限定修改、版本恢复与验证。 | 此前README部分模型推荐较旧，不沿用其模型排行。 |

建议综合采用轻量做法：明确需求→有限任务→实际验证→持久交接。暂不安装多个重叠框架，也不把工具名当作流程本身。

上述判断主要针对此前阅读的README与相关说明，未对框架进行完整安装评测。动用其命令或依赖前重新核对版本、维护状态和许可。

## 媒体处理资料

- [FFmpeg滤镜文档](https://ffmpeg.org/ffmpeg-filters.html)：concat、xfade、acrossfade、loudnorm、subtitles等是候选能力。xfade要求输入在分辨率、像素格式、帧率和时间基等方面兼容，并要求恒定帧率；“都是720p”不充分。
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)：候选语音识别实现。2026-10-11已再次读取README，存在CPU/GPU与量化方案；GPU有CUDA/cuDNN等依赖，需实测和打包验证。其发布的性能数字不是本机测试。
- [Demucs](https://github.com/facebookresearch/demucs)：此前README表明原项目不再维护，关联分支维护有限；歌曲音轨分离能力不能证明能完整保留游戏音效。
- [SAM Audio](https://github.com/facebookresearch/sam-audio)：候选声音分离研究方向。此前资料包含GPU建议、模型获取和许可限制；未验证本机兼容、许可适配、速度与实际效果，不作已选方案。
- [NVIDIA编码支持表](https://developer.nvidia.com/video-encode-decode-support-matrix)：2026-10-11查询包含GTX1660SUPER行；确认候选硬件具备编码能力，未验证项目运行链路。
- [Codex项目指令文档](https://developers.openai.com/codex/guides/agents-md/)：此前已查阅AGENTS.md发现机制。其他模型/工具的自动读取行为必须分别核实。

## 证据层级

产品要求由用户确认；开源说明是候选依据；真实素材实验才证明质量；另一台电脑的实际操作才证明对应环境交付。四者不能互相替代。

