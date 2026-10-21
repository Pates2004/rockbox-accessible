import unittest
from pathlib import Path
import re

from test_polish_translation import parse_language


ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = {
    "LANG_DICE_TITLE": ("Dice", "Kości"),
    "LANG_DICE_ROLL": ("Roll dice", "Rzuć kośćmi"),
    "LANG_DICE_COUNT": ("Number of dice", "Liczba kości"),
    "LANG_DICE_SIDES": ("Number of sides", "Liczba ścianek"),
    "LANG_DICE_RESULTS": ("Results", "Wyniki"),
    "LANG_DICE_TOTAL": ("Total", "Suma"),
    "LANG_CALCULATOR_MEMORY_RECALL": ("Recall memory", "Odczytaj pamięć"),
    "LANG_CALCULATOR_MEMORY_ADD": ("Add to memory", "Dodaj do pamięci"),
    "LANG_CALCULATOR_SCIENTIFIC": ("Scientific functions", "Funkcje naukowe"),
    "LANG_CALCULATOR_BASIC": ("Basic functions", "Funkcje podstawowe"),
    "LANG_CALCULATOR_CLEAR_ENTRY": ("Clear entry", "Wyczyść wpis"),
    "LANG_CALCULATOR_DIVIDE": ("Divide", "Podziel"),
    "LANG_CALCULATOR_SQRT": ("Square root", "Pierwiastek kwadratowy"),
    "LANG_CALCULATOR_MULTIPLY": ("Multiply", "Pomnóż"),
    "LANG_CALCULATOR_SQUARE": ("Square", "Podnieś do kwadratu"),
    "LANG_CALCULATOR_RECIPROCAL": ("Reciprocal", "Odwrotność"),
    "LANG_CALCULATOR_SIGN": ("Change sign", "Zmień znak"),
    "LANG_CALCULATOR_DECIMAL": ("Decimal separator", "Separator dziesiętny"),
    "LANG_CALCULATOR_EQUALS": ("Equals", "Równa się"),
    "LANG_CALCULATOR_FACTORIAL": ("Factorial", "Silnia"),
    "LANG_CALCULATOR_PI": ("Pi", "Pi"),
    "LANG_CALCULATOR_SINE": ("Sine", "Sinus"),
    "LANG_CALCULATOR_ASINE": ("Arc sine", "Arcus sinus"),
    "LANG_CALCULATOR_COSINE": ("Cosine", "Cosinus"),
    "LANG_CALCULATOR_ACOSINE": ("Arc cosine", "Arcus cosinus"),
    "LANG_CALCULATOR_TANGENT": ("Tangent", "Tangens"),
    "LANG_CALCULATOR_ATANGENT": ("Arc tangent", "Arcus tangens"),
    "LANG_CALCULATOR_LN": ("Natural logarithm", "Logarytm naturalny"),
    "LANG_CALCULATOR_EXP": ("Exponential", "Funkcja wykładnicza"),
    "LANG_CALCULATOR_LOG": ("Base ten logarithm", "Logarytm dziesiętny"),
    "LANG_CALCULATOR_POWER": ("Raise to a power", "Podnieś do potęgi"),
    "LANG_CALCULATOR_RESULT": ("Result", "Wynik"),
    "LANG_CALCULATOR_EXPONENT": ("Times ten to the power", "Razy dziesięć do potęgi"),
    "LANG_STOPWATCH_LAP": ("Lap", "Okrążenie"),
    "LANG_STOPWATCH_SPLIT": ("Split time", "Czas okrążenia"),
    "LANG_METRONOME_TEMPO": ("Tempo, beats per minute", "Tempo, uderzenia na minutę"),
    "LANG_METRONOME_METER": ("Meter", "Metrum"),
    "LANG_METRONOME_PART": ("Part", "Część"),
    "LANG_METRONOME_BAR": ("Bar", "Takt"),
    "LANG_PLUGIN_STATS_IMAGES": ("Images", "Obrazy"),
    "LANG_PLUGIN_STATS_VIDEOS": ("Videos", "Filmy"),
    "LANG_PLUGIN_STATS_MAX_FILES": ("Maximum files in one directory", "Najwięcej plików w jednym katalogu"),
    "LANG_ALARMCLOCK": ("Alarm clock", "Budzik"),
    "LANG_ALARMCLOCK_ARMED": ("Alarm armed", "Budzik włączony"),
    "LANG_ALARMCLOCK_WAKEUP": ("Wake up", "Pobudka"),
    "LANG_CHESSCLOCK": ("Chess clock", "Zegar szachowy"),
    "LANG_CHESSCLOCK_PLAYER": ("Player", "Gracz"),
    "LANG_CHESSCLOCK_DELETE_PLAYER": ("Delete player", "Usuń gracza"),
    "LANG_CHESSCLOCK_RESTART_ROUND": ("Restart round", "Rozpocznij rundę od nowa"),
    "LANG_CHESSCLOCK_TOTAL_TIME": ("Total time", "Łączny czas"),
    "LANG_CHESSCLOCK_MAX_ROUND_TIME": ("Maximum round time", "Maksymalny czas rundy"),
    "LANG_CHESSCLOCK_ROUND_TIME": ("Round time", "Czas rundy"),
    "LANG_CHESSCLOCK_SET_TOTAL_TIME": ("Set total time", "Ustaw łączny czas"),
    "LANG_CHESSCLOCK_SET_ROUND_TIME": ("Set round time", "Ustaw czas rundy"),
    "LANG_CHESSCLOCK_ROUND_FINISHED": ("Round finished", "Koniec rundy"),
}


class PluginTranslationTests(unittest.TestCase):
    def test_complete_english_and_polish_voice_and_display(self):
        languages = [parse_language((ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8"))
                     for language in ("english", "polski")]
        for identifier, translations in TRANSLATIONS.items():
            for index, phrases in enumerate(languages):
                with self.subTest(identifier=identifier, language=index):
                    self.assertEqual(phrases[identifier]["source"], {"*": f'"{translations[0]}"'})
                    for section in ("dest", "voice"):
                        self.assertEqual(phrases[identifier][section], {"*": f'"{translations[index]}"'})

    def test_all_plugin_language_references_exist(self):
        phrases = parse_language((ROOT / "apps/lang/english.lang").read_text(encoding="utf-8"))
        changed = ("calculator.c", "stopwatch.c", "metronome.c", "calendar.c", "stats.c",
                   "text_editor.c", "dict.c", "chessclock.c", "alarmclock.c", "countdown_timer.c",
                   "dice.c", "random_folder_advance_config.c", "shortcuts/shortcuts_view.c")
        identifiers = set()
        for name in changed:
            identifiers.update(re.findall(r"\bLANG_[A-Z0-9_]+\b",
                (ROOT / "apps/plugins" / name).read_text(encoding="utf-8")))
        self.assertFalse(identifiers - phrases.keys())
        self.assertFalse(TRANSLATIONS.keys() - identifiers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
