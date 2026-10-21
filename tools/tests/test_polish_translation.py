import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = ("source", "dest", "voice")
PLACEHOLDER = re.compile(
    r"%(?:%|(?:\d+\$)?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn])"
)
ENTRY = re.compile(r'([^\s:]+):\s*("(?:\\.|[^"\\])*"|none|deprecated|deprecate)')
FIXES = (
    ("LANG_OFF", "*", ("dest",), "Wył·", "Wył."),
    (
        "LANG_CHANNEL_LEFTRIGHT", "recording", ("voice",),
        "Monofoncziny lewy plus prawy", "Monofoniczny lewy plus prawy",
    ),
    (
        "LANG_EQUALIZER_GAIN", "*", ("voice",),
        "Ustawnienia podstawowe korektora", "Ustawienia podstawowe korektora",
    ),
    (
        "LANG_HEADPHONE_UNPLUG", "headphone_detection", ("dest", "voice"),
        "Wstrzymanie po odłączaniu słuchawek", "Wstrzymanie po odłączeniu słuchawek",
    ),
    (
        "LANG_SORT_CASE", "*", ("dest",),
        "Sortuj uwzgl. wielkość liter", "Sortuj, uwzgl. wielkość liter",
    ),
    (
        "LANG_SORT_CASE", "*", ("voice",),
        "Sortuj uwzględniając wielkość liter", "Sortuj, uwzględniając wielkość liter",
    ),
    ("LANG_SORT_DATE", "*", ("dest",), "Od najstarczego", "Od najstarszego"),
    (
        "LANG_SORT_DATE", "*", ("voice",),
        "Według daty od najstarczego", "Według daty od najstarszego",
    ),
    (
        "LANG_LISTACCEL_START_DELAY", "*", ("dest", "voice"),
        "Opóźnienie przyspiesznie przy przeglądaniu list",
        "Opóźnienie przyspieszenia przy przeglądaniu list",
    ),
    (
        "LANG_FM_US", "radio", ("voice",),
        "stany zjednoczone i kanada", "Stany Zjednoczone i Kanada",
    ),
    (
        "LANG_QUEUE_LAST", "*", ("dest", "voice"),
        "Ostanie do kolejki", "Ostatnie do kolejki",
    ),
    (
        "LANG_MENU_SHOW_ID3_INFO", "*", ("dest",),
        "Pokaż informacje utworu", "Pokaż informacje o utworze",
    ),
    (
        "LANG_MENU_SHOW_ID3_INFO", "*", ("voice",),
        "Pokaż informacje dla utowru", "Pokaż informacje o utworze",
    ),
    ("VOICE_BILLION", "*", ("voice",), "bilion", "miliard"),
    ("VOICE_KHZ", "*", ("voice",), "kilohercy", "kiloherców"),
    (
        "VOICE_MILLIAMPHOURS", "*", ("voice",),
        "miliampero godzin", "miliamperogodzin",
    ),
    ("VOICE_HERTZ", "*", ("voice",), "hercy", "herców"),
    (
        "LANG_AUTORESUME_AUTOMATIC", "*", ("dest",),
        "Wznów przy automatcznej zmianie utworu",
        "Wznów przy automatycznej zmianie utworu",
    ),
    (
        "LANG_SOFTLOCK_SELECTIVE", "*", ("dest", "voice"),
        "Zaawansowana blokada klawszy", "Zaawansowana blokada klawiszy",
    ),
    (
        "LANG_CLEAR_ALL_RESUMES", "*", ("dest", "voice"),
        "Wyczyść wszystko wznawia", "Wyczyść wszystkie wznowienia",
    ),
    (
        "LANG_FILTER_SHORT_SHARP", "filter_roll_off", ("voice",),
        "Krutki ostry", "Krótki ostry",
    ),
    (
        "LANG_FILTER_SHORT_SLOW", "filter_roll_off", ("voice",),
        "Krutki wolny", "Krótki wolny",
    ),
    (
        "LANG_COUNTDOWN_TIMER_OVERTIME", "*", ("voice",),
        "Przedłużno", "Przedłużono",
    ),
) + tuple(
    (
        "LANG_DISK_FULL", selector, ("dest",),
        f"Pamięć jest pełna. Wciśnij {button} żeby kontynuować.",
        f"Pamięć jest pełna. Wciśnij {button}, żeby kontynuować.",
    )
    for selector, button in (
        ("iaudiom5,iaudiox5", "POWER"),
        ("iriverh100,iriverh120,iriverh300", "STOP"),
        ("recording", "OFF"),
        ("samsungyh*", "LEFT"),
        ("sansac200*,sansae200*,vibe500", "PREV"),
    )
)


