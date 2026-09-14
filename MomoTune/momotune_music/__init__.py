"""MomoTune 点歌命令、候选列表和音频发送。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..momotune_config import MOMOTUNE_CONFIG
from .qq_source import (
    QqSource,
    clear_credential as qq_clear_credential,
    create_qr_login,
    has_login as qq_has_login,
    wait_qr_login,
)
from .render import render_song_card
from .sources import (
    # KUGOU,
    NCM,
    QQ,
    BaseSource,
    # KugouSource,
    MusicSource,
    NcmSource,
    Song,
    SourceError,
    download,
    get_render_profile,
)

PENDING_TTL_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class TuneSettings:
    ncm_api_base: str
    kugou_api_base: str
    search_limit: int
    quality: str
    ncm_cookie: str
    kugou_cookie: str
    render_quality: str


@dataclass(frozen=True, slots=True)
class PendingSelection:
    songs: tuple[Song, ...]
    created_at: float


def _setting_text(key: str, default: str) -> str:
    value = MOMOTUNE_CONFIG.get_config(key, default).data
    return value if isinstance(value, str) and value.strip() else default


def _setting_int(key: str, default: int) -> int:
    value = MOMOTUNE_CONFIG.get_config(key, default).data
    if isinstance(value, int) and not isinstance(value, bool):
        return max(1, min(30, value))
    return default


def _settings() -> TuneSettings:
    return TuneSettings(
        ncm_api_base=_setting_text("ncm_api_base", "http://127.0.0.1:3030"),
        kugou_api_base=_setting_text("ncm_kugou_api_base", "http://127.0.0.1:3040"),
        search_limit=_setting_int("ncm_search_limit", 10),
        quality=_setting_text("ncm_quality", "exhigh"),
        ncm_cookie=_setting_text("ncm_cookie", ""),
        kugou_cookie=_setting_text("ncm_kugou_cookie", ""),
        render_quality=_setting_text("render_quality", "default").strip().lower(),
    )


class SourceRegistry:
    """配置变更后自动重建 source，同时保留酷狗 dfid。"""

    def __init__(self) -> None:
        self._fingerprint: tuple[str, str, str, str, str, str] | None = None
        self._sources: dict[MusicSource, BaseSource] = {}

    def snapshot(self) -> tuple[TuneSettings, dict[MusicSource, BaseSource]]:
        settings = _settings()
        fingerprint = (
            settings.ncm_api_base,
            settings.kugou_api_base,
            settings.quality,
            settings.ncm_cookie,
            settings.kugou_cookie,
            settings.render_quality,
        )
        if fingerprint != self._fingerprint:
            profile = get_render_profile(settings.render_quality)
            self._sources = {
                NCM: NcmSource(
                    settings.ncm_api_base,
                    settings.ncm_cookie,
                    settings.quality,
                    cover_size=profile.ncm_cover_size,
                ),

# --- 酷狗音源注册（已注释） ---
                # KUGOU: KugouSource(
                    # settings.kugou_api_base,
                    # settings.kugou_cookie,
                    # settings.quality,
                    # cover_size=profile.kugou_cover_size,
                # ),
                QQ: QqSource(
                    settings.quality,
                    cover_size=profile.qq_cover_size,
                ),
            }
            self._fingerprint = fingerprint
        return settings, self._sources


_REGISTRY = SourceRegistry()
_PENDING: dict[str, PendingSelection] = {}


def _pending_key(ev: Event) -> str:
    scope = ev.group_id if ev.group_id is not None else f"direct:{ev.user_id}"
    return f"{ev.bot_id}:{ev.bot_self_id}:{scope}:{ev.user_id}"


def _set_pending(ev: Event, songs: list[Song]) -> None:
    now = time.monotonic()
    for key, pending in tuple(_PENDING.items()):
        if now - pending.created_at > PENDING_TTL_SECONDS:
            del _PENDING[key]
    _PENDING[_pending_key(ev)] = PendingSelection(tuple(songs), now)


def _get_pending(ev: Event) -> tuple[Song, ...] | None:
    pending = _PENDING.get(_pending_key(ev))
    if pending is None:
        return None
    if time.monotonic() - pending.created_at > PENDING_TTL_SECONDS:
        del _PENDING[_pending_key(ev)]
        return None
    return pending.songs


def _clear_pending(ev: Event) -> None:
    _PENDING.pop(_pending_key(ev), None)


def _merge_detail(song: Song, detail: Song | None) -> Song:
    if detail is None:
        return song
    if song.name != "未知曲目" and song.pic_url is not None:
        return song
    return Song(
        source=song.source,
        song_id=song.song_id,
        name=detail.name if song.name == "未知曲目" else song.name,
        artist=detail.artist if song.artist == "未知歌手" else song.artist,
        album=detail.album if not song.album else song.album,
        pic_url=detail.pic_url if song.pic_url is None else song.pic_url,
        duration_ms=detail.duration_ms if song.duration_ms is None else song.duration_ms,
        extra=song.extra,
    )


async def _send_audio(bot: Bot, audio: bytes) -> None:
    """以语音 record 段发送音频。

    OneBot v11 能否呈现为语音气泡取决于桥接/适配器：snowluma_gscore_bridge
    （>=2.1.4）会直调协议端 record API 发真语音；不支持 record 段的链路
    （如官方 nonebot-plugin-genshinuid）会丢弃该段，需升级桥接。
    """
    await bot.send(MessageSegment.record(audio))


async def _play_song(
    bot: Bot,
    ev: Event,
    song: Song,
    source: BaseSource,
    render_quality: str = "default",
) -> tuple[bool, str]:
    try:
        play_url = await source.play_url(song)
    except SourceError as exc:
        msg = str(exc)
        await bot.send(msg)
        return False, msg
    except httpx.HTTPError as exc:
        logger.warning(f"[MomoTune] {source.label}获取播放链接失败: {exc}")
        msg = f"{source.label}暂时无法获取播放链接，请稍后再试。"
        await bot.send(msg)
        return False, msg

    if not play_url:
        msg = "这首歌暂时没有可用的播放链接（可能受版权限制），换一首试试吧。"
        await bot.send(msg)
        return False, msg

    if song.name == "未知曲目" or song.pic_url is None:
        try:
            song = _merge_detail(song, await source.detail(song.song_id))
        except (SourceError, httpx.HTTPError) as exc:
            logger.debug(f"[MomoTune] 获取歌曲详情失败 {song.song_id}: {exc}")

    try:
        card = await render_song_card(
            [song],
            title="正在播放",
            hint=f"{source.label} · MomoTune 为你选中的旋律",
            quality=render_quality,
        )
        await bot.send(MessageSegment.image(card))
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        logger.warning(f"[MomoTune] 渲染歌曲卡片失败 {song.song_id}: {exc}")

    try:
        audio = await download(play_url)
    except (SourceError, httpx.HTTPError) as exc:
        logger.warning(f"[MomoTune] 下载音频失败 {song.song_id}: {exc}")
        msg = f"下载音频失败（{exc}），请稍后再试。"
        await bot.send(msg)
        return False, msg
    await _send_audio(bot, audio)
    return True, f"《{song.name}》- {song.artist}"


music_sv = SV("MomoTune点歌", priority=5, area="ALL")
pick_sv = SV("MomoTune选歌", priority=15, area="ALL")
auth_sv = SV("MomoTune管理", priority=5, area="ALL")

SONG_COMMANDS = ("点歌", "唱歌", "来一首")

# --- 酷狗命令（已注释） ---
# KUGOU_COMMANDS = ("酷狗点歌", "酷狗唱歌", "酷狗来一首")

# --- QQ音乐单源点歌命令已合并进统一的「点歌」指令（网易云 + QQ 双源） ---
# QQ_COMMANDS = ("QQ点歌", "QQ唱歌", "QQ来一首", "qq点歌")


async def _handle_mixed_search(bot: Bot, ev: Event) -> None:
    """统一点歌：网易云 + QQ 音乐并发搜索，各取 5 条交替排列共 10 条候选。"""
    settings, sources = _REGISTRY.snapshot()
    ncm_source = sources.get(NCM)
    qq_source = sources.get(QQ)
    raw = ev.text.strip()
    if not raw:
        await bot.send("请输入歌名，例如：点歌 晴天")
        return

    # 纯数字 ID：直接按网易云歌曲 ID 播放
    if ncm_source is not None and raw.isdigit():
        _clear_pending(ev)
        await _play_song(bot, ev, Song(source=NCM, song_id=raw), ncm_source, settings.render_quality)
        return

    async def _search(src: BaseSource) -> list[Song]:
        try:
            return await src.search(raw, 5)
        except SourceError as exc:
            logger.warning(f"[MomoTune] {src.label}搜索失败: {exc}")
            return []
        except httpx.HTTPError as exc:
            logger.warning(f"[MomoTune] {src.label}搜索失败: {exc}")
            return []

    ncm_results: list[Song] = []
    qq_results: list[Song] = []
    tasks = []
    if ncm_source is not None:
        tasks.append(_search(ncm_source))
    if qq_source is not None:
        tasks.append(_search(qq_source))
    results_list = await asyncio.gather(*tasks)
    if ncm_source is not None:
        ncm_results = results_list.pop(0)
    if qq_source is not None:
        qq_results = results_list.pop(0) if results_list else []

    # 交替合并，最多 10 条
    mixed: list[Song] = []
    max_len = max(len(ncm_results), len(qq_results))
    for i in range(max_len):
        if i < len(ncm_results):
            mixed.append(ncm_results[i])
        if i < len(qq_results):
            mixed.append(qq_results[i])
        if len(mixed) >= 10:
            break

    if not mixed:
        await bot.send("网易云和 QQ 音乐都没有找到相关歌曲，请更换关键词。")
        return
    if len(mixed) == 1:
        _clear_pending(ev)
        await _play_song(bot, ev, mixed[0], sources[mixed[0].source], settings.render_quality)
        return

    try:
        card = await render_song_card(
            mixed,
            title="点歌候选",
            hint=f"回复数字 1～{len(mixed)} 播放对应曲目 · {PENDING_TTL_SECONDS // 60:.0f} 分钟内有效",
            quality=settings.render_quality,
        )
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        logger.warning(f"[MomoTune] 渲染搜索结果失败: {exc}")
        await bot.send("渲染搜索结果失败，请稍后再试。")
        return

    _set_pending(ev, mixed)
    await bot.send(MessageSegment.image(card))
    await bot.send(f"回复数字 1～{len(mixed)} 播放对应曲目（{PENDING_TTL_SECONDS // 60:.0f} 分钟内有效）")


@music_sv.on_command(
    SONG_COMMANDS,
    block=True,
    prefix=False,
)
async def search_song(bot: Bot, ev: Event) -> None:
    await _handle_mixed_search(bot, ev)


# --- 酷狗点歌命令（已注释） ---
# @music_sv.on_command(
#     KUGOU_COMMANDS,
#     block=True,
#     prefix=False,
# )
# async def kugou_song(bot: Bot, ev: Event) -> None:
#     await _handle_song_request(bot, ev, KUGOU)


def _is_admin(ev: Event) -> bool:
    """是否为管理员：user_pm 0=主人，1=超级用户。"""
    return ev.user_pm in (0, 1)


async def _wait_qq_login(bot: Bot, client: object, session: object) -> None:
    """后台等待扫码结果并主动通知。"""
    try:
        await wait_qr_login(client, session)
    except asyncio.TimeoutError:
        await bot.send("QQ音乐登录超时，二维码已失效，请重新发送「QQ音乐登录」。")
    except Exception as exc:
        logger.warning(f"[MomoTune] QQ音乐扫码登录失败: {exc}")
        if "超时" in str(exc):
            await bot.send("QQ音乐登录二维码已超时失效，请重新发送「QQ音乐登录」。")
        elif "拒绝" in str(exc):
            await bot.send("已取消 QQ音乐登录（扫码被拒绝）。")
        else:
            await bot.send(f"QQ音乐登录失败：{exc}，请稍后重试。")
    else:
        await bot.send("QQ音乐会员登录成功，现在可以用「QQ点歌」发送语音了。")


@auth_sv.on_command(
    ("QQ音乐登录", "QQ音乐登陆", "qq音乐登录"),
    block=True,
    prefix=False,
)
async def qq_login(bot: Bot, ev: Event) -> None:
    if not _is_admin(ev):
        await bot.send("仅主人或超级用户可以登录 QQ音乐会员账号。")
        return
    login_type = (ev.text.strip().lower() or "qq")
    if login_type not in ("qq", "wx", "mobile"):
        await bot.send("登录方式仅支持 qq / wx / mobile，例如：QQ音乐登录 wx")
        return
    await bot.send(f"正在获取{'微信' if login_type == 'wx' else 'QQ'}扫码登录二维码，请在 3 分钟内完成扫码…")
    try:
        client, session, qr_png = await create_qr_login(login_type)
    except SourceError as exc:
        await bot.send(str(exc))
        return
    except Exception as exc:
        logger.warning(f"[MomoTune] 创建 QQ音乐扫码会话失败: {exc}")
        await bot.send(f"获取登录二维码失败：{exc}")
        return
    await bot.send(MessageSegment.image(qr_png))
    asyncio.create_task(_wait_qq_login(bot, client, session))


@auth_sv.on_fullmatch(
    ("QQ音乐退出", "QQ音乐登出", "qq音乐退出"),
    block=True,
    prefix=False,
)
async def qq_logout(bot: Bot, ev: Event) -> None:
    if not _is_admin(ev):
        await bot.send("仅主人或超级用户可以清除 QQ音乐登录态。")
        return
    qq_clear_credential()
    await bot.send("已清除 QQ音乐登录态。")


@auth_sv.on_fullmatch(
    ("QQ音乐状态", "qq音乐状态"),
    block=True,
    prefix=False,
)
async def qq_status(bot: Bot, ev: Event) -> None:
    status = "已登录会员账号（QQ音乐语音点歌可用）" if qq_has_login() else "未登录（QQ音乐语音点歌需主人或超级用户发送「QQ音乐登录」）"
    await bot.send(f"MomoTune · QQ音乐状态：{status}。")


@pick_sv.on_message(prefix=False)
async def pick_song(bot: Bot, ev: Event) -> None:
    text = ev.raw_text.strip()
    if not text.isdigit():
        return
    pending = _get_pending(ev)
    if pending is None:
        return
    choice = int(text)
    if choice < 1 or choice > len(pending):
        await bot.send(f"请回复 1～{len(pending)} 之间的数字。")
        return
    song = pending[choice - 1]
    _clear_pending(ev)
    settings, sources = _REGISTRY.snapshot()
    await _play_song(bot, ev, song, sources[song.source], settings.render_quality)


logger.info("[MomoTune] 网易云 / 酷狗 / QQ音乐点歌触发器已注册")


# ─── AI Core 工具集成 ──────────────────────────────────────────────────────────
try:
    from pydantic_ai import RunContext
    from gsuid_core.ai_core.models import ToolContext
    from gsuid_core.ai_core.register import ai_tools

    @ai_tools(
        category="common",
        capability_domain="音乐播放",
        covers=[
            "网易云音乐点歌与歌曲播放",
            # "酷狗音乐点歌与歌曲播放",
            "QQ音乐点歌与歌曲播放",
            "按歌名或歌手播放歌曲音频与卡片",
            "根据用户需求点播音乐",
        ],
        aliases=[
            "音乐·点歌",
            "音乐·播放歌曲",
            "音乐·网易云放歌",
            # "音乐·酷狗放歌",
            "音乐·QQ音乐放歌",
        ],
        context_tags=["音乐", "点歌", "娱乐"],
    )
    async def play_music(
        ctx: RunContext[ToolContext],
        song_name: str,
        artist: str = "",
        source: str = "ncm",
    ) -> str:
        """搜索并直接播放指定歌曲。调用本工具后，机器人会直接将歌曲卡片与音频语音发送到当前聊天中。
