# 歌词获取与时间轴校准 开发日志

- 日期：2026-08-03
- 里程碑：M4
- 关联：PLAN.md M4；[M3 元数据](2026-08-03-metadata-tagger.md)

## 目标与验收

- 目标：多源歌词获取（LRCLIB → 网易云 weapi → B站 AI 字幕）+ 时间轴校准（快速偏移/缩放 + lyric-align 强制对齐）
- 验收标准：
  - 下载后自动拿歌词，写 `.lrc` 侧车 + 内嵌音频标签 ✅
  - 快速校准：\|末行−时长\|≤5s 视为已同步不跑 whisper ✅
  - 翻唱/失配场景：装 `[align]` 后自动跑 lyric-align 强制对齐 ✅
  - 网易云 tlyric 翻译合并；纯音乐占位 LRC ✅
  - fMP4 m4a 时长用 ffmpeg 探测 ✅

## 方案与思路（含否决方案）

- 歌词源：LRCLIB（免 key，实测命中周杰伦晴天/七里香）→ 网易云 weapi `/song/lyric`（无周杰伦版权）→ B站 AI 字幕（需登录，质量差，兜底）。
- 校准两级：快速校准=廉价初筛（只信已同步）；失配自动跑 lyric-align（翻唱主场景：原词文字对上翻唱音频但时间轴不对）。
- **否决** `audio-offset-finder`：它对齐两段音频需要参考音频，我们没有 → 由缩放/lyric-align 覆盖。
- m4a 时长：保持直拷，需要时长时 ffmpeg `-i -f null -` 解析 Duration。
- whisper 触发：`calibrate()` 里"快速校准未通过(not synced) 且装了 [align] 且 align_enabled"才跑；`--align` 强制；`align_enabled=false` 关闭。
- **模型下载**：hf-mirror 实测 <15KB/s 不可用；ModelScope 镜像官方 `Systran/faster-whisper-small` 4.6MB/s。`whisper_model` 支持本地目录路径。

## 技巧

- `whisper_model` 直接给本地目录：faster-whisper 接受路径，`lyric-align --model <dir>` 透传 → `musicalbili/services/aligner.py:107`
- 子进程设 `PYTHONUTF8=1`：Windows 默认 GBK，lyric-align `read_text()` 无编码参数会读崩 UTF-8 歌词 → `aligner.py:111`
- `_align_exe()` 从 `sys.executable` 同级找 `lyric-align(.exe)`：`python -c` 时 venv\Scripts 不在 PATH，`shutil.which` 找不到 → `aligner.py:17`
- 时长探测：mutagen 先试（mp3/flac 准）→ ffmpeg `-i -f null -` 解析 `Duration:` 兜底（fMP4）→ `aligner.py:38`
- 网易云 LRC 清理：`clean_netease` 剥"作曲/编曲/制作人"元数据头；`merge_translation` 原句后插译文行 → `services/lyric.py`
- LRCLIB 可能命中 live 版：`clean_lrc` 剥空行 + 开头 <5s 的 `(liveN)` 标题标记行 → `lyric.py:28`

## API / 库 速查

- `GET lrclib.net/api/get?track_name=&artist_name=&duration=`（duration 为秒 float）：精确匹配，200 返回 syncedLyrics/plainLyrics，404 无 → `lyric.py:150`
- `GET lrclib.net/api/search?q=`：模糊，取前 5 条第一个有词的 → `lyric.py:153`
- 网易云 `weapi/song/lyric`（payload `{id, lv:-1, kv:-1, tv:-1}`）：返回 `lrc.lyric` + `tlyric.lyric` → `providers/meta.py:92`
- B站 `x/player/wbi/v2?bvid=&cid=`（需登录）：`data.subtitle.subtitles[]`，`subtitle_url` 指向 body[{from,to,content}] → `providers/bilibili.py:200`
- `lyric-align <audio> <lyrics.txt> -o out.lrc -f lrc --language zh --model <size|path> --no-vad -q`：字符级模糊锚定，CJK 阈值 0.25；`--no-vad` 对慢歌必要 → `aligner.py:103`
- `faster-whisper`：PyAV 内嵌 ffmpeg 解码，无需系统 ffmpeg；py3.14 需 >=1.3.0（实测 1.2.1 也能装）

