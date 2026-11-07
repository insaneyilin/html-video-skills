# 环境与命令

## 已验证的组合

- Apple Silicon Mac，Python 3.12，MLX Audio 0.6.4，MLX 0.32.4。
- Node.js 20+、ffmpeg / ffprobe、Playwright Chromium。
- html-video 的本地源码及其 `content-graph`、`core`、`adapter-hyperframes` 构建产物。
- 本次验证使用 html-video commit `c414ecc07f795add03807d5d9ce4baefd807cea2`。这是验证基线，不表示未来版本一定不兼容。

`scripts/requirements-mlx-tested.txt` 是测试环境快照。升级库或模型后，应重新跑 decoder probe、短音频和小视频检查，不要将已观察到的回归假设为所有版本都存在。

## 依赖准备

按 html-video 仓库的说明安装依赖。仅使用本流程时，需要的构建目标是：

```sh
node node_modules/typescript/bin/tsc -p packages/content-graph/tsconfig.json
node node_modules/typescript/bin/tsc -p packages/core/tsconfig.json
node node_modules/typescript/bin/tsc -p packages/adapter-hyperframes/tsconfig.json
node packages/adapter-hyperframes/node_modules/playwright/cli.js install chromium
```

这些命令在 html-video 根目录执行。包管理器若阻止了与本流程无关的安装脚本，不要顺手批准所有依赖；先确认所需 TypeScript 和浏览器依赖是否已安装，再构建实际需要的包。本流程不要求另启一个 AI Agent，也不要求云端语音账号。

```sh
export HTML_VIDEO_ROOT=/path/to/html-video
export SKILL_DIR=/path/to/html-video-skills/skills/html-video-demo
export DEMO_PROJECT=/path/to/your-video-project
uv venv --python 3.12 /path/to/isolated-env
uv pip install --python /path/to/isolated-env/bin/python -r "$SKILL_DIR/scripts/requirements-mlx-tested.txt"
```

用隔离环境的 Python 执行音频命令。模型首次下载到 Hugging Face 的常规缓存目录，模型 ID 和 revision 位于项目配置，推理在本机进行。

## 常用命令

```sh
python "$SKILL_DIR/scripts/audio.py" init --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" validate --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" audition --project "$DEMO_PROJECT" --voices Serena Uncle_Fu --text "同一段需要试听的文本。"
python "$SKILL_DIR/scripts/audio.py" synthesize --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" check-text --project "$DEMO_PROJECT"
python "$SKILL_DIR/scripts/audio.py" align --project "$DEMO_PROJECT"
node "$SKILL_DIR/scripts/compose.mjs" --project "$DEMO_PROJECT"
node "$SKILL_DIR/scripts/verify.mjs" --project "$DEMO_PROJECT" --stage scenes
node "$SKILL_DIR/scripts/render.mjs" --project "$DEMO_PROJECT"
node "$SKILL_DIR/scripts/verify.mjs" --project "$DEMO_PROJECT" --stage export
node "$SKILL_DIR/scripts/serve.mjs" --project "$DEMO_PROJECT"
```

`serve.mjs` 默认选择空闲本机端口，可通过 `--port` 指定。`capture.mjs`、`render.mjs`、`verify.mjs` 可用 `--html-video` 替代环境变量。无需启动 html-video Studio；脚本直接调用其核心接口。

`check-text` 只报告差异，不把机器识别当成自动验收。阅读 `work/transcript-check.json`：同音字、英文大小写和标点差异可能无需重做，遗漏整句、重复短语或缺失结尾需要处理。

## 版本与更新

每次 render 创建新的 `exports/时间戳-短ID/`，不会覆盖旧 MP4。修改 `project.json` 后旧时序会被拒绝；重新运行音频步骤会复用仍匹配的成功合成组。只改 HTML 模板或截图时，重新 compose、检查场景、render 和检查 export。

用户已有成片时，保留那一版及其配置。只把通过检查的版本设为本地默认预览；外部发布由用户的实际授权决定。
