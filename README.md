# MomoTune（简体中文）

<p align="center">
  <a href="https://github.com/Xinzhus/MomoTune"><img src="./ICON.png" width="180" alt="MomoTune 插件头像"></a>
</p>

<h1 align="center">MomoTune</h1>
<h4 align="center">✨ 基于 GsCore 的网易云 / QQ音乐双源点歌插件 ✨</h4>

<div align="center">
  <a href="https://github.com/Genshin-bots/gsuid_core">GsCore</a> &nbsp;·&nbsp;
  <a href="https://docs.sayu-bot.com/">官方文档</a> &nbsp;·&nbsp;
  <a href="https://github.com/Xinzhus/MomoTune/issues">问题反馈</a>
</div>

<br/>

## 丨安装提醒

> **MomoTune 是 [早柚核心（GsCore / gsuid_core）](https://github.com/Genshin-bots/gsuid_core) 的扩展插件，使用前请先完成 GsCore 部署。**
>
> 支持所有已经接入 GsCore 的上游 Bot，包括 NoneBot2、HoshinoBot、ZeroBot、Yunzai、Koishi、AstrBot 等。
>
> 首次安装或更新插件后，请重启 GsCore 以完成加载。

本插件不提供独立 WebUI。搜索结果、播放信息和封面会渲染成图片卡片发送到聊天窗口。

> [!NOTE]
> 歌曲搜索、封面与播放地址来自你配置的后端接口。请自行确认音源的版权、地区限制以及接口服务条款。

<br/>

## 丨安装方式

### 方式一（推荐）：通过 GsCore 安装

在已经连接 GsCore 的聊天中发送：

~~~text
core安装插件MomoTune
core重启
~~~

依赖已经写入 <code>pyproject.toml</code>，开启 GsCore 自动安装依赖即可。若你的 Core 关闭了自动安装，请在 Core 使用的同一个 Python 环境执行：

~~~bash
pip install "httpx>=0.27.0" "pytakumi>=0.1.0"
~~~

QQ音乐依赖 <code>qqmusic-api-python</code> 为可选依赖，**不随插件内置**，启用 QQ 音乐功能前需在 GsCore 所用的同一个 Python 环境中安装：

~~~bash
pip install "qqmusic-api-python>=0.7.2"
~~~

安装完成后重启 GsCore 即可。若已开启 GsCore 的自动安装依赖，也可通过 <code>pip install "momo-tune[qqmusic]"</code> 一同安装。

### 方式二：手动克隆

~~~bash
cd /path/to/gsuid_core/gsuid_core/plugins
git clone https://github.com/Xinzhus/MomoTune.git
~~~

然后重启 GsCore。

<br/>

## 丨快速上手

| 触发指令 | 功能说明 | 备注 |
| :--- | :--- | :--- |
| <code>点歌 晴天</code> | 搜索网易云并展示候选 | <code>唱歌</code>、<code>来一首</code> 是同义指令 |
| ~~<code>酷狗点歌 花海</code>~~ | ~~搜索酷狗并展示候选~~ | 酷狗相关代码已注释，需要时可在源码中取消注释启用 |
| <code>QQ点歌 晴天</code> | 搜索 QQ音乐并展示候选 | <code>QQ唱歌</code>、<code>QQ来一首</code>、<code>qq点歌</code> 是同义指令 |
| <code>双源点歌 晴天</code> | 网易云 + QQ音乐并发搜索，各 5 条交替排列共 10 条候选 | <code>合并点歌</code>、<code>综合点歌</code> 是同义指令；网易云未登录时也可使用 |
| <code>QQ音乐登录 [qq\|wx\|mobile]</code> | 主人/超级用户扫码登录 QQ音乐会员 | 二维码 3 分钟内有效；语音播放必需，支持过期自动刷新 |
| <code>QQ音乐退出</code> / <code>QQ音乐状态</code> | 清除登录态 / 查看登录状态 | 退出仅主人/超级用户（user_pm 0/1）可用 |
| <code>1</code> ～ <code>10</code> | 选择候选列表中的歌曲 | 选择状态 5 分钟内有效 |
| <code>点歌 421423808</code> | 直接播放网易云歌曲 ID | 仅支持纯数字 ID，仅网易云音源 |

搜索到多个结果时，先查看图片卡片，再回复对应数字。插件会发送歌曲信息卡片，并在播放地址可用时发送语音记录。

> [!NOTE]
> 酷狗音乐相关代码已**注释**（包括命令注册、音源类与配置项），如需启用可在 `momotune_music/sources.py`、`momotune_music/__init__.py` 中找到对应注释块取消注释即可。

<br/>

## 丨功能特色

- **网易云 / 酷狗 / QQ音乐三源**：HTTP 兼容后端（网易云、酷狗）与 QQ音乐官方接口库统一为相同的点歌交互。
- **QQ音乐会员扫码登录**：主人（user_pm=0）或超级用户（user_pm=1）发送「QQ音乐登录」即可在聊天内扫码（QQ / 微信 / QQ音乐 APP），登录态加密保存在 Core 数据目录并自动刷新；登录后可解析 VIP 歌曲语音。
- **候选列表与数字选择**：结果按序号展示，候选状态按机器人、群组和用户隔离，避免串单。
- **网易云 ID 直达**：输入数字歌曲 ID 时跳过搜索，直接查询详情并播放。
- **实时封面卡片**：显示歌曲名、歌手、专辑、时长和来源，封面从接口实时取得。
- **圆形主封面**：搜索结果第一首歌的封面会被裁成圆形，并叠加唱片环与中心孔效果。
- **日系二次元视觉**：使用仓库内的 <code>MomoTuneWenKai</code> 字体，以及青蓝、奶油白、珊瑚橙配色。
- **AI 可调用**：点歌触发器注册了 <code>to_ai</code>，GsCore AI 可以理解“帮我找一首虚拟”“用网易云播放晴天”等自然语言。
- **版权失败可解释**：后端没有返回可用播放地址时，会给出明确提示，不会静默失败。

<details>
<summary>接口实时渲染示例：网易云《虚拟》</summary>

<p align="center">
  <img src="./preview/virtual-api-render.png" width="680" alt="通过 api.ames.cc.cd 实时渲染的歌曲虚拟预览">
</p>

上图由 <code>https://api.ames.cc.cd</code> 的 <code>cloudsearch</code> 接口实时返回第一条结果：陈粒《虚拟》（专辑《小梦大半》）。右上角的圆形唱片同样使用这首歌的封面，未使用静态占位图。
</details>

<br/>

## 丨后端接口与配置

所有配置均挂载在 GsCore 网页控制台的 **MomoTune** 配置项中，可以热更新，无需手动修改 JSON 文件。

| 配置键 | 默认值 | 说明 |
| :--- | :--- | :--- |
| <code>ncm_api_base</code> | <code>https://api.ames.cc.cd</code> | 网易云兼容 API；使用 <code>/cloudsearch</code>、<code>/song/detail</code>、<code>/song/url/v1</code> |
| <code>ncm_kugou_api_base</code> | <code>http://127.0.0.1:3040</code> | 酷狗兼容 API；使用 <code>/search</code>、<code>/song/url</code> |
| <code>ncm_search_limit</code> | <code>10</code> | 单次最多展示的结果数量，范围 1～30 |
| <code>ncm_quality</code> | <code>exhigh</code> | 网易云音质等级，酷狗会自动映射 |
| <code>ncm_cookie</code> | 空 | 可选的网易云 Cookie |
| <code>ncm_kugou_cookie</code> | 空 | 可选的酷狗 Cookie |
| <code>render_quality</code> | <code>default</code> | 卡片渲染清晰度：<code>default</code>（96DPI/封面240~300px）、<code>high</code>（192DPI 2倍图/封面480~500px）、<code>ultra</code>（288DPI 3倍图/封面最高800px，列表卡约4.5MB以内，渲染开销明显增加） |

QQ音乐音源没有 API 地址与 Cookie 配置项：它直接调用 <code>qqmusic-api-python</code> 库，会员凭据通过「QQ音乐登录」扫码获得，保存在 GsCore 数据目录的 <code>MomoTune/qqmusic_credential.json</code>。音质沿用 <code>ncm_quality</code>（standard→128kbps，higher/exhigh→320kbps，lossless/hires→FLAC，高音质不可用时自动降级）。

Cookie 属于敏感凭据，不要写进 README、截图、Issue 或提交信息。建议只在 WebConsole 的秘密配置项中填写；如果发生泄露，请立即失效并重新获取。

<br/>

## 丨渲染与字体

1. 读取搜索结果中的 <code>picUrl</code>，下载后转成 data URI 内嵌到 HTML，避免图片消息发送时出现外链失效。
2. 使用搜索结果第一首歌的封面作为右上角主视觉，<code>border-radius: 50%</code> 裁成圆形，再叠加唱片环和中心孔。
3. 列表中的每一项继续使用同一首歌的方形圆角封面，保持信息识别的一致性。
4. 封面地址不可访问时，回退到本地音符占位图，不影响候选信息发送。
5. 字体文件位于 <code>resources/fonts/LXGWWenKai-Regular.ttf</code>，注册名为 <code>MomoTuneWenKai</code>，不依赖系统默认字体。
6. <code>ICON.png</code> 使用你提供的插画做了抗锯齿圆形裁切，作为插件头像。

<br/>

## 丨常见问题

| 现象 | 排查方向 |
| :--- | :--- |
| 搜索不到歌曲 | 检查 <code>ncm_api_base</code>、网络连通性、关键词和后端日志 |
| 提示没有可用播放链接 | 可能是版权或地区限制；尝试其他版本、音源或 Cookie |
| 封面显示占位图 | 检查 <code>picUrl</code> 是否可访问、证书是否有效、后端是否返回图片地址 |
| 渲染失败 | 确认 <code>pytakumi</code> 安装在 GsCore 使用的 Python 环境中，然后重启 Core |
| QQ音乐提示缺少依赖 / <code>_vendor/wheels</code> 缺失 | 说明装的是**精简补丁**（仅文本代码，不含 77 个 wheel）。请改用完整发行包 <code>MomoTune-hd.zip</code> 覆盖整个 MomoTune 目录后重启；也可在 Core 的 Python 环境执行 <code>pip install "qqmusic-api-python>=0.7.2"</code>。错误提示会附带真实异常（如 <code>ImportError</code>/平台信息），反馈问题时请一并提供 |
| OneBot v11 收不到语音 / 收到的是文件 | 插件始终发送早柚 <code>record</code> 语音段。<b>snowluma_gscore_bridge 2.1.4+</b> 会直调协议端 record API 发送真正的语音气泡（要求 NapCat/Lagrange 等协议端支持 mp3，自动转 silk）；旧版桥接会降级成 mp3 文件，请升级桥接。官方 <code>nonebot-plugin-genshinuid</code> 无 record 分支会直接丢弃语音。另注意桥接 WS 单帧上限 64MB，音频本体限制 40MB |
| 首次 QQ点歌很慢/占磁盘 | 首次使用需把内置 wheel 解压到数据目录 <code>MomoTune/_vendor_lib/</code>（约数十 MB），仅一次，后续直接复用 |
| QQ音乐提示需要登录态 | 语音播放必须由主人或超级用户（user_pm 0/1）发送「QQ音乐登录」扫码；匿名状态只能看候选卡片 |
| QQ音乐提示风控/暂时不可用 | 请求过频触发安全验证，稍等再试，或完成会员登录 |
| 回复数字无反应 | 必须在同一会话中选择，且搜索结果没有超过 5 分钟有效期 |

<br/>

## 丨项目结构

项目结构遵循 GsCore 嵌套插件约定：

~~~text
MomoTune/
├── MomoTune/                 # GsCore 插件本体
│   ├── momotune_music/       # 搜索、选择、播放、渲染（sources.py 网易云/酷狗，qq_source.py QQ音乐）
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
- 网易云 / 酷狗兼容后端：提供搜索、封面与播放信息。

本项目仅供学习与交流使用。使用音源、转发或播放歌曲时产生的版权与合规责任由部署者自行承担。

本项目以 [GNU General Public License v3.0](https://github.com/Xinzhus/MomoTune/blob/main/LICENSE) 开源。

---