## 踩坑

1. **mutagen 读 fMP4 时长为 0**：B站 DASH 是分片 MP4，时长在 moof 片段头；直拷 m4a mutagen 读 0.0s → 用 ffmpeg `-i -f null -` 解析 Duration → `aligner.py:38`。
2. **hf-mirror 模型下载极慢**：实测 8MB/60s 超时（<15KB/s），466MB 的 small 模型要数小时 → 改 ModelScope `Systran/faster-whisper-small`（4.62MB/s），`whisper_model` 指向本地目录。
3. **lyric-align GBK 编码崩**：`read_lyrics` 用 `path.read_text()` 无编码，Windows 默认 GBK 读 UTF-8 中文歌词报 `UnicodeDecodeError: 'gbk' codec can't decode` → 子进程 `PYTHONUTF8=1`。
4. **`shutil.which` 找不到 venv console script**：`python -c`/`python -m` 时 venv\Scripts 不在 PATH → `_align_exe()` 从 `sys.executable` 同级补找。
5. **Config 文件 BOM + 类型字符串化**：PowerShell `Set-Content -Encoding UTF8` 写 BOM → `utf-8-sig` 读取；`download_dir` 被 JSON 覆盖成 str → `load()` 末尾强制 `Path()`。
6. **`《》` 式标题匹配失败**：`split_query` 只认 ` - ` 分隔，`周杰伦《七里香》...` 匹配不到 → 增加《》提取（`《([^》]+)》` 内为歌名，前面为歌手）。
7. **LRCLIB 命中 live 版歌词**：`搁浅(live04)` 标题行 + 空行污染 → `clean_lrc` 清理。
8. **align 触发条件 bug**：`calibrate()` 初写 `method=="none"` 才跑 align，导致 scale 情形不跑 → 改为 `not synced`。

## 外文歌实测（One Last Kiss / EVA）与校准回退设计

### 实测结果

- `BV1Eb4y1Q7GD`（官方 MV 259s，日英混词）：migu 元数据「宇多田ヒカル - One Last Kiss」→ LRCLIB 歌词 56 行。
- **歌词内容完全正确**：日语（初めてのルーブルは/私だけのモナリザ/あの日動き出した歯車/忘れたくないこと/燃えるようなキスをしよう/忘れられない人）+ 英语（Can you give me one last kiss? / I love you more than you'll ever know, oh / Oh, can you give me one last kiss?）共 19 行含英文，与真实歌词逐行一致。
- **whisper(small) 只对齐了 18/56 行**（匹配率 32%）——小模型对日语歌唱误听多，后半段（"忘れられない人" 结尾）几乎全丢。

### 设计修正（本次引入）

1. **`「」` 日式引号提取**：`split_query` 优先匹配 `《》`/`「」` 内歌名（宇多田ヒカル「One Last Kiss」→ 宇多田ヒカル / One Last Kiss），否则被末尾 `-宇多田光` 干扰。
2. **网易云空行清理**：`clean_netease` 同时剥空内容行（网易云该歌首行 `[00:18.610]` 无内容）。
3. **align 置信度回退（核心）**：`calibrate_align` 改用 `-f json --interpolate`，从每行 `matched` 标记统计匹配率；**<50% 或 <5 行判为失败返回 None** → `calibrate` 保留原歌词（完整、内容正确）。
4. **取消自动 scale**：实测缩放对"带器乐尾声/前奏"的歌有害（One Last Kiss 会把 231s 歌词硬拉到 259s +12%）；失配且 align 不可用/失败时**按原样保存** + 警告，不再盲目缩放。

