"""QQ 音乐音源（基于 qqmusic-api-python，会员扫码登录后可解析播放链接）。

与网易云/酷狗不同，QQ 音乐不经过自建 HTTP 后端，而是直接调用
``qqmusic-api-python`` 库；登录态（Credential）持久化在 GsCore
数据目录的 MomoTune/qqmusic_credential.json。
"""

from __future__ import annotations

import importlib
import json
from typing import Any

from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger

from .sources import BaseSource, QQ, Song, SourceError, _text

CREDENTIAL_PATH = get_res_path() / "MomoTune" / "qqmusic_credential.json"
LOGIN_TIMEOUT = 180.0

# MomoTune 音质等级（网易云命名）→ QQ 音乐文件类型键
_QQ_QUALITY_MAP: dict[str, str] = {
    "standard": "MP3_128",
    "higher": "MP3_320",
    "exhigh": "MP3_320",
    "lossless": "FLAC",
    "hires": "FLAC",
    "jyeffect": "MP3_320",
    "sky": "FLAC",
    "jymaster": "FLAC",
}

_lib: Any = None
_credential: Any = None
_credential_loaded = False


_DEP_HINT = (
    "QQ音乐功能缺少依赖 qqmusic-api-python，请在 GsCore 使用的 Python 环境执行"
    "「pip install \"qqmusic-api-python>=0.7.2\"」后重启 Core。"
)


def _load_lib() -> Any:
    """惰性导入 qqmusic_api；未安装时给出可直接执行的提示。"""
    global _lib
    if _lib is not None:
        return _lib
    try:
        _lib = importlib.import_module("qqmusic_api")
    except ImportError as exc:
        raise SourceError(_DEP_HINT) from exc
    return _lib


def _mod(name: str) -> Any:
    """导入 qqmusic_api 子模块；依赖缺失/损坏时统一转为可读提示。"""
    try:
        _load_lib()
        return importlib.import_module(name)
    except ImportError as exc:
        raise SourceError(_DEP_HINT) from exc


def _load_credential() -> Any | None:
    global _credential, _credential_loaded
    if _credential_loaded:
        return _credential
    _credential_loaded = True
    if not CREDENTIAL_PATH.exists():
        return None
    try:
        data = json.loads(CREDENTIAL_PATH.read_text(encoding="utf-8"))
        _credential = _load_lib().Credential(**data)
    except Exception:
        logger.exception("[MomoTune] 读取 QQ音乐登录态失败")
        _credential = None
    return _credential


