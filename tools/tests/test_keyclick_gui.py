"""Isolated R1 SDL disk-mixer keyclick checks, not a product builder.

--self-test exercises only PCM/configuration helpers; it never opens a window.
Real runs require the same explicit --build-ready and frozen --exe-sha256 as
test_hiby_accessibility_gui.py. The build owner must grant the exclusive GUI
token first. Each matrix case uses a synthetic profile, muted speech and no
music, so unrelated speech cannot masquerade as a keyclick. Runtime copies,
PCM and logs remain in the central R1 GUI evidence area for reproduction.

This checks routing and observable click bursts, not human sound quality,
physical R1 input, NVDA, or two duplicate beep calls that overwrite the same
2 ms mixer slot. UI editing of strength/source is a separate acceptance gate.
"""

import array
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest


SAMPLE_RATE = 44100
STRENGTHS = ("off", "weak", "moderate", "strong")
SCOPES = {"both": 3, "physical": 1, "gestures": 2}
ROOT = Path(__file__).resolve().parents[2]


def configuration(language, strength, repeats=False):
    if language not in ("english", "polski") or strength not in STRENGTHS:
        raise ValueError("Invalid synthetic language/keyclick strength")
    return (f"lang: /.rockbox/langs/{language}.lng\n"
            "start in screen: root\nshow files: all\nsort case: off\n"
            "talk menu: off\ntalk dir: off\ntalk file: off\ntalk mixer level: 0\n"
            "talk dir clip: off\ntalk file clip: off\ntts enabled: off\n"
            "volume: 0\nbeep: off\nplayback frequency: 44100\n"
            "backlight filters first keypress: off\n"
            f"keyclick: {strength}\nkeyclick repeats: {'on' if repeats else 'off'}\n")


def accessibility_configuration(sources, version=8):
    if type(sources) is not int or sources not in SCOPES.values() or type(version) is not int or version not in (3, 4, 5, 6, 7, 8):
        raise ValueError("Invalid synthetic input feedback scope")
    mapping = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 8: 7, 17: 5}
    system_action = {3: 15, 4: 16, 5: 17, 6: 19, 7: 22, 8: 22}[version]
    return (f"RBACCESSIBILITY:{version}\nenabled:1\nclick:{sources}\nhold:700\n"
            + ("touch_hold:900\nstroke_repeat:0\n" if version >= 7 else "")
            + ("empty_pitch:1\nempty_semitones:-4\n" if version >= 8 else "")
            + ''.join(f"gesture:{slot}:{mapping.get(slot, 0)}:0\n" for slot in range(1, 21 if version >= 7 else 19))
            + ''.join(f"button:{button}:{slot}:{system_action}:0\n" for button in range(5) for slot in range(4))
            + ''.join(f"target:{target}:\n" for target in range(4))).encode("ascii")


def analyze_pcm(data, sample_rate=SAMPLE_RATE):
    if not isinstance(data, bytes) or len(data) % 4:
        raise ValueError("Expected complete stereo signed-16-bit little-endian PCM frames")
    if not 8000 <= sample_rate <= 192000:
        raise ValueError("Invalid PCM sample rate")
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    frames = len(samples) // 2
    intervals = []
    begin = None
    for frame in range(frames):
        nonzero = samples[frame * 2] != 0 or samples[frame * 2 + 1] != 0
        if nonzero and begin is None:
            begin = frame
        elif not nonzero and begin is not None:
            intervals.append((begin, frame))
            begin = None
    if begin is not None:
        intervals.append((begin, frames))
    bursts = []
    for begin, end in intervals:
        channel = samples[begin * 2:end * 2:2]
        flips = sum((first < 0) != (second < 0) for first, second in zip(channel, channel[1:]))
        duration = (end - begin) / sample_rate
        bursts.append({"start_frame": begin, "end_frame": end, "frames": end - begin,
                       "seconds": duration, "peak": max(map(abs, channel), default=0),
                       "sign_flips": flips, "estimated_frequency_hz": flips / (2 * duration),
                       "channels_equal": all(samples[frame * 2] == samples[frame * 2 + 1]
                                             for frame in range(begin, end))})
    return {"frames": frames, "sample_rate_assumption": sample_rate, "bursts": bursts,
            "peak": max(map(abs, samples), default=0),
            "nonzero_samples": sum(sample != 0 for sample in samples)}


