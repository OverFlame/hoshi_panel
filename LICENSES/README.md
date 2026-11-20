# 第三方许可证

本目录存放随仓库分发的第三方作品的许可证全文。它不替代根目录的 `LICENSE`（本项目自身的 GPL-3.0）。

| 文件 | 覆盖对象 | 许可证 |
|---|---|---|
| `OFL-1.1-JetBrainsMono.txt` | JetBrains Mono 与 JetBrainsMono Nerd Font（界面等宽字体） | SIL Open Font License 1.1 |

## 尚未随仓库分发、但发布包里会带的

| 对象 | 许可证 | 处理 |
|---|---|---|
| psutil | BSD-3-Clause | Python 依赖，装进发布包时在其元数据里已带版权声明；`NOTICE.md` 有署名 |
| aiohttp、segno 等 | Apache-2.0 / BSD / MIT | 同上，改用 Python 包 | 

## 改动规则

1. 新增内嵌资源（字体、图标、音频）时，先查许可证，再在 `NOTICE.md` 表格里加一行，并把全文放本目录。
2. 字体只做子集化，不改字形：OFL 允许，无需改字体名。
3. 若修改字形或改名，必须避开 OFL 的保留字体名（本项目涉及的字体没有保留名限制，但仍不应把改过的版本叫 JetBrains Mono）。