def _save_credential(credential: Any) -> None:
    global _credential, _credential_loaded
    CREDENTIAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIAL_PATH.write_text(
        json.dumps(credential.model_dump(by_alias=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _credential = credential
    _credential_loaded = True
    logger.info(f"[MomoTune] QQ音乐登录态已保存: {CREDENTIAL_PATH}")


def clear_credential() -> None:
    global _credential, _credential_loaded
    _credential = None
    _credential_loaded = True
    if CREDENTIAL_PATH.exists():
        CREDENTIAL_PATH.unlink()


def has_login() -> bool:
    return _load_credential() is not None


async def create_qr_login(login_type: str = "qq") -> tuple[Any, Any, bytes]:
    """创建扫码登录会话，返回 (client, session, 二维码 PNG)。"""
    lib = _load_lib()
    login_models = _mod("qqmusic_api.models.login")
    login_utils = _mod("qqmusic_api.modules.login_utils")
    type_map = {
        "qq": login_models.QRLoginType.QQ,
        "wx": login_models.QRLoginType.WX,
        "mobile": login_models.QRLoginType.MOBILE,
    }
    if login_type not in type_map:
        raise SourceError("登录方式仅支持 qq / wx / mobile。")
    client = lib.Client()
    await client.__aenter__()
    try:
        session = login_utils.QRCodeLoginSession(
            client.login,
            type_map[login_type],
            interval=1.5,
            timeout_seconds=LOGIN_TIMEOUT,
        )
        qr = await session.get_qrcode()
        return client, session, qr.data
    except Exception:
        await client.close()
        raise


async def wait_qr_login(client: Any, session: Any) -> Any:
    """等待扫码完成并持久化登录态；超时/取消会抛异常。"""
    try:
        credential = await session.wait_qrcode_login()
        _save_credential(credential)
        return credential
    finally:
        await client.close()


class QqSource(BaseSource):
    """QQ 音乐音源；不使用 HTTP 后端，base/cookie 参数对其无意义。"""

    name = QQ

    def __init__(self, quality: str, cover_size: int) -> None:
        self.quality = quality
        self.cover_size = cover_size

    def _file_type(self, song_mod: Any, quality_key: str) -> Any:
        key = _QQ_QUALITY_MAP.get(quality_key, "MP3_128")
        return getattr(song_mod.SongFileType, key, song_mod.SongFileType.MP3_128)

    @staticmethod
    def _parse(raw: Any, cover_size: int) -> Song | None:
        try:
            mid = _text(getattr(raw, "mid", ""))
            if not mid:
                return None
            singers = "/".join(
                name
                for s in getattr(raw, "singer", [])
                if (name := getattr(s, "name", ""))
            )
            album = getattr(getattr(raw, "album", None), "name", "") or ""
            pic_url = ""
            try:
                pic_url = raw.cover_url(cover_size) or ""
            except Exception:
                logger.debug("[MomoTune] QQ音乐封面获取失败", exc_info=True)
            interval = int(getattr(raw, "interval", 0) or 0)
            numeric_id = getattr(raw, "id", "")
            return Song(
                source=QQ,
                song_id=mid,
                name=_text(getattr(raw, "name", ""), "未知曲目"),
                artist=_text(singers, "未知歌手"),
                album=_text(album),
                pic_url=pic_url or None,
                duration_ms=interval * 1000,
                extra={"id": _text(numeric_id)},
            )
        except Exception:
            logger.warning("[MomoTune] QQ音乐歌曲数据解析失败", exc_info=True)
            return None

    async def search(self, keyword: str, limit: int) -> list[Song]:
        lib = _load_lib()
        search_mod = _mod("qqmusic_api.modules.search")
        num = max(1, min(int(limit), 10))
        try:
            async with lib.Client(_load_credential()) as client:
                resp = await client.search.search_by_type(
                    keyword,
                    search_mod.SearchType.SONG,
                    num=num,
                )
        except SourceError:
            raise
        except Exception as exc:
            logger.warning(f"[MomoTune] QQ音乐搜索失败: {exc}")
            raise SourceError(f"QQ音乐搜索暂时不可用（{type(exc).__name__}），请稍后再试。") from exc
        items = getattr(resp, "song", None) or []
        return [
            song
            for raw in items
            if (song := self._parse(raw, self.cover_size)) is not None
        ][:num]

    async def play_url(self, song: Song) -> str | None:
        lib = _load_lib()
        song_mod = _mod("qqmusic_api.modules.song")
        credential = _load_credential()
        if credential is None:
            raise SourceError(
                "QQ音乐语音播放需要会员登录态，请由超级用户发送「QQ音乐登录」扫码登录后再试。"
            )

        try:
            return await self._resolve_play_url(lib, song_mod, song, credential)
        except SourceError:
            raise
        except Exception as exc:
            logger.warning(f"[MomoTune] QQ音乐播放链接获取失败 {song.song_id}: {exc}")
            raise SourceError(f"QQ音乐暂时无法获取播放链接（{type(exc).__name__}），请稍后再试。") from exc

    async def _resolve_play_url(self, lib: Any, song_mod: Any, song: Song, credential: Any) -> str | None:
        async with lib.Client(credential) as client:
            cdn_dispatch = await client.song.get_cdn_dispatch()
            sip = getattr(cdn_dispatch, "sip", None) or []
            cdn = sip[0] if sip else "https://isure.stream.qqmusic.qq.com/"

            async def _resolve(cred: Any, file_type: Any) -> str | None:
                resp = await client.song.get_song_urls(
                    [song_mod.SongFileInfo(mid=song.song_id)],
                    file_type=file_type,
                    credential=cred,
                )
                for info in resp.data:
                    if info.purl:
                        return cdn + info.purl
                return None

            file_type = self._file_type(song_mod, self.quality)
            try:
                url = await _resolve(credential, file_type)
            except TypeError:
                # 兼容旧版库签名：不支持 credential 关键字
                resp = await client.song.get_song_urls(
                    [song_mod.SongFileInfo(mid=song.song_id)],
                    file_type=file_type,
                )
                url = None
                for info in resp.data:
                    if info.purl:
                        url = cdn + info.purl
                        break
            if url:
                return url
            # 高音质失败时降级标准音质
            if file_type is not song_mod.SongFileType.MP3_128:
                logger.info(f"[MomoTune] QQ音乐 {song.song_id} 高音质无链接，降级 MP3_128")
                url = await _resolve(credential, song_mod.SongFileType.MP3_128)
                if url:
                    return url
            # 登录态过期时刷新一次
            try:
                new_cred = await client.login.refresh_credential(credential)
                _save_credential(new_cred)
                return await _resolve(new_cred, file_type)
            except Exception:
                logger.warning("[MomoTune] QQ音乐登录态刷新失败", exc_info=True)
                return None