FOLLOWUP_FIXES = (
    ("LANG_FORCE", "*", ("dest", "voice"), "Moc", "Wymuś"),
    ("LANG_ACTION_SEEK", "*", ("dest", "voice"), "Zwolnij przewijanie", "Wyjątek: przewijanie"),
    ("LANG_ACTION_SKIP", "*", ("dest", "voice"), "Zwolnij pomijanie", "Wyjątek: pomijanie"),
    ("LANG_ACTION_PLAY", "*", ("dest", "voice"), "Zwolnij odtwarzanie", "Wyjątek: odtwarzanie"),
    ("LANG_ACTION_VOLUME", "*", ("dest", "voice"), "Zwolnij głośność", "Wyjątek: głośność"),
    (
        "LANG_EXT_ONLY_VIEW_ALL", "*", ("dest", "voice"),
        "Tylko gdy wyświetlane wszystkie typy plików",
        "Tylko gdy wyświetlane są wszystkie typy plików",
    ),
    (
        "LANG_ACCESSORY_SUPPLY", "accessory_supply", ("dest", "voice"),
        "Zasilanie Akcesorium", "Zasilanie akcesorium",
    ),
    ("VOICE_QUICKSCREEN", "*", ("voice",), "Szybki Dostęp", "Szybki dostęp"),
    (
        "LANG_HW_EQ_GAIN", "gigabeats,samsungypr1", ("voice",),
        "pasma wzm.", "Wzmocnienie pasma",
    ),
    (
        "LANG_TTS_PUNCTUATION_SOME", "*", ("dest", "voice"),
        "Wybrane", "Niektóre",
    ),
)
TTS_TRANSLATIONS = {
    "LANG_TTS": ("eSpeak settings", "Ustawienia eSpeak"),
    "LANG_TTS_ENABLED": ("Speech synthesis", "Synteza mowy"),
    "LANG_TTS_LANGUAGE": ("Speech language", "Język syntezy mowy"),
    "LANG_TTS_VARIANT": ("Voice variant", "Wariant głosu"),
    "LANG_TTS_RATE": ("Speech rate", "Tempo mowy"),
    "LANG_TTS_PITCH": ("Pitch", "Wysokość głosu"),
    "LANG_TTS_VOLUME": ("Speech volume", "Głośność mowy"),
    "LANG_TTS_RANGE": ("Modulation", "Modulacja"),
    "LANG_TTS_WORDGAP": ("Word gap", "Odstęp między słowami"),
    "LANG_TTS_ERROR": ("Speech synthesis unavailable", "Synteza mowy niedostępna"),
    "LANG_TTS_READER": ("Read text", "Czytaj tekst"),
    "LANG_TTS_READING": ("Reading", "Czytanie"),
    "LANG_TTS_PAUSED": ("Paused", "Wstrzymano"),
    "LANG_TTS_FINISHED": ("End of text", "Koniec tekstu"),
    "LANG_TTS_INVALID_TEXT": ("Unsupported text encoding", "Nieobsługiwane kodowanie tekstu"),
    "LANG_TTS_DEFAULT_VARIANT": ("Default variant", "Wariant domyślny"),
    "LANG_TTS_SYSTEM": ("Follow system language", "Zgodny z systemem"),
    "LANG_TTS_RATE_SCALE": ("Speech rate scale", "Skala tempa mowy"),
    "LANG_TTS_RATE_PERCENT": ("Percent", "Procenty"),
    "LANG_TTS_RATE_WPM": ("WPM", "WPM"),
    "LANG_TTS_RATE_WPM_UNIT": ("words/min", "słów/min"),
    "LANG_TTS_PUNCTUATION": ("Punctuation", "Interpunkcja"),
    "LANG_TTS_PUNCTUATION_NONE": ("None", "Brak"),
    "LANG_TTS_PUNCTUATION_SOME": ("Some", "Niektóre"),
    "LANG_TTS_PUNCTUATION_MOST": ("Most", "Większość"),
    "LANG_TTS_PUNCTUATION_ALL": ("All", "Wszystkie"),
    "LANG_TTS_READER_SETTINGS": ("Text reading settings", "Ustawienia czytania tekstu"),
    "LANG_TTS_READER_UNIT": ("Navigation unit", "Zakres nawigacji"),
    "LANG_TTS_READER_PAGE_LINES": ("Lines per page", "Wiersze na stronie"),
    "LANG_TTS_UNIT_CHARACTER": ("Characters", "Znaki"),
    "LANG_TTS_UNIT_WORD": ("Words", "Słowa"),
    "LANG_TTS_UNIT_LINE": ("Lines", "Wiersze"),
    "LANG_TTS_UNIT_PARAGRAPH": ("Paragraphs", "Akapity"),
    "LANG_TTS_UNIT_PAGE": ("Pages", "Strony"),
    "LANG_TTS_NEWLINE": ("New line", "Nowy wiersz"),
    "LANG_TTS_DUCKING": ("Audio ducking", "Przyciszanie audio"),
    "LANG_TTS_DUCKING_LEVEL": ("Audio level during speech", "Poziom audio podczas mowy"),
    "LANG_TTS_RECORDER_UNAVAILABLE": ("Recording is unavailable in the simulator",
                                      "Nagrywanie jest niedostępne w symulatorze"),
    "LANG_TTS_READER_MENU": ("Text options", "Opcje tekstu"),
    "LANG_TTS_RESUME": ("Resume reading", "Wznów czytanie"),
    "LANG_TTS_BEGINNING": ("Go to beginning", "Przejdź na początek"),
    "LANG_TTS_END": ("Go to end", "Przejdź na koniec"),
    "LANG_TTS_BYTES": ("bytes", "bajtów"),
    "LANG_TTS_TEXT_BOOKMARK": ("Text bookmark", "Zakładka tekstowa"),
    "LANG_TTS_POSITION": ("Position", "Pozycja"),
    "LANG_TTS_BOOKMARK_CHANGED": ("The text has changed or the bookmark is invalid",
                                  "Tekst zmienił się lub zakładka jest nieprawidłowa"),
    "LANG_TTS_BOOKMARK_LOCAL_ONLY": (
        "Bookmark saved, but recent bookmarks could not be updated",
        "Zakładka zapisana, ale nie udało się zaktualizować ostatnich zakładek",
    ),
}
TTS_VOICE_OVERRIDES = {
    "LANG_TTS_RATE_WPM": ("Words per minute", "Słowa na minutę"),
    "LANG_TTS_RATE_WPM_UNIT": ("Words per minute", "Słów na minutę"),
}
MENU_TRANSLATIONS = (
    ("LANG_LCD_MENU", "*", "LCD Settings", "Ustawienia wyświetlacza"),
    (
        "LANG_LCD_REMOTE_MENU", "remote", "Remote-LCD Settings",
        "Ustawienia wyświetlacza pilota",
    ),
    ("LANG_VOICE_MENU", "*", "Voice Menus", "Używaj plików głosowych do czytania interfejsu"),
    (
        "LANG_DIRCACHE_ENABLE", "dircache", "Directory Cache",
        "Pamięć podręczna folderów",
    ),
    ("LANG_USB_DAC", "usbdac", "USB-DAC", "DAC USB"),
    ("LANG_USB_DAC_ACTIVE", "usbdac", "USB-DAC Active", "DAC USB aktywny"),
)
CATALOG_FIXES = (
    (
        "LANG_LCD_MENU", "*", ("dest",),
        "Ustawienia LCD", "Ustawienia wyświetlacza",
    ),
    (
        "LANG_LCD_MENU", "*", ("voice",),
        "Ustawienia wyświetlacza el si di", "Ustawienia wyświetlacza",
    ),
    (
        "LANG_LCD_REMOTE_MENU", "remote", ("dest",),
        "Ustawienia pilota LCD", "Ustawienia wyświetlacza pilota",
    ),
    (
        "LANG_LCD_REMOTE_MENU", "remote", ("voice",),
        "Ustawienia wyświetlacza pilota el si di", "Ustawienia wyświetlacza pilota",
    ),
    ("LANG_VOICE_MENU", "*", ("dest", "voice"), "Menu głosowe", "Używaj plików głosowych do czytania interfejsu"),
    (
        "LANG_DIRCACHE_ENABLE", "dircache", ("dest", "voice"),
        "Pamięć podręczna katalogów", "Pamięć podręczna folderów",
    ),
    ("LANG_USB_DAC", "usbdac", ("voice",), "dak uesbe", "DAC USB"),
    (
        "LANG_USB_DAC_ACTIVE", "usbdac", ("voice",),
        "dak uesbe aktywny", "DAC USB aktywny",
    ),
    (
        "LANG_PITCH_UP_SEMITONE", "pitchscreen", ("dest",),
        "Wzmocnienie półtonu", "Podwyższenie o pół tonu",
    ),
    (
        "LANG_PITCH_DOWN_SEMITONE", "pitchscreen", ("dest",),
        "Obniżenie półtonu", "Obniżenie o pół tonu",
    ),
    (
        "VOICE_PITCH_TIMESTRETCH_MODE", "pitchscreen", ("voice",),
        "Przedział czasu", "Rozciąganie czasu",
    ),
)


