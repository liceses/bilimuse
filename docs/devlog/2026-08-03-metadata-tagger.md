# 元数据反查与打标签 开发日志

- 日期：2026-08-03
- 里程碑：M3
- 关联：PLAN.md M3；[M2 下载与转码](2026-08-03-download.md)

## 目标与验收

- 目标：反查真实歌曲元数据（歌名/歌手/专辑/封面），用 mutagen 写入音频标签
- 验收标准：
  - 多源反查能命中真实曲目（含周杰伦等版权曲目）✅
  - 打标签支持 m4a(MP4) / mp3(ID3) / flac(VorbisComment)，含封面内嵌 ✅
  - `musicalbili tag <文件> --query "..."` 可打标签并回读验证 ✅
  - download 集成自动打标签（`--no-tag` 跳过）✅

## 方案与思路（含否决方案）

### 数据源：咪咕优先 → 网易云兜底（关键决策）

- **否决**：只用网易云。实测**周杰伦版权 2018 年已离开网易云**，搜"周杰伦 晴天"前 10 条全是关键词堆砌的翻唱/remix（`周杰伦- / A-LNK`、`周杰伦. / Asasblue` 等，短时长、假专辑），原版根本不在库，无法靠评分筛出。
- **选定**：咪咕音乐为第一源（正规曲库含周杰伦，MIGUM2.0 明文接口），网易云兜底。
- **否决 weapi 逆向**：网易云旧版明文接口 `api/search/get` + `api/song/detail` 直接可用，免 AES/RSA/cryptography 依赖。
- **否决** `static-ffmpeg` 等运行时下载（前文 ffmpeg 内嵌已定 imageio-ffmpeg）。

### 封面：webp → jpeg

- 咪咕封面是 `.webp`，mutagen 的 MP4Cover/APIC 不支持 webp；用内置 ffmpeg `-i - ... -vcodec mjpeg -` 管道转 jpeg（复用 imageio-ffmpeg，无新依赖）。
- **坑**：封面 URL 必须取自**搜索结果本身**（`SongMeta.cover`），不能拿 contentId 再搜一次（搜不到）。

## 技巧

- 标题清洗 `clean_title`：剥 `【】`、括号、循环剥尾部 `MV/4K/修复版/现场/翻唱` 等 token，再 `split_query` 拆出「歌手 - 歌名」→ `musicalbili/services/tagger.py:30`
- 匹配评分：歌名相似度 + 歌手命中加分（`_norm_artist` 剥尾标点，`周杰伦-`→`周杰伦`），歌手不符罚 0.4；阈值 0.5 → `tagger.py:55`
- 多源顺序即优先级：`search_metadata` 按 providers 顺序返回首个命中，咪咕在前 → `tagger.py:152`
- mutagen 打标签：m4a 用 `\xa9nam/\xa9ART/\xa9alb/covr`，mp3 用 `TIT2/TPE1/TALB/APIC(encoding=3 UTF-8)`，flac 用 VorbisComment + `add_picture` → `tagger.py:100`

## API / 库 速查

- `GET music.163.com/api/search/get?s=&type=1&offset=0&limit=`：网易云明文搜索；`result.songs[]` 含 `id/name/artists[].name/album.name/picUrl/duration`（picUrl 常空）→ `providers/meta.py:44`
- `GET music.163.com/api/song/detail?id=&ids=[id]`：补全封面；`songs[].album.picUrl` → `meta.py:69`
- `GET pd.musicapp.migu.cn/MIGUM2.0/v1.0/content/search_all.do?ua=Android_migu&version=5.0.1&text=&pageSize=&searchSwitch={song:1,...}`：咪咕明文搜索；返回 `songResultData.result[]`，字段 `contentId/name/singers[].name/albums[].name/imgItems[].img`（封面 webp），**无 duration** → `meta.py:96`
- `mutagen.mp4.MP4 / mutagen.id3.ID3 / mutagen.flac.FLAC`：标签读写 → `tagger.py`

## 踩坑

1. **网易云无周杰伦版权**：2018 年授权到期，搜索只剩翻唱/remix。→ 增加咪咕第一源（见上）。这是本项目数据源设计的核心教训。
2. **咪咕封面按 id 反查失败**：`fetch_cover_bytes` 原实现用 contentId 再 search 一次 → 返回空。→ 直接使用搜索结果里的 `imgItems` URL。
3. **webp 封面无法嵌入**：mutagen APIC/MP4Cover 只认 jpeg/png。→ ffmpeg 管道转 jpeg。
4. **导入路径**：`providers/meta.py` 里 `from .download import find_ffmpeg` 写成同级导入报 `ModuleNotFoundError`。→ 应为 `..services.download`。
5. **控制台乱码**：同 M1，`$env:PYTHONIOENCODING='utf-8'`。

## 验证

- `musicalbili tag` 对错标的 m4a 反查"周杰伦 - 晴天"：命中**咪咕**原版 `晴天/周杰伦/叶惠美`，重命名 `周杰伦 - 晴天.m4a` ✅
- 封面：原 webp 转 jpeg，内嵌 75982 bytes，magic `\xff\xd8\xff` ✅
- 端到端 `musicalbili download BV1M4411P7gM --format m4a`：下载 → 咪咕匹配「周杰伦 - 搁浅」→ 打标签重命名 ✅
  - 回读：`title=['搁浅'] artist=['周杰伦'] album=['七里香'] cover=True(69892B jpeg)` ✅
- `musicalbili list-downloads`：历史记录含真实标签 ✅
- `python -m pytest tests -q`：17 passed ✅
- `python -m ruff check musicalbili tests`：All checks passed ✅
