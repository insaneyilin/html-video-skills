# 第三方组件

本仓库只分发自有流程说明、脚本和虚构示例，不分发模型权重、浏览器、字体或 html-video 源码。依赖与模型保留各自许可。

| 组件 | 角色 | 来源 |
| --- | --- | --- |
| html-video | 实际调用的分镜编排、渲染、拼接与音轨合入框架；Apache-2.0 | [源码仓库](https://github.com/nexu-io/html-video) |
| Hyperframes | html-video 上游参考的 HTML 视频方案与渲染范式；Apache-2.0 | [源码仓库](https://github.com/heygen-com/hyperframes) |
| MLX Audio | Apple Silicon 语音生成与识别运行库；MIT | [源码仓库](https://github.com/Neywa-Labs/mlx-audio) |
| Qwen3-TTS / Qwen3-ASR（含 ForcedAligner） | 原始语音合成、转写与对齐模型；下载时保留对应模型卡及许可 | [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)、[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) |
| MLX Community 模型转换 | 本流程采用的 MLX 量化权重，具体版本与许可见各模型卡 | [模型集合](https://huggingface.co/mlx-community) |
| MLX | Apple Silicon 推理 | [源码仓库](https://github.com/ml-explore/mlx) |
| Playwright / Chromium | 界面采集、HTML 检查和录像 | [Playwright](https://playwright.dev/) |
| ffmpeg | 音频处理、编码和最终媒体检查 | [官网](https://ffmpeg.org/) |

当前实际调用的是 html-video 的 `adapter-hyperframes`。已验证版本通过 Playwright / Chromium 录制自包含 HTML，再用 ffmpeg 编码；Hyperframes 在此列为上游方案与渲染范式参考。具体运行依赖以该适配器的实现和版本为准。

所用模型 ID 和 revision 在示例配置中明确列出。若重新分发打包的模型或应用，模型卡和依赖的实际许可证需要随相应组件保留；本仓库的 MIT 许可不替换它们。