def parse_language(text):
    text = re.sub(r"(?m)^[ \t]*#.*$", "", text)
    phrase_pattern = re.compile(r"<phrase>\s*(.*?)\s*</phrase>", re.DOTALL)
    phrases = {}
    for match in phrase_pattern.finditer(text):
        block = match.group(1)
        identifier = re.search(r"(?m)^[ \t]*id: (\w+)[ \t]*$", block)
        if identifier is None:
            raise ValueError("Missing phrase identifier")
        identifier = identifier.group(1)
        if identifier in phrases:
            raise ValueError(f"Duplicate phrase: {identifier}")
        phrase = {}
        for section in SECTIONS:
            section_pattern = re.compile(
                rf"<{section}>\s*(.*?)\s*</{section}>", re.DOTALL
            )
            bodies = section_pattern.findall(block)
            if len(bodies) != 1:
                raise ValueError(f"Expected one {section} in {identifier}")
            entries = {}
            for line in bodies[0].splitlines():
                entry = ENTRY.fullmatch(line.strip())
                if entry is None:
                    raise ValueError(f"Invalid entry in {identifier}/{section}: {line}")
                selector, value = entry.groups()
                if selector in entries:
                    raise ValueError(f"Duplicate selector in {identifier}/{section}")
                entries[selector] = value
            if "*" not in entries:
                raise ValueError(f"Missing default in {identifier}/{section}")
            phrase[section] = entries
            block = section_pattern.sub("", block)
        metadata = dict(re.findall(r"(?m)^[ \t]*(id|desc|user):[ \t]*(.*)$", block))
        if set(metadata) != {"id", "desc", "user"}:
            raise ValueError(f"Incomplete metadata in {identifier}")
        block = re.sub(r"(?m)^[ \t]*(id|desc|user):.*$", "", block)
        if block.strip():
            raise ValueError(f"Unexpected phrase content in {identifier}: {block}")
        phrase["user"] = metadata["user"]
        phrases[identifier] = phrase
    if phrase_pattern.sub("", text).strip():
        raise ValueError("Unexpected content outside phrases")
    return phrases


