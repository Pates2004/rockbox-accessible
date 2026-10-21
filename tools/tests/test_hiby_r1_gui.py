import argparse
import datetime
import json
from pathlib import Path
import re
import sys
import time

from test_tts_bookmarks_gui import (
    GuiProbe, DOCUMENT, READER_ROWS, bookmark_entries, music_properties, open_document,
    prepare_fixture, properties, require, startup, verify_evidence, write_json,
)
from test_tts_recorder_gui import ExecutableLoan, contained, digest
from test_tts_simulator import catalog_labels, send_key
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]


class R1Probe(GuiProbe):
    def press(self, key, hold=0.12):
        if key == "Insert":
            self.unit_chord("Left")
            return
        key = {"space": "Insert", "Escape": "Left"}.get(key, key)
        super().press(key, hold)

    def open_reader_menu(self, labels, key="Right"):
        return super().open_reader_menu(labels, key="Right")

    def unit_chord(self, key):
        self.check_alive()
        try:
            for button in ("Insert", key):
                self.held.add(button)
                send_key(self.process.pid, self.window, button, True, self.environment)
                time.sleep(0.15)
        finally:
            for button in (key, "Insert"):
                if self.process.poll() is None:
                    send_key(self.process.pid, self.window, button, False, self.environment)
                self.held.discard(button)
                time.sleep(0.1)


def exercise(probe, labels, displayed, document, report):
    probe.launch("r1-physical-profile")
    startup(probe, report["language"])
    open_document(probe, labels)
    menu_start = probe.open_reader_menu(labels)
    for index in range(1, len(READER_ROWS)):
        probe.speech(f"R1 text menu row {index}", lambda: probe.press("Down"), labels[READER_ROWS[index]])
    for index in range(len(READER_ROWS) - 2, -1, -1):
        probe.speech(f"R1 text menu return {index}", lambda: probe.press("Up"), labels[READER_ROWS[index]])
    probe.assert_menu_stayed_open(menu_start)
    offset = int(re.findall(r"TTS reader cursor: (\d+)", probe.text())[-1])
    probe.reader_row(labels, 1)
    probe.speech("R1 bookmark submenu", lambda: probe.press("space"), labels["LANG_BOOKMARK_MENU_CREATE"])
    probe.capture("R1 creates text bookmark", lambda: probe.press("space"),
                  lambda text: f"TTS reader bookmark saved: 1 offset={offset}" in text, speech=False)
    local = probe.runtime / "simdisk" / (DOCUMENT + ".bmark")
    recent = probe.runtime / "simdisk/.rockbox/most-recent.bmark"
    entries = bookmark_entries(local)
    require(len(entries) == 1 and entries[0]["offset"] == offset and
            entries[0]["size"] == len(document) and entries[0]["unit"] == 1 and
            entries == bookmark_entries(recent), "R1 bookmark does not match the audible position")
    report["saved_bookmark"] = entries[0]
    probe.cancel("leave R1 bookmark submenu")
    probe.cancel("leave R1 text menu")
    properties(probe, labels, displayed, offset, len(document))
    probe.capture("R1 Next key steps forward through text", lambda: probe.press("Right"),
                  lambda text: re.search(r"TTS reader cursor: (\d+)", text) is not None)
    moved = int(re.findall(r"TTS reader cursor: (\d+)", probe.text())[-1])
    require(moved > offset, "R1 forward step did not advance")
    probe.capture("R1 Play key steps backward through text", lambda: probe.press("Left"),
                  lambda text: re.search(r"TTS reader cursor: (\d+)", text) is not None)
    returned = int(re.findall(r"TTS reader cursor: (\d+)", probe.text())[-1])
    require(returned < moved, "R1 backward step did not move the cursor backward")
    probe.speech("R1 reader lock chord is spoken", lambda: probe.unit_chord("Up"), labels["LANG_KEYLOCK_ON"])
    locked = probe.speech("R1 locked reader rejects cursor navigation", lambda: probe.press("Right"),
                          labels["LANG_KEYLOCK_ON"])
    require("TTS reader cursor:" not in probe.text(locked["log_start"]), "Locked reader moved the cursor")
    probe.speech("R1 reader unlock chord is spoken", lambda: probe.unit_chord("Up"), labels["LANG_KEYLOCK_OFF"])
    probe.capture("R1 volume down tap changes range", lambda: probe.press("Down"),
                  lambda text: "TTS reader unit: 2 " in text)
    probe.capture("R1 volume up tap restores range", lambda: probe.press("Up"),
                  lambda text: "TTS reader unit: 1 " in text)
    probe.local_list(labels)
    probe.speech("R1 existing bookmark context", lambda: probe.press("Right", 1.2),
                 labels["LANG_BOOKMARK_CONTEXT_RESUME"])
    probe.capture("R1 restores saved text position", lambda: probe.press("space"),
                  lambda text: re.search(r"TTS reader bookmark restored: " + str(offset) + r"\s", text)
                  is not None, speech=False)
    probe.close()
    require(bookmark_entries(local) == entries == bookmark_entries(recent), "R1 bookmark changed at shutdown")
    report["checks"].append(dict(name="R1 persistent local and recent text bookmarks", status="passed"))


