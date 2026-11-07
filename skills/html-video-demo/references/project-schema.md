# 项目格式

`assets/starter/project.json` 是可直接使用的完整示例。下面的约定是脚本接口；场景内容和视觉风格可以按项目调整。

| 字段        | 用途                                                                                                                   |
| ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| `version`   | 当前为 `1`                                                                                                             |
| `title`     | 项目显示名称                                                                                                           |
| `language`  | Qwen 使用的语言名，如 `Chinese` / `English`                                                                            |
| `video`     | `width`、`height`、`fps`、`accent`                                                                                     |
| `voice`     | 模型、固定 revision、speaker、instruction、seed、temperature、max_tokens、max_group_chars、decoder_policy、target_lufs |
| `alignment` | 对齐和 ASR 模型、固定 revision、pre_roll_seconds、end_hold_seconds、cut_rms_dbfs                                       |
| `groups`    | 可选；按场景顺序列出 ID 分组，每个场景恰好出现一次                                                                     |
| `scenes`    | 有序场景列表                                                                                                           |

场景示例：

```json
{
  "id": "save-note",
  "title": "保存你的想法",
  "kind": "steps",
  "narration": ["先写下想法，再点击保存。", "新卡片会出现在列表中。"],
  "items": ["输入内容", { "text": "保存卡片", "cue": 1 }]
}
```

`id` 使用唯一的小写字母、数字和连字符。`narration` 按适合字幕展示的意群切分；合成时会把同组多个场景合并为完整讲述，而不是把每个字幕句单独随机生成。

内置场景类型：

| `kind`  | 额外字段                                                                 |
| ------- | ------------------------------------------------------------------------ |
| `title` | 可选 `headline`、`subtitle`                                              |
| `steps` | `items`，字符串或带 `text`、`cue` 的对象                                 |
| `image` | `media`，项目内的图片路径                                                |
| `video` | `media`，项目内的视频路径；可选 `poster`、`media_start`、`markers.video` |
| `code`  | `code`，会转义为文本                                                     |

例如：

```json
{
  "id": "edit",
  "title": "直接调整内容",
  "kind": "video",
  "media": "assets/edit-demo.mp4",
  "poster": "assets/edit-before.png",
  "narration": ["打开编辑器，查看当前内容。", "现在拖动这张卡片。"],
  "markers": { "video": "拖动这张卡片" }
}
```

标记文本必须实际出现在该场景旁白中。对齐后会转成秒数，录像从该标记开始播放。脚本会为录像保留足够时长；更复杂的鼠标轨迹与多阶段操作可在 HTML 模板里扩展。

图片支持 PNG、JPEG、WebP、SVG；录像支持 MP4、WebM。媒体路径必须在项目目录内，不能指向目录外的符号链接。不要把凭证、真实用户名或内部 URL 当作素材元数据。

## 运行数据

- `work/synthesis.json`：语音组、缓存指纹、生成统计。
- `work/transcript-check.json`：独立转写与文本差异。
- `work/word-alignment.json`：词级时间。
- `work/timing.json`：每幕起止时间、字幕、标记、尾字后保持时间。
- `work/boundaries.json`：切点能量和原始采样完整性。
- `work/scenes/`：自包含 HTML 分镜。
- `exports/<id>/`：独立成片、字幕、配置快照与验证结果。

`source_signature` 绑定 `project.json` 的字节内容。配置变化会使旧中间状态过期，避免新稿配旧声音或旧字幕。自定义截图或模板变化后应重新 compose，签名不替代资产内容审查。