class LanguageParserTests(unittest.TestCase):
    def setUp(self):
        sections = "".join(
            f'  <{section}>\n    *: none\n    feature: "Text"\n  </{section}>\n'
            for section in SECTIONS
        )
        self.fixture = (
            "<phrase>\n  id: LANG_FIXTURE\n  desc: parser fixture\n"
            f"  user: core\n{sections}</phrase>\n"
        )

    def test_complete_conditional_sections(self):
        phrase = parse_language(self.fixture)["LANG_FIXTURE"]
        self.assertEqual("core", phrase["user"])
        for section in SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    {"*": "none", "feature": '"Text"'}, phrase[section],
                )

    def test_rejects_missing_or_duplicate_sections(self):
        for section in SECTIONS:
            section_block = re.search(
                rf"  <{section}>.*?</{section}>\n", self.fixture, re.DOTALL,
            ).group(0)
            for replacement in ("", section_block * 2):
                with self.subTest(section=section, replacement=replacement):
                    with self.assertRaisesRegex(ValueError, f"Expected one {section}"):
                        parse_language(self.fixture.replace(section_block, replacement))

    def test_rejects_missing_default_or_duplicate_selectors(self):
        for section in SECTIONS:
            opening = f"  <{section}>\n    *: none\n"
            for replacement, error in (
                (f"  <{section}>\n", "Missing default"),
                (opening + "    *: none\n", "Duplicate selector"),
            ):
                with self.subTest(section=section, error=error):
                    with self.assertRaisesRegex(ValueError, error):
                        parse_language(self.fixture.replace(opening, replacement))

    def test_rejects_duplicate_or_incomplete_phrases(self):
        for text, error in (
            (self.fixture * 2, "Duplicate phrase"),
            (self.fixture.replace("  id: LANG_FIXTURE\n", ""), "Missing phrase identifier"),
            (self.fixture.replace("  user: core\n", ""), "Incomplete metadata"),
            (self.fixture.replace('feature: "Text"', "feature: Text", 1), "Invalid entry"),
            (self.fixture.replace("</phrase>", ""), "Unexpected content outside phrases"),
            (self.fixture + "unexpected\n", "Unexpected content outside phrases"),
        ):
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, error):
                    parse_language(text)


class PolishTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.english = parse_language(
            (ROOT / "apps/lang/english.lang").read_text(encoding="utf-8")
        )
        cls.polish = parse_language(
            (ROOT / "apps/lang/polski.lang").read_text(encoding="utf-8")
        )

    def test_identifier_parity(self):
        self.assertGreater(len(self.polish), 1000)
        self.assertEqual(self.english.keys(), self.polish.keys())

    def test_source_and_selector_parity(self):
        for identifier, phrase in self.polish.items():
            with self.subTest(identifier=identifier):
                reference = self.english[identifier]
                self.assertEqual(reference["user"], phrase["user"])
                self.assertEqual(reference["source"], phrase["source"])
                for section in SECTIONS:
                    self.assertEqual(reference[section].keys(), phrase[section].keys())

    def test_placeholder_parity(self):
        for identifier, phrase in self.polish.items():
            for section in SECTIONS:
                for selector, value in phrase[section].items():
                    with self.subTest(id=identifier, section=section, selector=selector):
                        reference = self.english[identifier][section][selector]
                        self.assertEqual(
                            PLACEHOLDER.findall(reference), PLACEHOLDER.findall(value)
                        )

    def test_nontext_values_preserved(self):
        for identifier, phrase in self.polish.items():
            for section in SECTIONS:
                for selector, value in phrase[section].items():
                    with self.subTest(id=identifier, section=section, selector=selector):
                        reference = self.english[identifier][section][selector]
                        if not reference.startswith('"') or not value.startswith('"'):
                            self.assertEqual(reference, value)

    def test_confirmed_spelling_and_grammar_fixes(self):
        for identifier, selector, sections, original, corrected in (
            FIXES + FOLLOWUP_FIXES + CATALOG_FIXES
        ):
            for section in sections:
                with self.subTest(id=identifier, section=section, selector=selector):
                    self.assertNotEqual(original, corrected)
                    self.assertEqual(
                        f'"{corrected}"', self.polish[identifier][section][selector]
                    )
                    self.assertEqual(
                        PLACEHOLDER.findall(original), PLACEHOLDER.findall(corrected)
                    )

    def test_requested_menu_display_voice_and_source(self):
        for identifier, selector, source, translated in MENU_TRANSLATIONS:
            expected_source = {selector: f'"{source}"'}
            expected_translation = {selector: f'"{translated}"'}
            if selector != "*":
                expected_source = {"*": "none", **expected_source}
                expected_translation = {"*": "none", **expected_translation}
            with self.subTest(identifier=identifier):
                self.assertEqual(expected_source, self.polish[identifier]["source"])
                for section in ("dest", "voice"):
                    self.assertEqual(expected_translation, self.polish[identifier][section])

    def test_pitch_labels_preserve_display_and_voice_silence(self):
        for identifier in ("LANG_PITCH_UP_SEMITONE", "LANG_PITCH_DOWN_SEMITONE"):
            with self.subTest(identifier=identifier):
                self.assertEqual(
                    {"*": "none", "pitchscreen": '""'},
                    self.polish[identifier]["voice"],
                )
        self.assertEqual(
            {"*": "none", "pitchscreen": '""'},
            self.polish["VOICE_PITCH_TIMESTRETCH_MODE"]["dest"],
        )

    def test_tts_display_voice_and_source_translations(self):
        for language_index, phrases in enumerate((self.english, self.polish)):
            self.assertEqual(
                set(TTS_TRANSLATIONS),
                {identifier for identifier in phrases if identifier.startswith("LANG_TTS")},
            )
            for identifier, translations in TTS_TRANSLATIONS.items():
                with self.subTest(language=language_index, identifier=identifier):
                    self.assertEqual(
                        {"*": f'"{translations[0]}"'}, phrases[identifier]["source"]
                    )
                    self.assertEqual(
                        {"*": f'"{translations[language_index]}"'},
                        phrases[identifier]["dest"],
                    )
                    voices = TTS_VOICE_OVERRIDES.get(identifier, translations)
                    self.assertEqual(
                        {"*": f'"{voices[language_index]}"'}, phrases[identifier]["voice"]
                    )

    def test_talkbox_root_has_its_own_complete_spoken_translation(self):
        for language_index, phrases in enumerate((self.english, self.polish)):
            with self.subTest(language=language_index):
                self.assertEqual({'*': '"Talkbox settings"'}, phrases['LANG_TALKBOX_SETTINGS']['source'])
                for section in ('dest', 'voice'):
                    self.assertEqual({'*': '"' + ('Talkbox settings', 'Ustawienia Talkbox')[language_index] + '"'},
                                     phrases['LANG_TALKBOX_SETTINGS'][section])

    def test_track_information_display_and_speech(self):
        for section in ("dest", "voice"):
            with self.subTest(section=section):
                self.assertEqual(
                    '"Pokaż informacje o utworze"',
                    self.polish["LANG_MENU_SHOW_ID3_INFO"][section]["*"],
                )
                self.assertEqual(
                    '"Informacje o utworze"',
                    self.polish["LANG_TRACK_INFO"][section]["*"],
                )