### 验证（修正后）

- One Last Kiss：匹配率低 → 回退，`.lrc` = 完整 56 行原词（首 `[00:21.84]初めてのルーブルは`，末 `[03:51.60]追いかけた眩しい午後`），方法标记 `source` + 警告 ✅
- 七里香回归：匹配率高 → align 完整 32 行（`--interpolate` 补全，此前只有 28 行）✅

## M4.5 增强：语言检测 + 锚点线性拟合 + 更大模型 + 人声分离

### 问题复盘（One Last Kiss 前留白）

- 症状：歌词整体提前 ~8s（官方 MV 有前留白），且"没真正对齐"。
- 根因一（**最大**）：`calibrate_align` **硬编码 `--language zh`**，One Last Kiss 是日语 → whisper 用中文识别日语转写严重失真 → 匹配率仅 18/56（32%）→ 触发回退，把没加偏移的原词存下。
- 根因二：官方 MV ~8s 前留白，LRCLIB（按 CD 同步）歌词整体偏早。

### 新增能力

1. **语言自动检测**：`detect_lyric_language` 本地字符判定（假名→ja 决定性、谚文→ko、汉字→zh、西里尔→ru、拉丁→en）；**咪咕 tags 网络信号**（`_lang_from_tags`：日语/国语/英语/韩语/粤语/泰语）；兜底 `cfg.whisper_language`（默认 zh）。实测网易云 weapi detail/search **无 language 字段**、LRCLIB 无 → 网络侧仅咪咕 tags 可用。
2. **whisper 锚点线性拟合**：`_apply_alignment` 从 `-f json` 拿每行 `matched`：
   - 匹配率 ≥50% → lyric-align interpolate 完整输出（method `align`）；
   - 锚点 ≥3 但 <50% → 最小二乘拟合 `aligned = a·source + b` 整体变换**完整源歌词**（method `align_offset`，治前留白/变速）；
   - 锚点 <3 → 保留原词 + 警告。
3. **更大模型**：`whisper_model` 已支持 medium/large-v3-turbo（文档注明更准更慢）。
4. **人声分离（可选）**：`[separate]` extra（torch）+ `cfg.vocal_separate`，开启且装 demucs 时 `--separate`，未装降级提示。

### 验证（增强后）

- One Last Kiss（`--language ja` 生效）：匹配率 **32% → 96%**（54/56 行），首句 `[00:28.00]初めてのルーブルは`（贴近真实发声 ~30s，前留白抵消），末 `[04:23.18]追いかけた眩しい午後`，17 行英文 ✅
- 七里香回归：detect zh → `align` 完整 32 行 ✅
- 单测：`detect_lyric_language`（ja/zh/ko/ru/en）、`_linear_fit`（偏移/缩放/退化）、`_apply_alignment` 三分支 ✅（36 passed）

## 验证

- 七里香端到端（m4a，align 开启）：下载 → migu 元数据「周杰伦 - 七里香」→ lrclib 歌词 → **lyric-align 对齐 28 行**，首 `[00:30.00]窗外的麻雀 在電線桿上多嘴`，末 `[04:25.96]...唯一想要的瞭解`（4:58 视频留器乐尾）✅
  - `.lrc` 侧车写入 + m4a `\xa9lyr` 内嵌 28 行验证一致 ✅
- 搁浅（align 关）：lrclib 46 行 → scale 缩放校准 + 警告"装 [align] 可强制对齐" ✅
- `doctor`：`歌词校准: lyric-align 可用（whisper=<本地模型路径>）` + HF 镜像 ✅
- `python -m pytest tests -q`：29 passed ✅（含 LRC 解析/清理/翻译合并/快速缩放）
- `python -m ruff check musicalbili tests`：All checks passed ✅
- 模型获取：ModelScope `Systran/faster-whisper-small`（config/model.bin 472MB/tokenizer.json/vocabulary.txt），`models/` 已 gitignore