def check_clicks(analysis, expected):
    bursts = analysis["bursts"]
    if len(bursts) != expected:
        raise AssertionError(f"Expected {expected} isolated keyclick bursts, found {len(bursts)}")
    nominal_frames = (analysis["sample_rate_assumption"] // 1000) * 2
    for burst in bursts:
        if not (abs(burst["frames"] - nominal_frames) <= 8
                and 3200 <= burst["estimated_frequency_hz"] <= 4800
                and burst["peak"] >= 8 and burst["channels_equal"]):
            raise AssertionError(f"Non-keyclick audio or incomplete 2 ms / 4 kHz burst: {burst}")


def capture_feedback(probe, name, action, expected, duration=0.5, prequiet=0.15):
    from test_tts_bookmarks_gui import phrases, require
    pcm = Path(probe.session["pcm"])
    probe.observe(prequiet)
    marker = probe.mark()
    start = pcm.stat().st_size if pcm.exists() else 0
    observation = {"name": name, "status": "in_progress", "session": probe.session["name"],
                   "speech_required": False, "pcm_start": start, "log_start": marker,
                   "keyclick_expected": expected}
    probe.report["checks"].append(observation)
    probe.session["checks"].append(name)
    try:
        if action is not None:
            action()
        probe.observe(duration)
        observation["pcm_end"] = pcm.stat().st_size if pcm.exists() else 0
        text = probe.text(marker)
        require(not phrases(text) and not phrases(text, "TTS utterance"),
                "Speech contaminated isolated keyclick PCM")
        observation["pcm_advanced"] = observation["pcm_end"] > start
        require(expected == 0 or observation["pcm_advanced"],
                "Expected keyclick did not start/advance the disk mixer")
        if not observation["pcm_advanced"]:
            observation["negative_pcm_limit"] = "Mixer may be paused; this is absent output, not sampled silence"
        observation["status"] = "pending_keyclick_pcm"
    except Exception as error:
        observation.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        observation["log_end"] = probe.mark()
    return observation


def explore_without_click(probe, first, second):
    probe.mouse.press(first)
    try:
        probe.observe(0.3)
        probe.mouse.move(second)
        probe.observe(0.3)
        probe.mouse.move(first)
        probe.observe(0.3)
    finally:
        probe.mouse.release()


def exercise_feedback(probe, language):
    from test_hiby_accessibility_gui import parse_accessibility_config
    from test_tts_bookmarks_gui import require, write_json
    resources = probe.runtime / "simdisk/.rockbox"
    probe.report["keyclick_requirements"] = {
        "strengths_and_scopes": "in_progress", "silent_exploration": "in_progress",
        "single_tap_delay": "in_progress", "double_tap_once": "in_progress",
        "repeat_behavior": "not_tested", "ui_strength_editor": "not_tested",
        "ui_source_editor": "not_tested", "default_scope_without_config": "not_tested"}
    probe.report["limitations"].extend([
        "Keyclick cases load synthetic strength/source settings; not UI-editor persistence acceptance.",
        "Signed-16-bit stereo disk PCM at requested 44100 Hz; incompatible output fails, never auto-relabels.",
        "Two overlapping beep calls can replace one mixer slot and are not distinguishable from one PCM burst.",
        "Repeat filtering and absent-config default scope need additional actual GUI cases."])
    for strength in STRENGTHS:
        for scope, sources in SCOPES.items():
            name = f"keyclick-{strength}-{scope}"
            config = configuration(language, strength)
            accessibility = accessibility_configuration(sources)
            parsed = parse_accessibility_config(accessibility)
            require(parsed["click_sources"] == sources, "Synthetic feedback fixture parser mismatch")
            (resources / "config.cfg").write_text(config, encoding="utf-8")
            (resources / "accessibility.cfg").write_bytes(accessibility)
            write_json(probe.results / (name + "-profile.json"), {
                "purpose": "Synthetic isolated keyclick measurement, not user configuration",
                "accessibility_config_version": parsed["version"],
                "config": config, "accessibility": accessibility.decode("ascii")})
            probe.launch(name)
            probe.wait(lambda text: "A11Y list geometry:" in text, 0, "actual root list draw")
            probe.observe(0.6)
            initial = probe.geometry()
            require(initial.group == 1 and initial.count >= 3 and initial.selected < initial.count - 1,
                    "Synthetic root focus cannot move down without an edge sound")
            capture_feedback(probe, name + " idle silence", None, 0)
            expected_physical = int(strength != "off" and bool(sources & 1))
            expected_gesture = int(strength != "off" and bool(sources & 2))
            capture_feedback(probe, name + " physical Down", lambda: probe.press("Down"), expected_physical)
            require(probe.geometry().selected == initial.selected + 1,
                    "Physical keyclick case did not move the actual focused row exactly once")
            capture_feedback(probe, name + " physical Up", lambda: probe.press("Up"), expected_physical)
            require(probe.geometry().selected == initial.selected, "Physical restoration changed focus unexpectedly")
            capture_feedback(probe, name + " gesture Right", lambda: probe.mouse.swipe("right"), expected_gesture)
            require(probe.geometry().selected == initial.selected + 1,
                    "Gesture keyclick case did not move the actual focused row exactly once")
            capture_feedback(probe, name + " gesture Left", lambda: probe.mouse.swipe("left"), expected_gesture)
            require(probe.geometry().selected == initial.selected, "Gesture restoration changed focus unexpectedly")
            point = probe.geometry().point(initial.selected)
            next_point = probe.geometry().point(initial.selected + 1)
            capture_feedback(probe, name + " held exploration stays silent",
                             lambda: explore_without_click(probe, point, next_point), 0)
            capture_feedback(probe, name + " single tap decision window",
                             lambda: probe.mouse.tap(point), 0, duration=0.12)
            capture_feedback(probe, name + " resolved single tap", None, expected_gesture,
                             duration=0.7, prequiet=0)
            capture_feedback(probe, name + " double tap once", probe.mouse.double_tap, expected_gesture)
            probe.close()
    probe.report["completed_scenarios"].append("keyclick-source-and-strength-matrix")


def verify_feedback(report):
    from test_tts_bookmarks_gui import phrases, require
    from test_tts_recorder_gui import digest
    changed = [item["source"] for item in report["copies"] + report.get("catalog_inputs", [])
               if not Path(item["source"]).is_file() or digest(Path(item["source"])) != item["sha256"]]
    report["changed_source_assets"] = changed
    require(not changed, "Immutable runtime source assets changed during feedback testing")
    for session in report["sessions"]:
        require(session.get("exit_code") == 0 and not session.get("forced_owned_process_cleanup"),
                f"Unclean feedback session exit: {session['name']}")
        require(bool(session.get("log")), "Missing complete feedback session log")
        text = Path(session["log"]).read_text(encoding="utf-8", errors="replace")
        require(not phrases(text) and not phrases(text, "TTS utterance"),
                "Speech present in speech-disabled feedback session")
        require("TTS: synthesis failed" not in text, "Synthesis failure in isolated feedback session")
        pcm = Path(session["pcm"])
        session["pcm_sha256"] = digest(pcm) if pcm.is_file() else None
        for check in report["checks"]:
            if check.get("session") != session["name"]:
                continue
            start, end = check["pcm_start"], check["pcm_end"]
            require(start % 4 == 0 and end % 4 == 0 and end >= start,
                    "Incomplete/invalid stereo disk PCM action interval")
            data = b""
            if pcm.is_file():
                with pcm.open("rb") as source:
                    source.seek(start)
                    data = source.read(end - start)
            require(len(data) == end - start, "Disk PCM interval was truncated")
            analysis = analyze_pcm(data)
            check["keyclick_pcm"] = analysis
            try:
                require(not check["keyclick_expected"] or analysis["frames"] > 0,
                        "Expected beep has no PCM frames")
                check_clicks(analysis, check["keyclick_expected"])
                require(check["status"] == "pending_keyclick_pcm", "Feedback action did not finish successfully")
                check["status"] = "passed"
            except AssertionError as error:
                check.update(status="failed", error=str(error))
    require(all(check["status"] == "passed" for check in report["checks"]), "Keyclick PCM regression failed")
    require(len(report["sessions"]) == 12 and len(report["checks"]) == 108,
            "Incomplete feedback source/strength matrix")
    for suffix in ("physical Down", "gesture Right"):
        peaks = {}
        for strength in STRENGTHS[1:]:
            name = f"keyclick-{strength}-both {suffix}"
            matching = [check for check in report["checks"] if check["name"] == name]
            require(len(matching) == 1, "Missing strength comparison observation")
            peaks[strength] = matching[0]["keyclick_pcm"]["bursts"][0]["peak"]
        check_strengths(peaks)
        report.setdefault("keyclick_strength_peaks", {})[suffix] = peaks
    report["keyclick_requirements"].update(strengths_and_scopes="passed", silent_exploration="passed",
                                            single_tap_delay="passed", double_tap_once="passed")


def check_strengths(peaks):
    weak = peaks["weak"]
    if weak < 8 or abs(peaks["moderate"] - weak * 2) > max(3, weak * 0.05) or abs(
            peaks["strong"] - weak * 3) > max(3, weak * 0.05):
        raise AssertionError(f"Keyclick strength did not scale 1:2:3 at fixed volume: {peaks}")


def synthetic_pcm(bursts=1, amplitude=2500, frequency=4000, duration=0.002):
    frames = int(round(duration * SAMPLE_RATE))
    result = array.array("h", [0] * 200)
    for _index in range(bursts):
        for frame in range(frames):
            value = amplitude if int(frame * frequency * 2 / SAMPLE_RATE) % 2 == 0 else -amplitude
            result.extend((value, value))
        result.extend([0] * 200)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


class FeedbackHarnessTests(unittest.TestCase):
    def test_synthetic_profiles_disable_all_unattributed_audio(self):
        for language in ("polski", "english"):
            for strength in STRENGTHS:
                text = configuration(language, strength)
                self.assertIn("tts enabled: off\n", text)
                self.assertIn("talk menu: off\n", text)
                self.assertIn("beep: off\n", text)
                self.assertIn(f"keyclick: {strength}\n", text)

    def test_all_feedback_scopes_have_valid_complete_legacy_v8_profiles(self):
        from test_hiby_accessibility_gui import ACCESSIBILITY_CONFIG_VERSION, parse_accessibility_config
        for sources in SCOPES.values():
            data = accessibility_configuration(sources)
            parsed = parse_accessibility_config(data)
            self.assertLess(parsed["version"], ACCESSIBILITY_CONFIG_VERSION)
            self.assertEqual(parsed["version"], 8)
            self.assertEqual(len(data.splitlines()), 52)
            self.assertTrue(parsed["empty_pitch"])
            self.assertEqual(parsed["empty_semitones"], -4)
            self.assertEqual(parsed["click_sources"], sources)
            self.assertEqual(parsed["gestures"][2], 2)
            self.assertEqual(parsed["gestures"][8], 7)
            self.assertEqual(len(parsed["buttons"]), 20)
            self.assertEqual(set(parsed["buttons"].values()), {22})
            self.assertEqual(len(parsed["gestures"]), 20)
            self.assertEqual([parsed["gestures"][slot] for slot in (19, 20)], [0, 0])
            self.assertEqual(parsed["touch_hold_ms"], 900)
            self.assertFalse(parsed["stroke_repeat"])
            self.assertEqual(len(parsed["launch_paths"]), 4)
            self.assertFalse(any(parsed["gesture_launch"].values()))
            self.assertFalse(any(parsed["button_launch"].values()))

    def test_feedback_profiles_keep_each_supported_system_sentinel(self):
        from test_hiby_accessibility_gui import parse_accessibility_config
        for version, system_action in ((3, 15), (4, 16), (5, 17), (6, 19), (7, 22)):
            for sources in SCOPES.values():
                with self.subTest(version=version, sources=sources):
                    parsed = parse_accessibility_config(accessibility_configuration(sources, version))
                    self.assertEqual(parsed["version"], version)
                    self.assertEqual(set(parsed["buttons"].values()), {system_action})
                    self.assertEqual(len(parsed["gestures"]), 20 if version == 7 else 18)
                    self.assertEqual(len(accessibility_configuration(sources, version).splitlines()),
                                     50 if version == 7 else 46)
        for version in (True, 0, 2, 9, "5", "6", "7", "8", 6.0, 7.0, 8.0):
            with self.subTest(version=version), self.assertRaises(ValueError):
                accessibility_configuration(3, version)

    def test_feedback_generator_rejects_noncanonical_scopes(self):
        for sources in (True, False, 0, 4, -1, "3", 3.0, None):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                accessibility_configuration(sources)

    def test_silence_is_distinct_from_missing_pcm(self):
        silent = analyze_pcm(bytes(44100 * 4))
        self.assertEqual(silent["frames"], 44100)
        check_clicks(silent, 0)
        self.assertEqual(analyze_pcm(b"")["frames"], 0)
        with self.assertRaises(AssertionError):
            check_clicks(silent, 1)

    def test_single_keyclick_has_expected_duration_frequency_and_channels(self):
        analysis = analyze_pcm(synthetic_pcm())
        check_clicks(analysis, 1)
        self.assertEqual(analysis["bursts"][0]["peak"], 2500)
        self.assertTrue(analysis["bursts"][0]["channels_equal"])

    def test_separated_duplicate_clicks_are_rejected(self):
        analysis = analyze_pcm(synthetic_pcm(2))
        with self.assertRaises(AssertionError):
            check_clicks(analysis, 1)
        check_clicks(analysis, 2)

    def test_strength_effect_is_not_just_a_setting_label(self):
        check_strengths({"weak": 2500, "moderate": 5000, "strong": 7500})
        for peaks in ({"weak": 2500, "moderate": 2500, "strong": 2500},
                      {"weak": 2500, "moderate": 7500, "strong": 5000}):
            with self.subTest(peaks=peaks), self.assertRaises(AssertionError):
                check_strengths(peaks)

    def test_track_or_list_edge_sounds_cannot_masquerade_as_keyclicks(self):
        for frequency, duration in ((1000, 0.04), (2000, 0.02), (2000, 0.1), (997, 0.002)):
            with self.subTest(frequency=frequency, duration=duration), self.assertRaises(AssertionError):
                check_clicks(analyze_pcm(synthetic_pcm(frequency=frequency, duration=duration)), 1)

    def test_pcm_validation_rejects_partial_frames_and_invalid_rate(self):
        for data in (b"\0", b"\0\0", b"\0\0\0"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                analyze_pcm(data)
        with self.assertRaises(ValueError):
            analyze_pcm(b"", 0)


def keyclick_factory_declarations(source):
    defaults = re.search(r'#ifdef HAVE_ESPEAK\s*\n#define DEFAULT_KEYCLICK_STRENGTH [^\n]+\n'
                         r'#else\s*\n#define DEFAULT_KEYCLICK_STRENGTH [^\n]+\n#endif', source)
    if defaults is None:
        raise AssertionError("Missing actual eSpeak/non-eSpeak default definition")
    choices = []
    for match in re.finditer(r'CHOICE_SETTING\(0,\s*keyclick,\s*LANG_KEYCLICK(?:_SOFTWARE)?,', source):
        position = match.start() + source[match.start():].index('(') + 1
        depth = 1
        while depth and position < len(source):
            depth += (source[position] == '(') - (source[position] == ')')
            position += 1
        if depth:
            raise AssertionError("Unterminated actual keyclick setting declaration")
        choices.append(source[match.start():position])
    if len(choices) != 2:
        raise AssertionError("Both actual software/hardware-click setting declarations are required")
    return defaults[0], choices


class FreshDefaultCompilationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; run actual factory-default compilation under WSL")
        sys.path.insert(0, str(ROOT / "tools"))
        from project_materials import project_materials_root
        cls.directory = project_materials_root(ROOT) / "r1-empty-radio-20261017" / (
            "pipeline-default-tests-" + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        cls.directory.mkdir(parents=True, exist_ok=False)
        cls.source = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")

    def compile_default(self, source, espeak, variant, expected, name):
        definitions, choices = keyclick_factory_declarations(source)
        harness = ('#include <stdio.h>\n' + ('#define HAVE_ESPEAK\n' if espeak else '') + definitions + '\n'
            '#define CHOICE_SETTING(flags, member, label, default_value, ...) { .member = (default_value) }\n'
            'static const struct { int keyclick; } factory = ' + choices[variant] + ';\n'
            'int main(void) { printf("%d\\n", factory.keyclick); return factory.keyclick != ' + str(expected) + '; }\n')
        path = self.directory / (name + '.c')
        executable = path.with_suffix('.exe' if sys.platform == 'win32' else '.bin')
        path.write_text(harness, encoding='utf-8')
        command = self.compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(executable)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10, check=False)
        (self.directory / (name + '.json')).write_text(json.dumps(dict(
            source_sha256=hashlib.sha256(self.source.encode()).hexdigest(),
            tested_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            harness_sha256=hashlib.sha256(harness.encode()).hexdigest(), command=command,
            compile_returncode=compiled.returncode, execute_returncode=result.returncode, stdout=result.stdout,
            espeak=espeak, declaration_variant=variant, expected=expected,
            scope='Positive actual default macro/CHOICE_SETTING/member projection; negative mutation guard; not live GUI or PCM',
            actual_gui_executed=False, host_audio_used=False), indent=2) + '\n', encoding='utf-8')
        self.assertEqual((ROOT / 'apps/settings_list.c').read_text(encoding='utf-8'), self.source)
        return result

    def test_actual_factory_defaults_are_moderate_for_espeak_and_off_for_other_targets(self):
        for espeak, expected in ((True, 2), (False, 0)):
            for variant in (0, 1):
                with self.subTest(espeak=espeak, variant=variant):
                    result = self.compile_default(self.source, espeak, variant, expected, f'default-{espeak}-{variant}')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), str(expected))

    def test_mutating_espeak_default_back_to_off_is_detected(self):
        changed = self.source.replace('#define DEFAULT_KEYCLICK_STRENGTH 2', '#define DEFAULT_KEYCLICK_STRENGTH 0', 1)
        self.assertNotEqual(changed, self.source)
        result = self.compile_default(changed, True, 0, 2, 'negative-old-off')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), '0')


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--self-test"]:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(
            unittest.defaultTestLoader.loadTestsFromTestCase(test_case)
            for test_case in (FeedbackHarnessTests, FreshDefaultCompilationTests)))
        return 0 if result.wasSuccessful() else 1
    if "--self-test" in arguments or "--suite" in arguments or any(value.startswith("--suite=") for value in arguments):
        raise SystemExit("--self-test must be used alone; this harness always selects --suite keyclick")
    from test_hiby_accessibility_gui import main as accessibility_main
    return accessibility_main(["--suite", "keyclick", *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
