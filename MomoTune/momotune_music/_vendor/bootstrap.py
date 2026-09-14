"""内置依赖引导：从随插件分发的 wheels 中选择与当前解释器匹配的版本解压加载。

设计要点：
- 纯标准库实现，不依赖 packaging/pip；
- 支持 Linux（manylinux，x86_64/aarch64）与 Windows（win_amd64；CPython 3.11~3.13），
  其他平台（macOS、Win32/ARM64）回退系统环境；
- 系统已安装且兼容的包优先（vendor 默认 append 到 sys.path 末尾）；
  系统包版本不兼容遮蔽 vendor 时，自动把 vendor 提到最前后重试；
- wheel 只解压一次到 GsCore 数据目录，wheels 清单变化时重新解压；
- 首次使用 QQ音乐时惰性执行，不影响网易云/酷狗音源加载速度。
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path

WHEELS_DIR = Path(__file__).resolve().parent / "wheels"
_MANIFEST_NAME = "_vendor_manifest.json"

# 判定“环境中 qqmusic 可用”时需要真正导入的子模块：
# 仅 import qqmusic_api 可能成功，但子依赖版本不兼容会在子模块导入时才爆炸。
_PROBE_MODULES = (
    "qqmusic_api",
    "qqmusic_api.modules.song",
    "qqmusic_api.modules.login_utils",
)


class VendorError(RuntimeError):
    """内置依赖无法加载，消息面向最终用户（中文、可操作）。"""


def _platform_desc() -> str:
    vmaj, vmin = sys.version_info.major, sys.version_info.minor
    return (
        f"{sys.platform} / {platform.machine()} / CPython {vmaj}.{vmin}；"
        "内置矩阵仅支持 Linux x86_64、aarch64 与 Windows x64(AMD64) 上的 CPython 3.11~3.13"
    )


def _try_probe() -> Exception | None:
    """尝试导入 qqmusic 关键模块；失败时清理本次半载入的模块并返回异常。"""
    before = set(sys.modules)
    try:
        for name in _PROBE_MODULES:
            importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - 需要覆盖版本不兼容导致的任意异常
        # 半初始化模块必须清理，否则即使调整了 sys.path 也不会重新执行
        for name in set(sys.modules) - before:
            sys.modules.pop(name, None)
        return exc
    return None

# manylinux wheel 的平台段可能是多个点分别名，全部视为兼容（glibc >= 2.17）
_LINUX_MACHINES = {
    "x86_64": ("x86_64", "amd64"),
    "aarch64": ("aarch64", "arm64"),
}
# Windows 上 platform.machine() 的取值 → wheel platform_tag
_WINDOWS_MACHINES = {
    "amd64": ("win_amd64",),
    "x86": ("win32",),
    "arm64": ("win_arm64",),
}


def _platform_spec() -> tuple[str | None, tuple[str, ...]]:
    """返回 (平台族, 可接受的 wheel 平台别名)；不在内置矩阵的平台返回 (None, ())。

    内置矩阵仅覆盖：Linux x86_64/aarch64 与 Windows x64(AMD64)。
    其他平台必须让全部包（含 py3-none-any）都走系统环境，
    否则纯 Python wheel 选得到而原生扩展缺失，会产生不完整的解压目录。
    """
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in _LINUX_MACHINES:
        return "linux", _LINUX_MACHINES[machine]
    if sys.platform == "win32" and machine == "amd64":
        return "win", _WINDOWS_MACHINES["amd64"]
    # macOS（macosx 版本标记复杂）、Win32/WinARM、其他 Linux 架构暂不内置
    return None, ()


def _machine_aliases() -> tuple[str, ...]:
    return _LINUX_MACHINES.get(platform.machine().lower(), (platform.machine().lower(),))


def _parse_wheel_name(filename: str) -> tuple[str, str, str, str, str] | None:
    """解析 wheel 文件名 → (分发名, 版本, python_tag, abi_tag, platform_tag)。"""
    if not filename.endswith(".whl"):
        return None
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return None
    name, version, py_tag, abi_tag, plat_tag = parts[0], parts[1], parts[2], parts[3], "-".join(parts[4:])
    return name, version, py_tag, abi_tag, plat_tag


def _platform_compatible(
    plat_tag: str,
    family: str | None,
    machine_aliases: tuple[str, ...],
) -> bool:
    if plat_tag == "any":
        return True
    if family == "linux":
        if "manylinux" not in plat_tag and "linux" not in plat_tag:
            return False
        return any(alias in plat_tag for alias in machine_aliases)
    if family == "win":
        # Windows wheel 的 platform_tag 即 win_amd64 / win32 / win_arm64
        return plat_tag in machine_aliases
    return False


def _cp_version() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def _python_score(py_tag: str, abi_tag: str) -> int:
    """返回与当前解释器的兼容评分，0 表示不兼容，越高越优先。"""
    vmaj, vmin = _cp_version()
    cur = f"cp{vmaj}{vmin}"
    if py_tag == "py3" and abi_tag == "none":
        return 100
    if abi_tag == "abi3" and py_tag.startswith("cp"):
        try:
            req_minor = int(py_tag[3:])
        except ValueError:
            return 0
        # cpXY-abi3 要求 CPython >= X.Y；满足前提下，要求越高（越接近当前）越优先
        if (vmaj, req_minor) <= (vmaj, vmin):
            return 200 + req_minor
        return 0
    if py_tag == cur and abi_tag == cur:
        return 300
    return 0


def select_wheels() -> list[Path]:
    """为当前解释器选出每个分发的最佳 wheel。"""
    family, aliases = _platform_spec()
    if family is None or not aliases or not WHEELS_DIR.is_dir():
        return []
    best: dict[str, tuple[int, str, Path]] = {}
    for wheel in WHEELS_DIR.glob("*.whl"):
        parsed = _parse_wheel_name(wheel.name)
        if parsed is None:
            continue
        dist, version, py_tag, abi_tag, plat_tag = parsed
        if not _platform_compatible(plat_tag, family, aliases):
            continue
        score = _python_score(py_tag, abi_tag)
        if score == 0:
            continue
        # 同分取较新版本（按版本号段比较）
        incumbent = best.get(dist)
        if incumbent is None or (score, _version_key(version)) > (incumbent[0], _version_key(incumbent[1])):
            best[dist] = (score, version, wheel)
    return [item[2] for item in best.values()]


def _version_key(version: str) -> tuple[int, ...]:
    key: list[int] = []
    for part in version.replace("-", ".").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        key.append(int(digits) if digits else 0)
    return tuple(key)


def _replace_dir(tmp: Path, target: Path) -> None:
    """原子化地用 tmp 替换 target；Windows 上应对杀软短暂占用进行重试。"""
    last_error: OSError | None = None
    for _ in range(5):
        try:
            if target.exists():
                shutil.rmtree(target)
            os.rename(tmp, target)
            return
        except OSError as exc:
            last_error = exc
            import time

            time.sleep(0.3)
    # 兜底：跨卷或 rename 持续失败时退回拷贝
    shutil.copytree(tmp, target, dirs_exist_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if last_error is not None and not target.exists():
        raise last_error


def _extract_wheel(wheel: Path, dest_root: Path) -> Path:
    """解压单个 wheel 到独立目录，完成后写 .ok 标记。"""
    target = dest_root / wheel.name[:-4]
    ok_marker = target / ".extracted"
    if ok_marker.is_file():
        return target
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as zf:
        # wheel 内的 .pyc / 旧字节码不随包分发，直接全部解压
        zf.extractall(tmp)
    _replace_dir(tmp, target)
    ok_marker.write_text("ok", encoding="utf-8")
    return target


def _promote_paths(paths: list[str]) -> None:
    """把 vendor 目录从 sys.path 末尾提到最前（仅在“补缺模式”仍失败时使用）。"""
    for path in reversed(paths):
        while path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


def ensure_vendor() -> list[str]:
    """确保内置依赖可用，返回已加入 sys.path 的目录列表。

    系统环境可完整导入 qqmusic 关键模块时不做任何解压；否则解压内置 wheels：
    先以 append（系统包优先、vendor 补缺）尝试；若系统存在版本不兼容的旧包
    遮蔽 vendor，再提升到 sys.path 最前重试。
    """
    if _try_probe() is None:
        return []

    if not WHEELS_DIR.is_dir():
        raise VendorError(
            "QQ音乐内置依赖缺失：插件目录中未找到 momotune_music/_vendor/wheels。"
            "若你是用 .patch 补丁或仅同步文本代码安装的，补丁不含二进制 wheel，"
            "请改用完整发行包 MomoTune-hd.zip 覆盖整个 MomoTune 目录后重启 Core；"
            "也可在 Core 使用的 Python 环境手动执行"
            "「pip install \"qqmusic-api-python>=0.7.2\"」。"
        )

    try:
        from gsuid_core.data_store import get_res_path

        extract_root = get_res_path() / "MomoTune" / "_vendor_lib"
    except Exception:
        extract_root = Path.home() / ".cache" / "MomoTune" / "_vendor_lib"
    extract_root.mkdir(parents=True, exist_ok=True)

    wheels = select_wheels()
    if not wheels:
        raise VendorError(
            f"QQ音乐内置依赖与当前平台不匹配（{_platform_desc()}）。"
            "请在 Core 使用的 Python 环境手动执行"
            "「pip install \"qqmusic-api-python>=0.7.2\"」后重启 Core。"
        )

    selected = sorted(w.name for w in wheels)
    manifest_path = extract_root / _MANIFEST_NAME
    need_extract = True
    if manifest_path.is_file():
        try:
            need_extract = json.loads(manifest_path.read_text(encoding="utf-8")) != selected
        except Exception:
            need_extract = True

    vendor_dirs: list[str] = []
    for wheel in wheels:
        try:
            path = str(_extract_wheel(wheel, extract_root))
        except (OSError, zipfile.BadZipFile) as exc:
            raise VendorError(
                f"QQ音乐内置依赖解压失败（{wheel.name}: {exc}）。"
                f"可删除目录 {extract_root} 后重启 Core 重新解压，或手动 pip 安装。"
            ) from exc
        vendor_dirs.append(path)
        if path not in sys.path:
            # append：系统 site-packages 优先，vendor 仅补缺
            sys.path.append(path)

    if need_extract:
        manifest_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    # 补缺模式再探；仍失败说明系统里有版本不兼容的同名包在遮蔽 vendor
    exc = _try_probe()
    if exc is None:
        return vendor_dirs

    _promote_paths(vendor_dirs)
    exc = _try_probe()
    if exc is None:
        return vendor_dirs

    raise VendorError(
        "QQ音乐内置依赖加载失败：系统环境与内置 wheels 均无法正常导入"
        f"（{type(exc).__name__}: {exc}；平台 {_platform_desc()}）。"
        "建议在 Core 使用的 Python 环境执行"
        "「pip install -U \"qqmusic-api-python>=0.7.2\"」修复冲突，或把上述完整报错反馈给插件作者。"
    )
