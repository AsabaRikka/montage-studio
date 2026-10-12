# 第三方组件与资源来源

1.0.2界面导航图标来自Tabler Icons v3.35.0（MIT），保存于assets/ui/tabler，许可原文LICENSE.txt随包；派生的勾选/上下箭头仅改色。来源https://github.com/tabler/tabler-icons/tree/v3.35.0 。软件Logo与MontageStudio.ico是本项目原创拼接/播放标记，可由scripts/make_brand.py重建，没有使用Codex/OpenAI品牌标志。界面仅参考中性桌面风格，不声称使用Codex官方设计系统。

混剪工坊源码按GPL-3.0发布（LICENSE），包含完整源码交付。FFmpeg 8.1.1 gyan.dev静态构建为GPL3，源版本239f2c733d，构建说明及许可随包。Qt/PySide6为动态库，LGPL3/GPL3许可原文随包，不嵌入静态Qt。软件没有限制替换兼容组件。

faster-whisper MIT；CTranslate2 MIT；Whisper-small权重来自Systran/faster-whisper-small，Whisper MIT；ONNX Runtime MIT；NotoSansSC字体OFL。当前Python依赖版本和安装包原文许可分别在assets/dependency_versions.json和assets/licenses/current。

音乐分离权重UVR-MDX-NET-Inst_HQ_3.onnx来自TRvlvr/model_repo的all_public_uvr_models发布资源。UVR开发者README明确要求模型使用者遵守MIT并署名；已保留README快照和MIT许可（历史提交ca61edf1c0766267d5498f9a5bc704f19e394478）。感谢Anjok07、Aufr33、UVR贡献者和MDX-Net原作者Kuielab/Woosung Choi。当前上游master已移除LICENSE文件，许可原文从上述历史提交读取，模型自身没有内嵌许可，来源和该边界明确保留。

模型设置以官方mdx模型资料快照核对：尾部10MiB MD5为55657dd70583b0fedfba5f67df11d711，primary_stem Instrumental，compensate1.022，dim_f3072，dim_t2^8，nfft6144。UVR-model-config-snapshot.json随包保留。

来源：
https://www.gyan.dev/ffmpeg/builds/
https://github.com/FFmpeg/FFmpeg/commit/239f2c733d
https://huggingface.co/Systran/faster-whisper-small
https://github.com/openai/whisper
https://github.com/Anjok07/ultimatevocalremovergui
https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models
https://raw.githubusercontent.com/Anjok07/ultimatevocalremovergui/ca61edf1c0766267d5498f9a5bc704f19e394478/LICENSE
https://github.com/notofonts/noto-cjk

合成演示素材采用Windows语音合成、合成和弦和彩色测试画面，不包含公司素材；仅用于软件功能示例，不作为广告成片。
