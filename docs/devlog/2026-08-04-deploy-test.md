# 统一入口 bilimuse-start + 从零部署测试 开发日志

- 日期：2026-08-04
- 里程碑：M9（部署体验）
- 关联：[pipeline 闭环](2026-08-04-pipeline-tui.md)、[便携模式](2026-08-04-portable.md)

## 目标与验收

- 目标：一个可双击的统一入口，集成「安装 → 配置 → 使用」；setup 补齐 tui/web/align 依赖。
- 验收标准：
  - `bilimuse-start.cmd` / `bilimuse-start` 无 venv 时自动全量安装，自动开配置向导，菜单可启动 TUI/Web/命令行。
  - `bilimuse-start config|tui|web` 参数直达。
  - 旧 `bilimuse-config` / `bilimuse-tui` 收敛为委托统一入口。
  - `setup.ps1` / `setup.sh` 默认全量 `[ffmpeg,align,tui,web,dev]`，`-Lite/--lite` 轻量。
  - 在 `test-deploy/`（远程克隆快照）中从零部署实测通过。

## 方案与思路（含否决方案）

- 方案 A：新增 `bilimuse-start.cmd`/`bilimuse-start` 统一入口，自带安装逻辑 + 菜单循环；`bilimuse.cmd` 保持纯命令转发。→ **采纳**。职责清晰：启动器管安装/配置/入口，命令包装器管脚本化调用。
- 方案 B：改造 `bilimuse.cmd` 无 venv 自动装、无参进菜单。→ 否决。命令转发与安装/菜单耦合，脚本调用会被菜单/安装流程干扰。
- 方案 C：在 `setup.ps1` 里加交互菜单。→ 否决。setup 只负责安装，交互入口应独立。
- 安装档位：全量默认 `[ffmpeg,align,tui,web,dev]`（一步到位），`-Lite` 仅 `.[dev]`；保留旧 `-WithFfmpeg` 语义被全量吸收后移除。

## 技巧

- cmd 内中文：文件存 **UTF-8 无 BOM** + 首行 `@echo off` 后紧跟 `chcp 65001 >nul`，菜单中文不再乱码；与 setup.ps1 需 BOM 的解法相反（cmd 读 UTF-8 要 chcp，PowerShell 5.1 要 BOM）→ `bilimuse-start.cmd:3`
- 首次配置探测：`python -c "from bilimuse.config import default_config_dir; sys.exit(0 if (default_config_dir()/'config.json').is_file() else 1)"`，用 `errorlevel` 判断是否自动开向导，无需解析 doctor 输出 → `bilimuse-start.cmd:15`
- 参数直达 + 菜单两种模式用 `goto :dispatch` 分流，`%~1` 判空；`setlocal` 保证局部变量不污染父 shell → `bilimuse-start.cmd:10`
- setup.ps1 参数数组：`$pipArgs = @(); if ($Mirror) { $pipArgs += @("-i", $Mirror) }`，`& $py -m pip install ... @pipArgs` 展开，避免字符串拼接引号地狱 → `setup.ps1`
- Web 启动方式：曾用 `start "标题" cmd /k "..."` 新窗口，后否决——无交互桌面环境（CI/服务化）`start` 建窗会挂死且引号转义脆弱；Web 改**当前窗口前台运行**（`"%PY%" -m bilimuse web`，Ctrl+C 返回菜单），行为与 `bilimuse web` 一致、随处可测 → `bilimuse-start.cmd:89`

## API / 库 速查

- `python -m venv <dir>`：建虚拟环境；`setup.ps1` 用 `Scripts\python.exe`，bash 用 `bin/python` → `setup.ps1:22` / `setup.sh:17`
- `pip install -e ".[extra1,extra2]"`：editable 安装可选依赖；`-i <mirror>` 指定镜像（默认清华）→ `setup.ps1:34`
- `[System.Management.Automation.Language.Parser]::ParseFile()`：无执行地校验 PowerShell 脚本语法（部署 CI 可复用）→ 验证小节

## 踩坑

- `setup.ps1` UTF-8 无 BOM → PowerShell 5.1 按系统 ANSI(GBK) 解析，中文乱码破坏字符串引号 → ParserError「字符串缺少终止符」。解决：转 **UTF-8 with BOM**（`WriteAllText` 传 `UTF8Encoding($true)`）。PowerShell 5.1 与 cmd/chcp 处理编码的机制不同，不可混用 → `setup.ps1`
- 原 setup 只装 `.[dev]`/`.[ffmpeg,dev]`，TUI/Web/align 全缺失，用户装完没提示 → 全量档默认 + 结尾提示。
- `.cmd` 若存 UTF-8 **带 BOM**，首行 `@echo off` 会被 BOM 前缀干扰；故 .cmd 用无 BOM + chcp，.ps1 用 BOM，两套标准分开记。
- `.cmd` 块内 echo 含圆括号 → cmd 括号匹配错乱 → `此时不应有 first.`。`if (...) { echo ... (xxx) }` 块内 echo 文本不得含裸 `(` `)` → `bilimuse-start.cmd:43`
- `set /p` 读管道/EOF 返回空 → `if "%ch%"==""` 无匹配 → 死循环菜单。加空输入直接退出兜底 → `bilimuse-start.cmd:32`
- cmd `chcp 65001` + UTF-8 在**批处理解析器**下不可靠（多字节吞换行粘连命令）→ `.cmd` 最终全 ASCII，中文交给 bash/README。

## 验证

- `setup.ps1`：`Parser::ParseFile` → parse OK（已加 BOM）
- `bilimuse-start.cmd`：`cmd /c "(echo 0)|bilimuse-start.cmd"` 菜单试跑、`bilimuse-start.cmd bogus` 未知参数提示（见下）
- `bash -n` 语法校验通过（setup.sh / bilimuse-start / bilimuse-config / bilimuse-tui）
- `ruff check bilimuse tests` 干净；`pytest -q` 70 用例全过
- 从零部署：`test-deploy/`（git clone）`.\setup.ps1` 全量安装成功 → 统一入口菜单正常