@unittest.skipUnless(shutil.which("perl"), "Perl is required for genlang tests")
class GenlangCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workspace = project_materials_root(ROOT)
        workspace.mkdir(exist_ok=True)
        cls.output = Path(tempfile.mkdtemp(prefix="polish-catalog-tests-", dir=workspace))
        cls.target = "sansaclipplus:rtc:recording:radio"
        cls.catalogs = {}
        for language in ("english", "polski", "deutsch"):
            cls.run_genlang(
                ROOT / f"apps/lang/{language}.lang",
                f"-b={cls.output / (language + '.lng')}",
                f"-c={cls.output / (language + '.vstrings')}",
            )
            for extension in ("lng", "vstrings"):
                cls.catalogs[language, extension] = cls.read_catalog(
                    cls.output / f"{language}.{extension}"
                )
        cls.identifiers = cls.read_identifiers(cls.output / "english.list")
        cls.fixture = cls.output / "voice-markers.lang"
        cls.fixture_values = {
            "LANG_NONE": ("none", ""),
            "LANG_UPPER_NONE": ("NONE", ""),
            "LANG_EMPTY": ('""', ""),
            "LANG_LITERAL_NONE": ('"none"', "none"),
            "LANG_SPACES": ('" "', " "),
            "LANG_UTF8": ('"Zażółć gęślą jaźń"', "Zażółć gęślą jaźń"),
            "LANG_DEPRECATED": ("deprecated", ""),
            "VOICE_NONE": ("none", ""),
        }
        phrases = []
        for identifier, (voice, expected) in cls.fixture_values.items():
            display = '""' if identifier.startswith("VOICE_") else '"Fixture"'
            phrases.append(
                f"<phrase>\n  id: {identifier}\n  desc: test fixture\n  user: core\n"
                f"  <source>\n    *: {display}\n  </source>\n"
                f"  <dest>\n    *: {display}\n  </dest>\n"
                f"  <voice>\n    *: {voice}\n  </voice>\n</phrase>\n"
            )
        cls.fixture.write_text("".join(phrases), encoding="utf-8")
        cls.run_genlang(
            cls.fixture, f"-c={cls.output / 'voice-markers.vstrings'}",
            english=cls.fixture,
        )
        cls.fixture_catalog = cls.read_catalog(cls.output / "voice-markers.vstrings")
        print(f"Genlang test evidence: {cls.output}")

    @classmethod
    def run_genlang(cls, language, *options, english=None, target=None):
        command = [
            shutil.which("perl"), "-s", (ROOT / "tools/genlang").as_posix(),
            f"-e={Path(english or ROOT / 'apps/lang/english.lang').as_posix()}",
            f"-t={target or cls.target}", "-i=66",
            *(option.replace("\\", "/") for option in options), language.as_posix(),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if completed.returncode or completed.stderr:
            raise AssertionError(
                f"genlang failed ({completed.returncode}): {completed.stderr}"
            )
        return completed.stdout

    @staticmethod
    def read_identifiers(path):
        identifiers = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            user, identifier, value = line.split(":")
            if user == "core":
                identifiers[identifier] = int(value)
        return identifiers

    @staticmethod
    def read_catalog(path):
        data = path.read_bytes()
        count, size, offset = struct.unpack_from(">HHH", data, 4)
        if offset != 10:
            raise AssertionError(f"Unexpected core catalog offset: {offset}")
        values = {}
        position = offset
        while position < len(data):
            identifier = struct.unpack_from(">H", data, position)[0]
            end = data.index(b"\0", position + 2)
            if identifier in values:
                raise AssertionError(f"Duplicate binary identifier: {identifier}")
            values[identifier] = data[position + 2:end].decode("utf-8")
            position = end + 1
        if len(values) != count:
            raise AssertionError(f"Declared {count} records, decoded {len(values)}")
        return {
            "header": data[:4], "declared_size": size,
            "payload_size": len(data) - offset, "values": values,
        }

    def test_catalog_headers_and_placeholder_parity(self):
        for (language, extension), catalog in self.catalogs.items():
            with self.subTest(language=language, extension=extension):
                cookie = 0x1A if extension == "lng" else 0x9A
                self.assertEqual(bytes((cookie, 6, 66, 0)), catalog["header"])
                self.assertEqual(catalog["declared_size"], catalog["payload_size"])
        for extension in ("lng", "vstrings"):
            english = self.catalogs["english", extension]["values"]
            polish = self.catalogs["polski", extension]["values"]
            self.assertEqual(english.keys(), polish.keys())
            for identifier in english:
                with self.subTest(extension=extension, identifier=identifier):
                    self.assertEqual(
                        PLACEHOLDER.findall(english[identifier]),
                        PLACEHOLDER.findall(polish[identifier]),
                    )

    def test_compiled_tts_display_and_voice_translations(self):
        for language_index, language in enumerate(("english", "polski")):
            for identifier, translations in TTS_TRANSLATIONS.items():
                voices = TTS_VOICE_OVERRIDES.get(identifier, translations)
                for extension, expected in (("lng", translations), ("vstrings", voices)):
                    with self.subTest(language=language, extension=extension, id=identifier):
                        self.assertEqual(
                            expected[language_index],
                            self.catalogs[language, extension]["values"][
                                self.identifiers[identifier]
                            ],
                        )

    def test_compiled_talkbox_root_is_distinct_from_engine_settings(self):
        for language, expected in (("english", "Talkbox settings"), ("polski", "Ustawienia Talkbox")):
            for extension in ("lng", "vstrings"):
                with self.subTest(language=language, extension=extension):
                    values = self.catalogs[language, extension]["values"]
                    self.assertEqual(values[self.identifiers["LANG_TALKBOX_SETTINGS"]], expected)
                    self.assertNotEqual(values[self.identifiers["LANG_TTS"]], expected)

    def test_compiled_followup_display_and_voice(self):
        for target, selector in (
            (self.target, "*"),
            ("iriverh120:remote", "remote"),
            ("sansaclipplus:dircache", "dircache"),
            ("sansaclipzip:usbdac", "usbdac"),
            ("sansaclipplus:pitchscreen", "pitchscreen"),
            ("ipodvideo:accessory_supply", "accessory_supply"),
            ("gigabeats", "gigabeats,samsungypr1"),
            ("samsungypr1", "gigabeats,samsungypr1"),
        ):
            for language in ("english", "polski"):
                source = ROOT / f"apps/lang/{language}.lang"
                phrases = parse_language(source.read_text(encoding="utf-8"))
                if target == self.target:
                    identifiers = self.identifiers
                    catalogs = {
                        extension: self.catalogs[language, extension]
                        for extension in ("lng", "vstrings")
                    }
                else:
                    target_output = self.output / target.replace(":", "-")
                    target_output.mkdir(exist_ok=True)
                    prefix = target_output / language
                    self.run_genlang(
                        source, f"-b={prefix}.lng", f"-c={prefix}.vstrings", target=target,
                    )
                    identifiers = self.read_identifiers(target_output / "english.list")
                    catalogs = {
                        extension: self.read_catalog(Path(f"{prefix}.{extension}"))
                        for extension in ("lng", "vstrings")
                    }
                fixes = FOLLOWUP_FIXES + CATALOG_FIXES
                if target == self.target:
                    fixes = FIXES + fixes
                for identifier, fix_selector, sections, original, corrected in fixes:
                    if fix_selector != selector:
                        continue
                    for section, extension in (("dest", "lng"), ("voice", "vstrings")):
                        if section == "dest" and identifier.startswith("VOICE_"):
                            self.assertEqual('""', phrases[identifier][section][selector])
                            continue
                        with self.subTest(target=target, language=language,
                                          id=identifier, section=section):
                            self.assertEqual(
                                phrases[identifier][section][selector][1:-1],
                                catalogs[extension]["values"][identifiers[identifier]],
                            )
                for identifier, menu_selector, source, translated in MENU_TRANSLATIONS:
                    if menu_selector != selector:
                        continue
                    for section, extension in (("dest", "lng"), ("voice", "vstrings")):
                        expected = (
                            translated if language == "polski"
                            else phrases[identifier][section][selector][1:-1]
                        )
                        with self.subTest(target=target, language=language,
                                          id=identifier, extension=extension):
                            self.assertEqual(
                                expected,
                                catalogs[extension]["values"][identifiers[identifier]],
                            )

    def test_disabled_menu_features_are_absent_from_catalogs(self):
        identifiers = [
            identifier for identifier, selector, source, translated
            in MENU_TRANSLATIONS if selector != "*"
        ] + [
            "LANG_PITCH_UP_SEMITONE", "LANG_PITCH_DOWN_SEMITONE",
            "VOICE_PITCH_TIMESTRETCH_MODE",
        ]
        for identifier in identifiers:
            with self.subTest(identifier=identifier, target=self.target):
                self.assertNotIn(identifier, self.identifiers)

    def test_none_markers_are_silent_in_real_catalogs(self):
        for language in ("english", "polski", "deutsch"):
            for identifier in (
                "LANG_TIME_SET_BUTTON", "LANG_TIME_REVERT", "LANG_PERCENT_FORMAT",
            ):
                with self.subTest(language=language, identifier=identifier):
                    self.assertEqual(
                        "", self.catalogs[language, "vstrings"]["values"][
                            self.identifiers[identifier]
                        ],
                    )

    def test_voice_only_fixture_header_and_values(self):
        catalog = self.fixture_catalog
        self.assertEqual(catalog["declared_size"], catalog["payload_size"])
        expected = [value for original, value in self.fixture_values.values()]
        self.assertEqual(expected, list(catalog["values"].values()))

    def test_text_voice_output_preserves_literals_and_silence(self):
        output = self.run_genlang(self.fixture, "-o", english=self.fixture)
        voices = dict(re.findall(r'^id: (\w+)\nvoice: "(.*)"$', output, re.MULTILINE))
        self.assertEqual(
            {identifier: expected for identifier, (original, expected)
             in self.fixture_values.items()},
            voices,
        )

    def test_compiled_polish_numeric_scale(self):
        values = self.catalogs["polski", "vstrings"]["values"]
        for offset, identifier, expected in (
            (0, "VOICE_THOUSAND", "tysiąc"),
            (1, "VOICE_MILLION", "milion"),
            (2, "VOICE_BILLION", "miliard"),
        ):
            with self.subTest(identifier=identifier):
                numeric_id = self.identifiers["VOICE_THOUSAND"] + offset
                self.assertEqual(numeric_id, self.identifiers[identifier])
                self.assertEqual(expected, values[numeric_id])

    def test_actual_numeric_branch_uses_billion_for_ten_to_nine(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("A C compiler is required for the numeric branch harness")
        source = (ROOT / "apps/talk.c").read_text(encoding="utf-8")
        function = re.search(
            r"int talk_number\(long n, bool enqueue\)\n\{.*?^\}",
            source, re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(function)
        definitions = "\n".join(
            f"#define {identifier} {self.identifiers[identifier]}"
            for identifier in (
                "VOICE_ZERO", "VOICE_CHAR_E", "VOICE_HUNDRED", "VOICE_THOUSAND",
                "VOICE_MINUS", "VOICE_NUMERIC_TENS_SWAP_SEPARATOR",
            )
        )
        harness = self.output / "numeric-branch.c"
        executable = self.output / (
            "numeric-branch.exe" if os.name == "nt" else "numeric-branch"
        )
        harness.write_text(
            "#include <stdbool.h>\n#include <stdio.h>\n#include <stdlib.h>\n"
            + definitions + "\n" + r"""
struct queue_entry { int unused; };
static bool talk_is_disabled(void) { return false; }
static void do_enqueue(bool enqueue) { (void)enqueue; }
static void talk_id(int identifier, bool enqueue)
{
    (void)enqueue;
    printf("%d\n", identifier);
}
static int get_clip(int identifier, struct queue_entry *entry)
{
    (void)identifier;
    (void)entry;
    return -1;
}
""" + function.group(0) + r"""
int main(int argument_count, char **arguments)
{
    if (argument_count != 2)
        return 1;
    return talk_number(strtol(arguments[1], NULL, 10), false);
}
""", encoding="utf-8",
        )
        subprocess.run(
            [compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
             str(harness), "-o", str(executable)],
            check=True, capture_output=True, text=True,
            env={**os.environ, "TMPDIR": str(self.output)},
        )
        for number, identifier in (
            (1000, "VOICE_THOUSAND"), (1000000, "VOICE_MILLION"),
            (1000000000, "VOICE_BILLION"),
        ):
            with self.subTest(number=number):
                result = subprocess.run(
                    [str(executable), str(number)], check=True,
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    [self.identifiers["VOICE_ONE"], self.identifiers[identifier]],
                    [int(value) for value in result.stdout.splitlines()],
                )


if __name__ == "__main__":
    unittest.main()
