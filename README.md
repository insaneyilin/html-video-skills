# html-video-skills

一套可复用、与 AI Agent 无关的演示视频制作流程：**理解产品 → 真实素材 → HTML 分镜 → Qwen3-TTS 旁白 → 字幕对齐 → MP4 → 最终播放检查**。

入口：[skills/html-video-demo/SKILL.md](skills/html-video-demo/SKILL.md)。可以让常用 Agent 直接读取，也可以把整个 `html-video-demo` 文件夹放入它支持的技能目录。本仓库不会自动修改任何 Agent 的全局配置。

## 演示效果

使用本流程生成的两幕笔记应用示例，约 **18 秒**，包含中文旁白、字幕和应用界面。所有内容均为虚构演示数据。

[![笔记应用演示视频预览](docs/demo/notes-demo.gif)](docs/demo/notes-demo.mp4)

动图为无声预览，点击可打开[带中文旁白的 MP4 原片](docs/demo/notes-demo.mp4)（1080p / 30fps）。

## 基于哪些项目

这套流程建立在以下开源项目之上，感谢它们提供的基础能力：

| 项目 | 在本流程中的角色 |
| --- | --- |
| [html-video](https://github.com/nexu-io/html-video) | 实际调用的视频编排与渲染框架，提供分镜组织、逐幕渲染、视频拼接和音轨合入。 |
| [Hyperframes](https://github.com/heygen-com/hyperframes) | html-video 上游参考的 HTML 视频方案与渲染范式。当前流程通过 html-video 的 `adapter-hyperframes` 接口接入。 |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) / [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) | 提供旁白合成、语音转写与强制对齐模型；本流程使用其 MLX 量化版本。 |
| [MLX Audio](https://github.com/Neywa-Labs/mlx-audio) | 在 Apple Silicon 上运行语音模型，完成本地配音、转写和时间对齐。 |

已验证的渲染调用链是 **本包 → html-video 的 `adapter-hyperframes` → Playwright / Chromium 录制 HTML → ffmpeg 编码**。

本仓库在这些基础能力之上，整理了面向 AI Agent 的演示制作工作流、可配置脚本与通用示例，并补充配音一致性处理、条件启用的尾字修复、字幕与转场对齐，以及最终成片验证。详细依赖、来源和许可说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 包含什么

- 一份技能说明，覆盖新视频制作与已有视频的迭代。
- 配置驱动的音色试听、语音分组、合成缓存、转写核对和字幕对齐脚本。
- 一个条件启用的 Qwen3 解码长度修正，避免合法 codec ID `0` 被误算为 padding 而裁掉尾音。
- 自包含 HTML 场景模板、html-video 渲染适配器、版本化导出和本地预览。
- 对原始音频样本、自然停顿、字幕、画面边界、最终 MP4 切点和浏览器播放的检查。
- 完全虚构的两幕笔记应用示例；没有真实项目名称、截图、配音、内部地址或个人路径。

## 怎样使用

给 Agent 的示例请求：

> 阅读 html-video-demo 的 SKILL.md，为这个产品制作一支中文演示视频。先理解实际功能，用演示数据采集界面；沿用我确认的音色和视觉风格，保留分镜、字幕和可复现脚本。检查最终 MP4，尤其是段尾收声和切幕。

也可以直接执行脚本。先按 [环境与命令](skills/html-video-demo/references/setup.md) 准备环境，再从通用示例开始：

```sh
export SKILL_DIR="$PWD/skills/html-video-demo"
export DEMO_PROJECT="$PWD/projects/my-demo"
export HTML_VIDEO_ROOT=/path/to/html-video

uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r "$SKILL_DIR/scripts/requirements-mlx-tested.txt"
.venv/bin/python "$SKILL_DIR/scripts/audio.py" init --project "$DEMO_PROJECT"
```

编辑生成的 `project.json`，再使用技能中的制作命令。命令中的 `python` 应指向上述隔离环境。音色、文字、配色、场景和分组都在配置里；没有固定幕数，也不要求特定 Agent 提供专用工具。

## 目录

```text
skills/html-video-demo/
  SKILL.md
  references/           环境、项目格式、画面、音频与排错
  scripts/              Python 音频管线与 Node 视频工具
  assets/starter/       可运行的虚构应用与示例配置
tests/                  分组、路径、解码长度和切幕回归检查
docs/demo/              README 演示视频与动图
```

项目运行后会产生 `work/`、`.html-video/` 和 `exports/`。工作缓存与模型缓存不是发布素材；每次成片位于独立的导出目录，检查通过后才更新 `review.html` 和 `exports/latest.json`。README 中的脱敏演示素材随仓库保存；其他生成的视频、音频、虚拟环境和实际业务素材不进入本仓库。

## 适用范围

内置配音后端使用 Apple Silicon、MLX 和 Qwen3-TTS CustomVoice；渲染使用 Node.js、Chromium、ffmpeg 与 html-video。其他系统可以复用分镜、HTML、时间协议与检查方法，但需要提供适合该系统的语音实现，不能把 MLX 命令直接当成跨平台方案。

声音自然度仍需要试听。机器转写用于发现内容问题，强制对齐用于定位时间；两者均不能代替对语气、术语读法和呼吸停顿的判断。

## 验证

在隔离的依赖环境中运行：

```sh
python -m unittest discover -s tests -v
node --test tests/runtime.test.mjs
```

本包已完成 9 项 Python 回归检查、1 项 Node 预览服务检查，以及全新示例的实际流程试跑：Qwen3-TTS 合成、独立转写、时间对齐、界面截图、HTML 抽帧、html-video 导出和最终 MP4 播放检查。两幕示例的计划时长为 18.4 秒，场景抽帧无文字溢出，导出音轨的切幕检查通过。验证覆盖当前记录的运行库与模型组合，不代表对全部音色和任意长稿件的质量保证。

自有脚本与模板采用 [MIT](LICENSE)；依赖与模型保留各自许可，见 [THIRD_PARTY.md](THIRD_PARTY.md)。