def main():
    parser = argparse.ArgumentParser(description="Actual native Windows R1 physical-profile/text/bookmark smoke")
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--language", choices=("polski", "english"), default="polski")
    parser.add_argument("--build-ready", action="store_true")
    parser.add_argument("--with-music", action="store_true")
    arguments = parser.parse_args()
    if sys.platform != "win32" or not arguments.build_ready:
        parser.error("Requires native Windows and an explicitly ready development build")
    workspace = project_materials_root(ROOT)
    build = contained(arguments.build, workspace)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results = workspace / "hiby-r1-gui-tests" / stamp
    results.mkdir(parents=True)
    report = dict(passed=False, target="hibyr1", language=arguments.language, source_build=str(build),
                  checks=[], sessions=[], copies=[], limitations=[
                      "Windows keyboard profile and disk PCM only; not physical R1, NVDA/UIA or human listening.",
                      "Touch exploration, gesture editor, Bluetooth and hardware recording are not exercised.",
                      "No installed/user profile is copied; runtime fixtures remain for reproduction."])
    loan = ExecutableLoan(build, results, report)
    probe = R1Probe(results / "fixture", results, report, 40)
    print(f"R1 Windows GUI evidence: {results}", flush=True)
    try:
        runtime, labels, displayed, document = prepare_fixture(build, results, arguments.language, report,
                                                               target_name="hibyr1", voice_files_disabled=True)
        catalog = catalog_labels(build, arguments.language)
        for identifier in ("LANG_KEYLOCK_ON", "LANG_KEYLOCK_OFF"):
            labels[identifier] = catalog.get(identifier) or displayed.get(identifier)
            require(bool(labels[identifier]), f"Missing compiled lock label: {identifier}")
        probe.runtime = runtime
        probe.log = runtime / "simulator.log"
        loan.move_to(runtime)
        exercise(probe, labels, displayed, document, report)
        if arguments.with_music:
            music_properties(probe, labels, displayed, document, report)
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            probe.close(graceful=False)
            loan.restore(probe.process)
            verify_evidence(report)
        except Exception as error:
            report["cleanup_or_evidence_error"] = str(error)
        report["passed"] = bool(report["sessions"]) and loan.record["restored"] and not any(
            key in report for key in ("error", "cleanup_or_evidence_error")) and all(
            check["status"] == "passed" for check in report["checks"])
        report["exe_sha256"] = digest(build / "rockboxui.exe") if loan.record["restored"] else None
        write_json(results / "report.json", report)
    print(json.dumps(dict(passed=report["passed"], error=report.get("error"),
                          report=str(results / "report.json")), ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