当用户要求点歌、放歌、听歌、来一首歌、或希望播放某位歌手的特定歌曲时调用。

Args:
    song_name: 歌曲名称或关键词，例如“晴天”、“海阔天空”。若已知网易云歌曲ID也可直接填入数字ID（如“347230”，仅限网易云）。
    artist: 可选，歌手名称，例如“周杰伦”、“陈奕迅”，用于更精准命中。
    # source: 音乐平台源，"ncm"（网易云音乐，默认）、"kugou"（酷狗音乐）或 "qq"（QQ音乐，需管理员扫码登录会员账号）。

Returns:
    播放状态说明。若成功，卡片与音频已直接发送给用户；AI 无需再重复发送音频，可直接自然回复用户。
"""
        bot = ctx.deps.bot
        ev = ctx.deps.ev
        if bot is None or ev is None:
            return "错误：当前会话上下文缺失，无法发送音乐。"

        src_lower = source.lower()
        # if src_lower in ("kugou", "kg", "酷狗"):
            # src_name: MusicSource = KUGOU
        if src_lower in ("qq", "qqmusic", "tencent", "QQ音乐", "腾讯"):
            src_name = QQ
        else:
            src_name = NCM
        settings, sources = _REGISTRY.snapshot()
        source_obj = sources[src_name]

        clean_name = song_name.strip()
        if not clean_name:
            return "错误：未指定歌名。"

        # 1. 网易云纯数字 ID 直接播放
        if src_name == NCM and clean_name.isdigit():
            ok, info = await _play_song(
                bot, ev, Song(source=NCM, song_id=clean_name), source_obj, settings.render_quality
            )
            if ok:
                return f"已成功为用户播放网易云歌曲（ID: {clean_name}）。歌曲卡片与音频已发送到聊天中。"
            return f"播放失败：{info}"

        # 2. 构造搜索关键词并检索
        query = f"{artist.strip()} {clean_name}".strip() if artist.strip() and artist.strip() not in clean_name else clean_name
        try:
            results = await source_obj.search(query, settings.search_limit)
        except SourceError as exc:
            return f"搜索失败：{exc}"
        except httpx.HTTPError as exc:
            logger.warning(f"[MomoTune] {source_obj.label}搜索失败: {exc}")
            return f"搜索失败：连接{source_obj.label}服务超时或异常，请稍后重试。"

        if not results:
            return f"在{source_obj.label}未找到「{query}」相关的歌曲。建议更换歌名或尝试其他平台。"

        # 3. 挑选最佳匹配
        best_song = results[0]
        if artist.strip():
            art_lower = artist.strip().lower()
            for s in results:
                if art_lower in s.artist.lower():
                    best_song = s
                    break

        # 4. 执行播放并发送
        ok, info = await _play_song(bot, ev, best_song, source_obj, settings.render_quality)
        if ok:
            return f"已成功为用户播放歌曲：《{best_song.name}》- {best_song.artist}（来源：{source_obj.label}）。歌曲卡片与音频语音已直接发送给用户，AI 可以在对话中告知用户歌曲已送达。"
        return f"找到歌曲《{best_song.name}》- {best_song.artist}，但在播放时失败：{info}"

    logger.info("[MomoTune] MomoTune AI 音乐播放工具已注册")
except ImportError as e:
    logger.warning(f"[MomoTune] 未能加载 AI Core 模块，跳过 AI 工具注册: {e}")
