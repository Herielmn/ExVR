from __future__ import annotations

from ctypes import windll

import utils.globals as g

LANGUAGE_SYSTEM = "system"
LANGUAGE_EN = "en"
LANGUAGE_ZH_CN = "zh_CN"

LANGUAGE_OPTIONS = [
    (LANGUAGE_SYSTEM, "Auto"),
    (LANGUAGE_EN, "English"),
    (LANGUAGE_ZH_CN, "简体中文"),
]

LANG_CHINESE = 0x04

_system_language: str | None = None


def system_language():
    global _system_language
    if _system_language is None:
        try:
            language_id = windll.kernel32.GetUserDefaultUILanguage()
        except Exception:
            language_id = 0
        _system_language = (LANGUAGE_ZH_CN if (language_id & 0x3FF) == LANG_CHINESE
                            else LANGUAGE_EN)
    return _system_language


def effective_language(language):
    if language in (LANGUAGE_EN, LANGUAGE_ZH_CN):
        return language
    return system_language()


def current_language():
    setting = g.config.get("Setting") if isinstance(g.config, dict) else None
    if isinstance(setting, dict):
        return setting.get("language", LANGUAGE_SYSTEM)
    return LANGUAGE_SYSTEM


def current_effective_language():
    return effective_language(current_language())


def bilingual(english: str, chinese: str) -> str:
    return chinese if current_effective_language() == LANGUAGE_ZH_CN else english
