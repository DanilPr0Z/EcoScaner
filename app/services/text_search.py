"""Примитивы текстового поиска по справочнику.

Своя реализация вместо SQL LIKE по трём причинам:
  * у SQLite регистронезависимое сравнение работает только для латиницы —
    «бутылка» не нашла бы «Бутылка из-под воды»;
  * нужны словоформы: «бутылки», «бутылке», «бутылку» должны находить «бутылка»;
  * нужен ранг, чтобы совпадение в названии было выше совпадения в описании.

Полноценной морфологии здесь нет и не нужно: справочник — полсотни строк,
запрос отрабатывает за доли миллисекунды.
"""

from __future__ import annotations

import re

#: Слова короче этого не считаем за основу слова — иначе «ка» матчит всё подряд.
MIN_STEM = 4

_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)


def fold(text: str) -> str:
    """Регистр и «ё» → «е», чтобы «Ёмкость» находилась по «емкость»."""
    return text.lower().replace("ё", "е")


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(word for word in _SPLIT_RE.split(fold(text)) if word)


def _common_prefix(a: str, b: str) -> int:
    length = 0
    for char_a, char_b in zip(a, b):
        if char_a != char_b:
            break
        length += 1
    return length


#: Какую долю длинного слова должна занимать общая основа. Одного лишь
#: «совпало 4 первых буквы» мало: у «метан» и «металл» это 4 из 6, и запрос
#: про метан приводил в категорию «Металл».
_STEM_RATIO = 0.75


def _same_stem(token: str, word: str) -> bool:
    """Различаются ли слова только окончанием: «бутылки» и «бутылка»."""
    if len(token) < MIN_STEM or len(word) < MIN_STEM:
        return False
    prefix = _common_prefix(token, word)
    return prefix >= MIN_STEM and prefix / max(len(token), len(word)) >= _STEM_RATIO


def _within_one_edit(a: str, b: str) -> bool:
    """Отличаются ли строки не больше чем на одну вставку, удаление или замену."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a

    i = j = 0
    edited = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if edited:
            return False
        edited = True
        if len(a) == len(b):
            i += 1
        j += 1
    return True


def score_token(token: str, word: str) -> float:
    """Насколько слово из текста отвечает на слово из запроса: 0.0 — никак, 1.0 — точно."""
    if token == word:
        return 1.0
    if word.startswith(token):
        # «бутыл» → «бутылка»: пользователь ещё не дописал слово
        return 0.85
    if len(word) >= MIN_STEM and token.startswith(word):
        return 0.7
    if _same_stem(token, word):
        # «бутылки» и «бутылка» — по сути одно слово, разница только в окончании
        return 0.8
    if len(token) >= 3 and token in word:
        return 0.4
    if len(token) >= 5 and _within_one_edit(token, word):
        # опечатка на один символ: «бутулка»
        return 0.3
    return 0.0


#: Насколько дешевле совпадение не в первом слове. «Бутылка из-под воды» —
#: это про бутылку, а «Крышка от бутылки» — про крышку, и по запросу «бутылки»
#: первой должна идти бутылка.
_TAIL_PENALTY = 0.75


def score_text(token: str, words: tuple[str, ...]) -> float:
    """Лучшее совпадение слова запроса с любым словом текста.

    Совпадение в первом слове ценится выше: в коротких названиях справочника
    первое слово — это сам предмет, остальные уточняют.
    """
    best = 0.0
    for index, word in enumerate(words):
        quality = score_token(token, word)
        if not quality:
            continue
        best = max(best, quality if index == 0 else quality * _TAIL_PENALTY)
    return best
