"""判断一节课是否属于某个用户的课表。

老师经常改场次名（比如 "TME" 改成 "CS/TME"），只按"课程名+场次名完全一致"匹配会漏课。
这里按以下规则判断每节课：

- selected   自动算进课表：
    * 和用户勾选的完全一致；或
    * 同一门课（课程代码相同，比如 UM4IN101），场次名拆开后有一部分和用户选的一致，
      例如选了 "TME"，"CS/TME" 也算；没写组号的场次（"TME"）对所有组都算（选了 "TME3" 也包括）。
- hidden     明确是别的组/别的语言版本，不显示：
    * 例如选了 "TD3"，"TD1" 就是别的组；选了英文版 "Cours (EN)"，法语版 "Cours" 就不显示。
- suggested  判断不了的新场次（新考试、补课、改了完全不同的名字……），
             网页日历上用虚线框提示，由用户决定"加入"还是"忽略"。

只有用户已经选过的课程（同一课程代码）才会出现 suggested，其他课程一律不显示。
"""

from __future__ import annotations

import re

_UE_RE = re.compile(r"^([A-Za-z]{2,}\d[A-Za-z0-9]*)-(.+)$")
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_COURS_SYNONYMS = {"cs", "cm", "cours", "amphi"}
_LANG_EN = {"en", "eng", "english", "anglais", "ang"}
# 这些场次后面的数字是"第几次考试"，不是组号，不能当成"别的组"
_NON_GROUP_BASES = {"er", "examenr", "examen", "exam", "partiel", "ds", "cc"}


def split_course_key(course_key: str):
    """'UM4IN101-VLSI1' -> ('UM4IN101', 'vlsi', '1')；没有课程代码的返回 (None, 原名小写, '')"""
    m = _UE_RE.match(course_key or "")
    if not m:
        return None, (course_key or "").strip().lower(), ""
    name = m.group(2).strip().lower()
    nm = re.match(r"^(.*?)(\d*)$", name)
    return m.group(1).upper(), nm.group(1), nm.group(2)


def _base_num(token: str):
    m = re.match(r"^(.*?)(\d*)$", token)
    return m.group(1), m.group(2)


def parse_session(session: str):
    """'CS/TME' -> ('fr', {('cours',''), ('tme','')})；'TD1_English' -> ('en', {('td','1')})"""
    lang = "fr"
    tokens = set()
    for t in _TOKEN_SPLIT.split((session or "").lower()):
        if not t:
            continue
        if t in _LANG_EN:
            lang = "en"
            continue
        for suffix in ("anglais", "english"):
            if t.endswith(suffix) and len(t) > len(suffix):
                t = t[: -len(suffix)]
                lang = "en"
        if t in _COURS_SYNONYMS:
            t = "cours"
        tokens.add(_base_num(t))
    return lang, tokens


def courses_compatible(ck_a: str, ck_b: str) -> bool:
    """同一门课的不同写法：'UM4IN101-VLSI1' 和 'UM4IN101-VLSI' 兼容；'...-VLSI1' 和 '...-VLSI2' 不兼容"""
    if ck_a == ck_b:
        return True
    ue_a, base_a, num_a = split_course_key(ck_a)
    ue_b, base_b, num_b = split_course_key(ck_b)
    if ue_a is None or ue_a != ue_b:
        return False
    if base_a != base_b:
        return True  # 同一课程代码下名字写法不同（缩写、改名），仍视为同一门课
    return not num_a or not num_b or num_a == num_b


def classify(course_key: str, session_type: str, selection: set, dismissed: set = frozenset()) -> str:
    """selection / dismissed: {(course_key, session_key_lower)}。返回 'selected' / 'suggested' / 'hidden'"""
    key = (course_key, (session_type or "").strip().lower())
    if key in selection:
        return "selected"
    if key in dismissed:
        return "hidden"

    # 课程名带编号（VLSI2），而用户选的是同一课程的另一个编号（VLSI1）→ 别的组
    ue, base, num = split_course_key(course_key)
    if ue and num and any(
        u == ue and b == base and n and n != num
        for u, b, n in (split_course_key(ck) for ck, _ in selection)
    ):
        return "hidden"

    related = [s for ck, s in selection if courses_compatible(ck, course_key)]
    if not related:
        return "hidden"  # 用户没选过这门课

    ev_lang, ev_tokens = parse_session(session_type)
    same_lang, other_lang = set(), set()
    for s in related:
        lang, toks = parse_session(s)
        (same_lang if lang == ev_lang else other_lang).update(toks)

    for b, n in ev_tokens:
        for sb, sn in same_lang:
            if b == sb and (n == sn or n == ""):
                return "selected"

    if ev_tokens:
        def other_group(b, n):
            return (n and b not in _NON_GROUP_BASES
                    and any(sb == b and sn and sn != n for sb, sn in same_lang))

        if all(other_group(b, n) for b, n in ev_tokens):
            return "hidden"  # 明确是别的组
        if other_lang and all(any(b == sb for sb, _ in other_lang) for b, _ in ev_tokens) \
                and not any(b == sb for b, _ in ev_tokens for sb, _ in same_lang):
            return "hidden"  # 用户选的是另一种语言的版本
    return "suggested"


def ue_codes(selection: set) -> set:
    return {ue for ck, _ in selection for ue in [split_course_key(ck)[0]] if ue}
