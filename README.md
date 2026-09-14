# MomoTune（简体中文）

<p align="center">
  <a href="https://github.com/Xinzhus/MomoTune"><img src="./ICON.png" width="180" alt="MomoTune 插件头像"></a>
</p>

<h1 align="center">MomoTune</h1>
<h4 align="center">✨ 一个指令，网易云 / QQ音乐双源点歌 ✨</h4>

<div align="center">
  <a href="https://github.com/Genshin-bots/gsuid_core">GsCore</a> &nbsp;·&nbsp;
  <a href="https://docs.sayu-bot.com/">官方文档</a> &nbsp;·&nbsp;
  <a href="https://github.com/Xinzhus/MomoTune/issues">问题反馈</a>
</div>

<br/>

## 丨项目简介

MomoTune 是运行在 [早柚核心（GsCore）](https://github.com/Genshin-bots/gsuid_core) 上的点歌插件。发送 **「点歌」** 指令时，插件会**并发**搜索网易云与 QQ 音乐两个音源，各返回 5 条结果，以交替顺序合并为一张 10 选 1 的候选卡片，回复数字即可播放对应歌曲的语音。

支持所有接入 GsCore 的上游 Bot（NoneBot2、HoshinoBot、ZeroBot、Yunzai、Koishi、AstrBot 等）。

> [!NOTE]
> 歌曲搜索、封面与播放地址来自你配置的后端接口。请自行确认音源的版权、地区限制以及接口服务条款。

<br/>

## 丨安装方式

### 方式一（推荐）：通过 GsCore 聊天安装

连接到 GsCore 后发送：

~~~text
core安装插件MomoTune
core重启
~~~

### 方式二：手动克隆

~~~bash
cd /path/to/gsuid_core/gsuid_core/plugins
git clone https://github.com/Xinzhus/MomoTune.git
~~~

然后重启 GsCore。

> [!IMPORTANT]
> 安装或更新插件后，需重启 GsCore 方可生效。

<br/>

## 丨依赖安装

插件本体依赖（网易云搜索 / 卡片渲染）：

~~~bash
pip install "httpx>=0.27.0" "pytakumi>=0.1.0"
~~~

**QQ 音乐**为可选依赖，不随插件打包，如需使用 QQ 音源请安装：

~~~bash
pip install "qqmusic-api-python>=0.7.2"
~~~

也可与插件本体依赖一并安装：

~~~bash
pip install "momo-tune[qqmusic]"
~~~

安装完成后重启 GsCore 即可生效。

<br/>

## 丨快速上手

| 触发指令 | 功能说明 | 备注 |
| :--- | :--- | :--- |
| <code>点歌 晴天</code> | 网易云 + QQ音乐**并发**搜索，各 5 条交替排列共 10 条候选 | <code>唱歌</code>、<code>来一首</code> 是同义指令；某一音源不可用时自动由另一音源补足 |
| <code>点歌 421423808</code> | 直接播放网易云歌曲 ID | 仅纯数字 ID，跳过搜索 |
| <code>QQ音乐登录 [qq\|wx\|mobile]</code> | 主人/超级用户扫码登录 QQ音乐会员 | 二维码 3 分钟内有效；**语音播放必需** |
| <code>QQ音乐退出</code> / <code>QQ音乐状态</code> | 清除登录态 / 查看登录状态 | 退出仅主人/超级用户可用 |
| <code>1</code> ～ <code>10</code> | 选择卡片里的歌曲 | 选择状态 5 分钟内有效 |

搜索到结果后，先看图片卡片，再回复对应数字。插件会发送歌曲信息卡片，并在播放地址可用时发送语音。

> [!NOTE]
> 酷狗音源相关代码目前处于**注释状态**（未启用）。如需启用，可在 `momotune_music/sources.py` 与 `momotune_music/__init__.py` 中找到对应注释块，取消注释后重新加载即可。

<br/>

## 丨功能特色

- **双源合并搜索**：「点歌」指令同时搜索网易云与 QQ 音乐，结果交替合并展示。
- **QQ音乐会员扫码**：主人/超级用户发送「QQ音乐登录」后可在聊天内扫码（支持 QQ / 微信 / QQ音乐 APP），登录态自动保存与刷新，登录后可播放 VIP 歌曲。
- **网易云 ID 直达**：支持直接输入网易云歌曲的数字 ID 跳过搜索、直接播放。
- **候选隔离**：不同群组、不同用户的候选列表相互隔离，避免干扰。
- **实时封面卡片**：卡片展示歌名、歌手、专辑、时长与来源，封面实时获取。
- **AI 可调用**：点歌触发器注册了 <code>to_ai</code>，GsCore AI 可通过自然语言（如"帮我找一首虚拟""用网易云放晴天"）触发点歌。
- **播放失败可解释**：因版权或后端限制无法获取播放地址时，会给出明确提示，而非静默失败。

<details>
<summary>渲染效果示例：网易云《虚拟》</summary>

<p align="center">
  <img src="./preview/virtual-api-render.png" width="680" alt="通过 api.ames.cc.cd 实时渲染的歌曲虚拟预览">
</p>

上图由配置的网易云接口实时返回：陈粒《虚拟》（专辑《小梦大半》）。右上角的圆形唱片使用该歌曲封面，非静态占位图。
</details>

<br/>

## 丨配置说明

所有配置均挂载于 GsCore 网页控制台的 **MomoTune** 配置项中，支持热更新，无需手动修改 JSON 文件。

| 配置键 | 默认值 | 说明 |
| :--- | :--- | :--- |
| <code>ncm_api_base</code> | <code>https://api.ames.cc.cd</code> | 网易云兼容 API 地址 |
| <code>ncm_kugou_api_base</code> | <code>http://127.0.0.1:3040</code> | 酷狗兼容 API（当前未启用） |
| <code>ncm_search_limit</code> | <code>10</code> | 单源最多展示的结果数，范围 1～30 |
| <code>ncm_quality</code> | <code>exhigh</code> | 音质等级，两源共用：standard→128k、higher/exhigh→320k、lossless/hires→FLAC |
| <code>ncm_cookie</code> | 空 | 可选的网易云 Cookie |
| <code>ncm_kugou_cookie</code> | 空 | 可选的酷狗 Cookie（当前未启用） |
| <code>render_quality</code> | <code>default</code> | 卡片渲染清晰度：<code>default</code>（96DPI）→ <code>high</code>（192DPI）→ <code>ultra</code>（288DPI，移动端更清晰但渲染开销更高） |

QQ 音乐音源无 API 地址与 Cookie 配置项：其直接调用 <code>qqmusic-api-python</code>，会员凭据通过「QQ音乐登录」扫码获得，保存于 GsCore 数据目录的 <code>MomoTune/qqmusic_credential.json</code>。

> [!WARNING]
> Cookie 属于敏感凭据，请勿写入 README、截图、Issue 或提交信息。建议仅在 WebConsole 的秘密配置项中填写；如发生泄露，请立即失效并重新获取。

<br/>

## 丨常见问题

| 现象 | 排查方向 |
| :--- | :--- |
| 搜索不到歌曲 | 检查 <code>ncm_api_base</code> 地址、网络连通性与后端日志 |
| 提示没有可用播放链接 | 多为版权或地区限制，可更换歌曲或音源重试 |
| 封面显示占位图 | 封面地址不可访问，检查证书与后端返回 |
| 渲染失败 | 确认 <code>pytakumi</code> 已安装于 GsCore 所用 Python 环境，并重启 Core |
| QQ音乐提示缺少依赖 | 未安装 <code>qqmusic-api-python</code>：执行 <code>pip install "qqmusic-api-python>=0.7.2"</code> 后重启 |
| 收不到语音 / 收到的是文件 | 需 <b>snowluma_gscore_bridge 2.1.4+</b> 方可发送语音气泡；旧版会降级为 mp3 文件，请升级桥接 |
| QQ音乐提示需要登录态 | 语音播放前须由主人/超级用户发送「QQ音乐登录」扫码；未登录时仅可查看候选卡片 |
| QQ音乐提示风控/暂时不可用 | 请求频率过高触发安全验证，请稍后重试或完成会员登录 |
| 回复数字无反应 | 须在同一会话中选择，且勿超过 5 分钟有效期 |

<br/>

## 丨项目结构

遵循 GsCore 嵌套插件约定：

~~~text
MomoTune/
├── MomoTune/                 # 插件本体
│   ├── momotune_music/       # 搜索、选择、播放、渲染（sources.py 网易云，qq_source.py QQ音乐）
│   ├── momotune_config/      # WebConsole 配置
│   └── __init__.py
├── templates/search_list.html
├── preview/virtual-api-render.png
├── ICON.png
├── resources/fonts/
├── pyproject.toml
└── README.md
~~~

<br/>

## 丨致谢与许可

- [GsCore / gsuid_core](https://github.com/Genshin-bots/gsuid_core)：插件运行时、触发器和消息收发。
- [pytakumi](https://github.com/KimigaiiWuyi/pytakumi)：HTML 卡片渲染引擎。
- [qqmusic-api-python](https://github.com/L-1124/QQMusicApi)：QQ音乐搜索、会员凭据与播放链接解析。
- 网易云兼容后端：提供搜索、封面与播放信息。

本项目仅供学习与交流使用。使用音源、转发或播放歌曲时产生的版权与合规责任由部署者自行承担。

本项目以 [GNU General Public License v3.0](https://github.com/Xinzhus/MomoTune/blob/main/LICENSE) 开源。

---
