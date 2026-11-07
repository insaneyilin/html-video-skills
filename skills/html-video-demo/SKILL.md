---
name: html-video-demo
description: 用 html-video 和本地 Qwen3-TTS 制作、修改带旁白与字幕的软件演示或技术讲解视频，包含真实界面采集、分镜、音色试听、字幕对齐和成片校验。适用于从项目文档或现有产品制作演示，以及修复尾音截断、段间语气跳变和转场不同步。
---

# HTML 视频与本地旁白

交付可播放的 MP4、字幕、可继续修改的 HTML 分镜和生成配置。以用户当前的项目、素材、音色与风格为准；这些脚本不绑定任何 AI Agent、账号或模型服务 API。

## 开始前

- 读取目标项目说明、已有成片与本地工作约定，确认实际功能和演示范围。不要把计划中的能力展示成已实现的界面。
- 指定独立的视频项目目录，保持原始代码、生产数据和旧版成片可恢复。修改现有视频时先读取最新配置和备份相关输出。
- 已确认的音色直接沿用。选择新音色时，优先用同一段短稿做等响度试听；无需重复要求用户确认已选定的方案。
- 初次运行或换机器时读 [环境与命令](references/setup.md)。本包的配音实现要求 Apple Silicon / MLX；Node 渲染入口独立于配音实现。

## 制作流程

1. **确定内容。** 把观众需要理解的操作串成因果明确的分镜。每幕一个主要信息，旁白口语化，画面保留关键文字。根据内容决定幕数与总时长，不套用固定九幕或两分钟模板。
2. **准备真实素材。** 用演示数据采集界面、局部截图或实际操作。浏览器控制方式遵循当前 Agent 和项目要求。读 [画面与素材](references/visuals.md)，不要复用其他项目的截图、人员信息或内部地址。
3. **确定声音。** 在 `project.json` 配置音色、风格和语言；先听新音色的短样，再批量生成。用相邻语义段落组成有界讲述组，沿用同一音色、风格和采样参数。不要逐句随机换种子，也不要默认整篇无限长合成。分组原则见 [旁白与对齐](references/audio.md)。
4. **核对内容与时序。** 用独立 ASR 找漏句或重复，再用强制对齐定位原稿。两者作用不同：对齐能给出时间，不能证明实际说对了所有文字。检查同音字、英文术语和最后几个字。
5. **按声音安排画面。** 在实际停顿处切章，保证最后一个字完整结束，并留出适合内容的收尾时间。默认约一秒可作为技术讲解的起点。局部强调与操作录像跟随语音标记，而不是沿用旧版固定秒数。
6. **用 html-video 渲染。** 先检查 HTML 抽帧，再通过 ContentGraph、ProjectOrchestrator 和 Hyperframes 导出。外部资源应本地化或嵌入；动画使用 `window.__hvPlayAll()`，避免字体加载期间提前播放。协议见 [画面与素材](references/visuals.md)。
7. **检查成片。** 完整解码 MP4，核对音视频时长和每个切幕点的音轨，再检查浏览器播放、跳转和画面。只检查 WAV 或字幕文件不足以证明最终视频正确。通过后提供本地预览、MP4、字幕和源文件。

## 可执行入口

所有路径由参数提供。完整字段见 [项目格式](references/project-schema.md)。下面的 `SKILL_DIR` 指本技能目录，`DEMO_PROJECT` 指独立的视频项目：

```sh
python "$SKILL_DIR/scripts/audio.py" init --project "$DEMO_PROJECT"
# 编辑 project.json，准备 assets/；必要时先运行 audition。
python "$SKILL_DIR/scripts/audio.py" validate --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" synthesize --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" check-text --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" align --project "$DEMO_PROJECT"
node "$SKILL_DIR/scripts/compose.mjs" --project "$DEMO_PROJECT"
node "$SKILL_DIR/scripts/verify.mjs" --project "$DEMO_PROJECT" --stage scenes
node "$SKILL_DIR/scripts/render.mjs" --project "$DEMO_PROJECT"
node "$SKILL_DIR/scripts/verify.mjs" --project "$DEMO_PROJECT" --stage export
node "$SKILL_DIR/scripts/serve.mjs" --project "$DEMO_PROJECT"
```

Node 的渲染、浏览器检查和截图命令通过 `HTML_VIDEO_ROOT` 或 `--html-video` 定位已安装的 html-video。使用隔离环境里的 Python，不把依赖装进系统 Python。

## 修改和排错

- 文案变更：重新合成受影响的组、核对、对齐、构建和渲染。图片或布局变更：重新构建、检查画面、渲染。音色变更：重新走声音与时序流程。
- 语音达到 token 上限或输出重复：缩短出问题的组，优先保留已验证的其余组。不要把不完整结果当成功交付；连续失败时保留诊断与可用素材，说明具体阻塞。
- 尾字不完整：按“原始合成 → 解码长度 → 归一化 → 拼接 → MP4”排查。**追加静音无法补回已经被裁掉的音节。** 当前脚本只在检测到 Qwen3-12Hz 无 padding 长度异常时启用局部修正，不改第三方安装目录。读 [字尾回归与音频排错](references/troubleshooting.md)。
- 不要把这次的音色、配色、组数或某版库的缺陷变成对所有任务的固定要求。若使用另一种 TTS 或已有配音，保留同样的时间、样本与导出校验约束。
- 成片发布到外部平台、上传业务资料或通知他人，不属于默认的本地制作步骤；按用户实际授权执行。
