"""Native Windows GUI/PCM smoke for spoken utility plugins on both Sansas.

Wait for explicit target-build authorization, then run one language per command:
  python -B tools/tests/test_tts_plugins_gui.py --target sansaclipplus --language polski --build-ready
  python -B tools/tests/test_tts_plugins_gui.py --target sansaclipzip --language english --build-ready

Repeat both languages for both targets. The shared recorder fixture copier and
EXE loan are reused directly, not its main/suite. No user profile is copied.
Runtime assets and root .rock aliases are deliberate retained diagnostic copies;
the development EXE is moved and restored with its identity/hash unchanged.
Each plugin gets its own process, complete log/PCM and fresh synthetic config.
Pass --voice-files-disabled to disable recorded menu/file/directory speech
and mute recorded voices while keeping eSpeak enabled in the clean fixture.
Action PCM is checked only after that process exits. Metronome observations are
paused, so click output cannot substitute for speech. No human/NVDA/hardware or
active-click duplex validation is claimed. Failures remain in the aggregate.

Extension API: run_suite(plugins, exercise, required_labels, argv=None,
extra_sources=(), after_session=None). exercise(driver, labels) uses PluginDriver.navigate_to_alias,
speech and exit_to_root. Mark one speech check requirement="initial_focus",
at least two requirement="functional_action", and one requirement="exit_root".
Set driver.pcm_attribution="speech_only" only if there are no other PCM sources;
the safe default is "unattributed". speech(..., pcm_attribution="mixed") marks
an individual music/beep observation. Nonzero mixed/unattributed PCM is partial,
never a speech PASS. UTF-8 fragments are matched intact in logs AND synthesis.
run_suite owns profiles, launch/cleanup, original EXE restoration and final PCM.
Optional after_session(driver, session, results) runs after process exit/log
preservation and before PCM validation and the session verdict. Its failures
remain visible and prevent success without discarding other plugin sessions.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

from test_tts_recorder_gui import (
    ExecutableLoan, RecorderProbe, TARGETS, contained, digest, display_labels,
    pcm_summary, prepare_fixture, voice_file_settings,
)
from test_tts_simulator import catalog_labels, find_window, send_key, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ("calculator", "stopwatch", "metronome", "dice")
ALIASES = {name: f"{index:03d} {name}.rock" for index, name in enumerate(PLUGINS, 1)}
REQUIRED_LABELS = (
    "LANG_DIR_BROWSER", "LANG_CALCULATOR_RESULT", "LANG_COUNTDOWN_TIMER_PAUSED",
    "LANG_COUNTDOWN_TIMER_RUNNING", "LANG_ELAPSED", "LANG_STOPWATCH_LAP",
    "LANG_METRONOME_TEMPO", "LANG_METRONOME_METER", "LANG_VOLUME",
    "LANG_DICE_ROLL", "LANG_DICE_RESULTS", "LANG_DICE_TOTAL",
)
SOURCE_INPUTS = (
    "uisimulator/buttonmap/sansa-clip.c", "apps/plugins/lib/pluginlib_actions.c",
    "firmware/export/config/sansaclipplus.h", "firmware/export/config/sansaclipzip.h",
    "apps/plugins/calculator.c", "apps/plugins/stopwatch.c",
    "apps/plugins/metronome.c", "apps/plugins/dice.c",
    "tools/tests/test_tts_recorder_gui.py", "tools/tests/test_tts_simulator.py",
    "tools/tests/test_tts_plugins_gui.py",
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def logged_phrases(text, prefix="TTS"):
    return re.findall(r"^" + re.escape(prefix) + r": (.*)$", text, re.MULTILINE)


def numeric_values(phrases):
    return re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", " ".join(phrases))


def speech_matches(phrases, fragments=(), numbers=()):
    text = " ".join(phrases)
    return all(fragment in text for fragment in fragments) and all(
        str(number) in numeric_values(phrases) for number in numbers)


def validate_dice_result(phrases, labels):
    results_label = labels["LANG_DICE_RESULTS"]
    total_label = labels["LANG_DICE_TOTAL"]
    joined = " ".join(phrases)
    require(results_label in joined and total_label in joined, "Missing dice result/total labels")
    results = joined.split(results_label, 1)[1]
    before_total, after_total = results.split(total_label, 1)
    faces = numeric_values([before_total])
    total = numeric_values([after_total])
    require(len(faces) == 1 and len(total) == 1, "Expected exactly one default die and one total")
    require(faces[0].isdigit() and total[0].isdigit(), "Dice results must be integers")
    require(1 <= int(faces[0]) <= 6 and int(total[0]) == int(faces[0]),
            "Default six-sided die or total is invalid")
    return {"faces": [int(faces[0])], "total": int(total[0]), "sides": 6}


def parse_keyboard_map(source):
    available = {}
    for match in re.finditer(
            r"((?:\s*case SDLK_[A-Z_0-9]+:\s*)+)new_btn\s*=\s*(BUTTON_[A-Z_]+);", source):
        available[match.group(2)] = re.findall(r"case (SDLK_[A-Z_0-9]+):", match.group(1))
    preferred = {
        "BUTTON_LEFT": ("SDLK_LEFT", "Left"), "BUTTON_RIGHT": ("SDLK_RIGHT", "Right"),
        "BUTTON_UP": ("SDLK_UP", "Up"), "BUTTON_DOWN": ("SDLK_DOWN", "Down"),
        "BUTTON_SELECT": ("SDLK_SPACE", "space"), "BUTTON_POWER": ("SDLK_ESCAPE", "Escape"),
    }
    for button, (symbol, key) in preferred.items():
        require(symbol in available.get(button, ()), f"Source no longer maps {symbol} to {button}")
    return {button: key for button, (symbol, key) in preferred.items()}


def keypad_defines(source):
    branches = list(re.finditer(r"^#(?:if|elif)(?:[^\n]*\\\n)*[^\n]*", source, re.MULTILINE))
    for branch in branches:
        if "SANSA_CLIP_PAD" not in branch.group():
            continue
        end = re.search(r"^#(?:elif|else|endif)\b", source[branch.end():], re.MULTILINE)
        require(end is not None, "Unterminated Sansa keymap branch")
        body = source[branch.end():branch.end() + end.start()]
        return dict(re.findall(r"^#define\s+(\w+)\s+([^\n]+)", body, re.MULTILINE))
    raise AssertionError("No Sansa Clip keymap branch in plugin source")


def target_keyboard_map(target):
    require(target in TARGETS, "Unsupported target")
    keyboard = parse_keyboard_map((ROOT / SOURCE_INPUTS[0]).read_text(encoding="utf-8"))
    configuration = (ROOT / f"firmware/export/config/{target}.h").read_text(encoding="utf-8")
    require(re.search(r"^#define CONFIG_KEYPAD\s+SANSA_CLIP_PAD\b", configuration, re.MULTILINE),
            "Selected target no longer uses the verified Sansa Clip keypad")
    calculator = keypad_defines((ROOT / "apps/plugins/calculator.c").read_text(encoding="utf-8"))
    stopwatch = keypad_defines((ROOT / "apps/plugins/stopwatch.c").read_text(encoding="utf-8"))
    required = {
        "CALCULATOR_INPUT": "(BUTTON_SELECT|BUTTON_REL)", "CALCULATOR_CALC": "(BUTTON_SELECT|BUTTON_REPEAT)",
        "CALCULATOR_RIGHT": "BUTTON_RIGHT", "CALCULATOR_QUIT": "BUTTON_POWER",
        "STOPWATCH_START_STOP": "BUTTON_RIGHT", "STOPWATCH_LAP_TIMER": "BUTTON_SELECT",
        "STOPWATCH_QUIT": "BUTTON_POWER",
    }
    for name, definition in required.items():
        actual = (calculator | stopwatch).get(name, "")
        require(re.sub(r"\s+", "", actual) == definition, f"Unexpected Sansa action mapping: {name}={actual}")
    actions = (ROOT / "apps/plugins/lib/pluginlib_actions.c").read_text(encoding="utf-8")
    action_branch = re.search(
        r"#elif \(CONFIG_KEYPAD == GIGABEAT_PAD.*?SANSA_CLIP_PAD.*?(?=#elif)", actions, re.DOTALL)
    require(action_branch is not None, "No verified Sansa pluginlib_actions branch")
    for action, expression in (
            ("PLA_CANCEL", "BUTTON_POWER|BUTTON_REL"), ("PLA_EXIT", "BUTTON_POWER|BUTTON_REPEAT"),
            ("PLA_SELECT", "BUTTON_SELECT"), ("PLA_SELECT_REPEAT", "BUTTON_SELECT|BUTTON_REPEAT")):
        require(re.search(r"\{" + action + r",\s*" + re.escape(expression) + r"\s*,", action_branch.group()),
                f"Unexpected pluginlib action mapping: {action}")
    metronome = (ROOT / "apps/plugins/metronome.c").read_text(encoding="utf-8")
    require(not re.search(r"^#define HAVE_SCROLLWHEEL\b", configuration, re.MULTILINE),
            "Scrollwheel metronome volume mapping requires a separate target check")
    for macro, action in (("METRONOME_VOL_UP", "PLA_UP"), ("METRONOME_RIGHT", "PLA_RIGHT"),
                          ("METRONOME_QUIT", "PLA_EXIT")):
        require(re.search(r"^#define " + macro + r"\s+" + action + r"\s*$", metronome, re.MULTILINE),
                f"Unexpected metronome action binding: {macro}")
    dice = (ROOT / "apps/plugins/dice.c").read_text(encoding="utf-8")
    require(re.search(r"^#define DICE_ROLL\s+PLA_SELECT\s*$", dice, re.MULTILINE) and
            re.search(r"^#define DICE_QUIT\s+PLA_CANCEL\s*$", dice, re.MULTILINE),
            "Unexpected non-iPod dice action bindings")
    return keyboard


def copy_alias(source, destination, build, runtime, report):
    source = contained(source, build)
    require(source.suffix == ".rock" and source.is_file(), "Alias source must be a compiled .rock module")
    require(not os.path.lexists(destination) and runtime in destination.resolve().parents,
            "Refusing occupied or escaping plugin alias destination")
    with source.open("rb") as module:
        require(module.read(2) == b"MZ", "Windows plugin alias requires a PE module")
    before = digest(source)
    shutil.copy2(source, destination)
    require(digest(source) == before == digest(destination), "Plugin alias copy/hash changed")
    report["copies"].append({"source": str(source), "destination": str(destination), "sha256": before,
                              "purpose": "root Files alias of the exact compiled plugin for GUI regression",
                              "retained_after_test": True})


def synthetic_config(language, voice_files_disabled=False):
    return (
        f"lang: /.rockbox/langs/{language}.lng\n"
        "start in screen: root\nshow files: all\nsort case: off\n"
        + voice_file_settings(voice_files_disabled, directory="spell", filename="spell")
        + "talk dir clip: off\ntalk file clip: off\ntts enabled: on\ntts language: system\n"
        "tts variant: \ntts rate: 175\ntts pitch: 50\ntts volume: 100\ntts range: 50\n"
        "tts wordgap: 0\nvolume: -25\nbacklight filters first keypress: off\n"
    )


def plugin_aliases(plugins):
    require(bool(plugins) and len(set(plugins)) == len(plugins), "Plugin names must be nonempty and unique")
    require(all(re.fullmatch(r"[a-z0-9_-]+", plugin) for plugin in plugins), "Unsafe plugin module name")
    return {name: f"{index:03d} {name}.rock" for index, name in enumerate(plugins, 1)}


def prepare_plugins_fixture(build, results, language, report, loan, target,
                            plugins=PLUGINS, required_labels=REQUIRED_LABELS, *, voice_files_disabled=False):
    copied = {}
    runtime, disk, unused_labels = prepare_fixture(
        build, results, language, copied, loan, target, voice_files_disabled=voice_files_disabled)
    report.update({name: copied[name] for name in ("fixture", "copies", "build_features", "catalog_inputs")})
    for item in report["copies"]:
        item["purpose"] = "isolated plugin GUI regression using shared immutable-resource fixture copier"
    voices, displayed = catalog_labels(build, language), display_labels(build, language)
    labels = {name: voices.get(name) or displayed.get(name)
              for name in dict.fromkeys(("LANG_DIR_BROWSER",) + tuple(required_labels))}
    require(all(labels.values()), f"Missing compiled plugin labels: {[name for name in labels if not labels[name]]}")
    report["labels"] = labels
    report["voice_files_disabled"] = voice_files_disabled
    report["keyboard_map"] = target_keyboard_map(target)
    for extension in ("lng", "vstrings"):
        installed = disk / ".rockbox/langs" / f"{language}.{extension}"
        require(digest(installed) == digest(build / "apps/lang" / f"{language}.{extension}"),
                f"Installed {language}.{extension} is stale")
    modules = contained(build / "simdisk/.rockbox/rocks", build)
    report["aliases"] = plugin_aliases(plugins)
    for plugin in plugins:
        candidates = list(modules.rglob(f"{plugin}.rock"))
        require(len(candidates) == 1, f"Expected one installed {plugin}.rock, found {len(candidates)}")
        copy_alias(candidates[0], disk / report["aliases"][plugin], build, runtime, report)
    write_json(runtime / ".tts-plugins-gui-fixture.json", {
        "suite": "plugins", "purpose": "Synthetic profiles/resources only; no user profile copied",
        "source_build": str(build), "language": language,
        "voice_files_disabled": voice_files_disabled,
        "base_copier": "test_tts_recorder_gui.prepare_fixture; generated recorder config replaced before launch",
    })
    return runtime, disk, labels


class PluginDriver(RecorderProbe):
    def __init__(self, process, window, environment, runtime, report, timeout, plugin, keyboard):
        super().__init__(process, window, environment, runtime, report, timeout)
        self.plugin = plugin
        self.keyboard = keyboard
        self.pcm = Path(environment["SDL_DISKAUDIOFILE"])
        self.held = set()
        self.pcm_attribution = "unattributed"

    def check_process(self):
        require(self.process.poll() is None,
                f"Plugin simulator {self.plugin} exited unexpectedly: {self.process.returncode}")

    def press(self, key, hold=0.10):
        self.check_process()
        self.held.add(key)
        try:
            send_key(self.process.pid, self.window, key, True, self.environment)
            time.sleep(hold)
        finally:
            if self.process.poll() is None:
                send_key(self.process.pid, self.window, key, False, self.environment)
            self.held.discard(key)

    def speech(self, name, action=None, fragments=(), numbers=(), initial=False, requirement=None,
               pcm_attribution=None):
        attribution = pcm_attribution or self.pcm_attribution
        require(attribution in ("speech_only", "mixed", "unattributed"), "Unknown PCM attribution policy")
        before = len(self.report["checks"])
        try:
            observation = self.capture(
                f"{self.plugin}: {name}", action,
                lambda segments: speech_matches(segments, fragments, numbers), initial=initial)
            require(speech_matches(observation["utterances"], fragments, numbers),
                    f"Expected plugin speech was logged but not submitted for synthesis: {name}")
            return observation
        except Exception as error:
            if len(self.report["checks"]) > before:
                self.report["checks"][-1].update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            for check in self.report["checks"][before:]:
                check.update(plugin=self.plugin, suite="plugins", speech_required=True,
                             expected_fragments=list(fragments), expected_numbers=list(numbers),
                             requirement=requirement, pcm_file=str(self.pcm),
                             pcm_attribution=attribution)

    def seek(self, label, maximum=20):
        recent = logged_phrases(self.text())
        if recent and label in recent[-1]:
            return
        for attempt in range(maximum):
            observation = self.speech(f"seek {label}: Down {attempt + 1}",
                                      lambda: self.press(self.keyboard["BUTTON_DOWN"]))
            if speech_matches(observation["segments"], (label,)):
                require(speech_matches(observation["utterances"], (label,)), "Selected file never reached synthesis")
                return
        raise AssertionError(f"Cannot locate spoken row: {label}")

    def navigate_to_alias(self, labels):
        self.speech("startup", initial=True)
        expected_language = "pl" if self.report["language"] == "polski" else "en"
        require(f"TTS parameters: language={expected_language} " in self.text(), "Unexpected startup voice language")
        self.seek(labels["LANG_DIR_BROWSER"])
        self.speech("enter Files", lambda: self.press(self.keyboard["BUTTON_SELECT"]))
        self.seek(self.report["aliases"][self.plugin].removesuffix(".rock"))
        return lambda: self.press(self.keyboard["BUTTON_SELECT"])

    def exit_to_root(self, labels, hold=0.10):
        def leave_to_root():
            self.press(self.keyboard["BUTTON_POWER"], hold)
            time.sleep(0.4)
            self.press(self.keyboard["BUTTON_LEFT"])

        return self.speech("exit plugin and return to root Files", leave_to_root,
                           fragments=(labels["LANG_DIR_BROWSER"],), requirement="exit_root")


def exercise_plugin(probe, labels):
    probe.pcm_attribution = "speech_only"
    key = probe.keyboard
    activate = probe.navigate_to_alias(labels)
    if probe.plugin == "calculator":
        probe.speech("initial keypad focus", activate, numbers=(5,), requirement="initial_focus")
        probe.speech("move to digit six", lambda: probe.press(key["BUTTON_RIGHT"]),
                     numbers=(6,), requirement="functional_action")
        probe.speech("activate digit and read result", activate,
                     fragments=(labels["LANG_CALCULATOR_RESULT"],), numbers=(6,), requirement="functional_action")
    elif probe.plugin == "stopwatch":
        probe.speech("initial paused timer", activate,
                     fragments=(labels["LANG_COUNTDOWN_TIMER_PAUSED"], labels["LANG_ELAPSED"]),
                     numbers=(0,), requirement="initial_focus")
        probe.speech("start timer", lambda: probe.press(key["BUTTON_RIGHT"]),
                     fragments=(labels["LANG_COUNTDOWN_TIMER_RUNNING"], labels["LANG_ELAPSED"]),
                     requirement="functional_action")
        observation = probe.speech("create first lap", activate,
                                   fragments=(labels["LANG_STOPWATCH_LAP"], labels["LANG_ELAPSED"]),
                                   numbers=(1,), requirement="functional_action")
        elapsed = " ".join(observation["segments"]).split(labels["LANG_ELAPSED"], 1)[1]
        if not any(float(value) > 0 for value in numeric_values([elapsed])):
            observation.update(status="failed", error="Lap did not announce positive elapsed time")
            raise AssertionError(observation["error"])
    elif probe.plugin == "metronome":
        probe.speech("initial paused controls", activate,
                     fragments=(labels["LANG_COUNTDOWN_TIMER_PAUSED"], labels["LANG_METRONOME_TEMPO"],
                                labels["LANG_METRONOME_METER"], labels["LANG_VOLUME"]),
                     numbers=(120, 4, -25), requirement="initial_focus")
        probe.speech("change paused tempo", lambda: probe.press(key["BUTTON_RIGHT"]),
                     fragments=(labels["LANG_METRONOME_TEMPO"],), numbers=(121,), requirement="functional_action")
        probe.speech("change paused volume", lambda: probe.press(key["BUTTON_UP"]),
                     fragments=(labels["LANG_VOLUME"],), numbers=(-24,), requirement="functional_action")
    else:
        probe.speech("initial Roll menu focus", activate,
                     fragments=(labels["LANG_DICE_ROLL"],), requirement="initial_focus")
        for attempt in range(2):
            observation = probe.speech(f"roll default die {attempt + 1}", activate,
                                       fragments=(labels["LANG_DICE_RESULTS"], labels["LANG_DICE_TOTAL"]),
                                       requirement="functional_action")
            try:
                observation["dice_result"] = validate_dice_result(observation["segments"], labels)
                require(validate_dice_result(observation["utterances"], labels) == observation["dice_result"],
                        "Dice synthesis text differs from the logged result")
            except AssertionError as error:
                observation.update(status="failed", error=str(error))
                raise

    probe.exit_to_root(labels, 0.75 if probe.plugin == "metronome" else 0.10)


def verify_pcm_checks(checks):
    for check in checks:
        if not check.get("speech_required"):
            continue
        path = Path(check["pcm_file"])
        start, end = check.get("pcm_start", -1), check.get("pcm_end", -1)
        valid = path.is_file() and 0 <= start <= end <= path.stat().st_size
        if not valid:
            check.update(status="failed", pcm_status="failed", pcm_error="Missing PCM file or invalid action bounds")
            continue
        statistics = pcm_summary(path, start, end)
        check.update(pcm=statistics, pcm_status="verified_after_exit")
        if statistics["nonzero_samples"] < 128 or statistics["peak"] < 64:
            check.update(status="failed", pcm_status="failed",
                         pcm_error="Logged speech has no meaningful action-window mixer PCM")
        elif check.get("pcm_attribution", "unattributed") != "speech_only":
            check.update(pcm_status="nonzero_not_attributed",
                         pcm_limitation="Other PCM sources may account for these samples; speech output is not isolated")
            if check["status"] == "passed":
                check["status"] = "partial"


def requirements_complete(checks, plugin):
    selected = [check for check in checks if check.get("plugin") == plugin]
    return (all(check["status"] == "passed" for check in selected) and
            sum(check.get("requirement") == "initial_focus" for check in selected) == 1 and
            sum(check.get("requirement") == "functional_action" for check in selected) >= 2 and
            sum(check.get("requirement") == "exit_root" for check in selected) == 1)


def close_session(probe, session, results, graceful):
    if probe is None:
        return
    try:
        if probe.process.poll() is None:
            for key in set(probe.keyboard.values()) | probe.held:
                send_key(probe.process.pid, probe.window, key, False, probe.environment)
            if graceful:
                shutdown(probe.process, probe.window, probe.environment)
    except Exception as error:
        session["cleanup_error"] = f"{type(error).__name__}: {error}"
    finally:
        if probe.process.poll() is None:
            session["forced_owned_process_cleanup"] = True
            probe.process.terminate()
            try:
                probe.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                probe.process.kill()
                probe.process.wait(timeout=8)
        session["exit_code"] = probe.process.returncode
        if probe.log.exists():
            destination = results / f"{probe.plugin}-simulator.log"
            require(not destination.exists(), "Refusing to overwrite a complete session log")
            probe.log.rename(destination)
            session.update(log=str(destination), log_sha256=digest(destination))
        if probe.pcm.exists():
            session.update(pcm_sha256=digest(probe.pcm), pcm=pcm_summary(probe.pcm))


def run_suite(plugins=PLUGINS, exercise=exercise_plugin, required_labels=REQUIRED_LABELS,
              argv=None, extra_sources=(), after_session=None):
    plugins = tuple(plugins)
    plugin_aliases(plugins)
    require(after_session is None or callable(after_session), "after_session must be callable or None")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--language", choices=("polski", "english"), required=True)
    parser.add_argument("--build-ready", action="store_true", help="Explicit authorization for this completed target build")
    parser.add_argument("--voice-files-disabled", action="store_true",
                        help="Disable recorded menu/file/directory speech and mute recorded voices in the clean TTS fixture")
    parser.add_argument("--timeout", type=float, default=30)
    arguments = parser.parse_args(argv)
    if not arguments.build_ready:
        parser.error("Wait for explicit parent authorization of this target, then pass --build-ready")
    if sys.platform != "win32":
        parser.error("Use native Windows Python, not WSL or Wine")
    if not 10 <= arguments.timeout <= 60:
        parser.error("--timeout must be between 10 and 60 seconds")
    workspace = contained(_project_materials_root(ROOT), ROOT)
    build = contained(arguments.build or workspace / TARGETS[arguments.target], workspace)
    test_root = workspace / "tts-plugins-gui-tests"
    if test_root.exists():
        test_root = contained(test_root, workspace)
    else:
        test_root.mkdir()
    results = test_root / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results.mkdir()
    report = dict(suite="plugins", passed=False, target=arguments.target, language=arguments.language,
                  voice_files_disabled=arguments.voice_files_disabled,
                  source_build=str(build), checks=[], sessions=[], copies=[],
                  source_inputs=[{"source": str(contained(ROOT / name, ROOT)), "sha256": digest(ROOT / name)}
                                 for name in dict.fromkeys(SOURCE_INPUTS + tuple(extra_sources))],
                  limitations=[
                      "One invocation tests one target/language; run both languages on both targets.",
                      "Disk PCM proves mixer output, not WASAPI, intelligibility, human listening, NVDA/UIA or hardware.",
                      "Action boundaries use conservative speech-log settling; PCM is verified only after process exit.",
                      "Metronome remains paused: initial controls, tempo and volume speech only; active-click duplex/timing is untested.",
                      "Recorded voice-file playback is not tested; --voice-files-disabled selects an eSpeak-only fixture.",
                      "Only initial focus, two functional actions and return to root are required per plugin; this is not full UI coverage.",
                  ], artifact_cleanup={"trash": [], "workspace": str(results), "pending_user_decisions": []})
    loan = ExecutableLoan(build, results, report)
    process = runtime = probe = None
    interrupted = False
    print(f"Native Windows plugins GUI evidence: {results}", flush=True)
    try:
        runtime, disk, labels = prepare_plugins_fixture(
            build, results, arguments.language, report, loan, arguments.target, plugins, required_labels,
            voice_files_disabled=arguments.voice_files_disabled)
        for plugin in plugins:
            session = {"plugin": plugin, "status": "in_progress"}
            report["sessions"].append(session)
            probe = process = None
            try:
                require(not (runtime / "simulator.log").exists(), "Previous complete session log was not preserved")
                (disk / ".rockbox/config.cfg").write_text(
                    synthetic_config(arguments.language, arguments.voice_files_disabled), encoding="utf-8")
                environment = dict(os.environ, SDL_VIDEODRIVER="windows", SDL_AUDIODRIVER="disk",
                                   SDL_DISKAUDIOFILE=str(runtime / f"{plugin}-audio.raw"), SDL_DISKAUDIODELAY="12")
                process = subprocess.Popen(
                    [str(runtime / "rockboxui.exe"), "--root", str(disk), "--audiodev",
                     environment["SDL_DISKAUDIOFILE"], "--debugbuttons"], cwd=runtime, env=environment,
                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
                session.update(pid=process.pid, pcm_file=environment["SDL_DISKAUDIOFILE"])
                window = find_window(process.pid, environment)
                probe = PluginDriver(process, window, environment, runtime, report, arguments.timeout,
                                     plugin, report["keyboard_map"])
                native = windows_backend()
                require(native is not None, "Native Windows backend is required before plugin actions")
                native.set_hidden(process.pid, window, True)
                session["native_window_hidden"] = True
                exercise(probe, labels)
                session["status"] = "logged_pending_pcm"
            except (Exception, KeyboardInterrupt) as error:
                session.update(status="failed", error=f"{type(error).__name__}: {error}")
                interrupted = isinstance(error, KeyboardInterrupt)
            finally:
                previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    if probe is not None:
                        close_session(probe, session, results, session["status"] == "logged_pending_pcm")
                    elif process is not None and process.poll() is None:
                        session["forced_owned_process_cleanup"] = True
                        process.terminate()
                        process.wait(timeout=8)
                    configuration = disk / ".rockbox/config.cfg"
                    if configuration.is_file():
                        session["synthetic_profile_after"] = configuration.read_text(encoding="utf-8", errors="replace")
                    if after_session is not None and probe is not None:
                        try:
                            require(probe.process.poll() is not None, "Post-session calibration requires process exit")
                            after_session(probe, session, results)
                        except (Exception, KeyboardInterrupt) as error:
                            session.update(status="failed", after_session_error=f"{type(error).__name__}: {error}")
                            interrupted = interrupted or isinstance(error, KeyboardInterrupt)
                    verify_pcm_checks([check for check in report["checks"] if check.get("plugin") == plugin])
                    session["passed"] = (session["status"] == "logged_pending_pcm" and
                                         requirements_complete(report["checks"], plugin) and
                                         session.get("exit_code") == 0 and not session.get("cleanup_error") and
                                         not session.get("forced_owned_process_cleanup"))
                    session["status"] = "passed" if session["passed"] else "failed"
                    write_json(results / "report.json", report)
                finally:
                    signal.signal(signal.SIGINT, previous_handler)
            if interrupted:
                break
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            if process is not None and process.poll() is None:
                report["forced_owned_process_cleanup"] = True
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=8)
            try:
                loan.restore(process)
            except Exception as error:
                report["executable_restore_error"] = f"{type(error).__name__}: {error}"
                loan.record.update(state="restore_failed", error=str(error))
                loan.save_record()
        finally:
            signal.signal(signal.SIGINT, previous_handler)
        try:
            inputs = report.get("copies", []) + report["source_inputs"] + [
                {"source": item["path"], "sha256": item["sha256"]} for item in report.get("catalog_inputs", [])]
            report["changed_source_assets"] = [item["source"] for item in inputs
                                               if not Path(item["source"]).is_file() or
                                               digest(Path(item["source"])) != item["sha256"]]
            report["failed_checks"] = [check["name"] for check in report["checks"] if check["status"] != "passed"]
            report["passed"] = (len(report["sessions"]) == len(plugins) and
                                all(session.get("passed") for session in report["sessions"]) and
                                not report["failed_checks"] and not report["changed_source_assets"] and
                                not report.get("error") and not report.get("executable_restore_error") and
                                loan.record["restored"])
        except Exception as error:
            report["evidence_error"] = f"{type(error).__name__}: {error}"
        write_json(results / "report.json", report)
    print(json.dumps({"suite": "plugins", "passed": report["passed"],
                      "failed_checks": report.get("failed_checks"),
                      "executable_restored": loan.record["restored"],
                      "report": str(results / "report.json")}, indent=2))
    return 0 if report["passed"] else 1


def main():
    return run_suite()


if __name__ == "__main__":
    raise SystemExit(main())
