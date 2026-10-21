#include "../rb_espeak.cpp"
#include "../engine/speech.h"

static void require(bool condition, const char *message)
{
    if (!condition)
    {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

struct WorkerState {
    HANDLE entered;
    HANDLE resume;
    int callbacks;
    bool cancel;
    bool nonzero;
};

static int capture(const short *samples, int count, void *user)
{
    WorkerState *state = static_cast<WorkerState *>(user);
    require(samples && count > 0 && count <= 441, "bounded PCM");
    require(espeak_text_locale != NULL, "worker has an explicit locale");
    require(iswalpha(0x0105) && iswupper(0x017b) && towlower(0x017b) == 0x017c,
            "Polish wide classification and case folding");
    require(strcmp(setlocale(LC_ALL, NULL), "C") == 0, "callback CRT locale unchanged");
    require((towlower)(0x017b) == 0x017b, "implicit CRT case mapping unchanged");
    for (int index = 0; index < count; ++index)
        state->nonzero |= samples[index] != 0;
    if (++state->callbacks == 1)
    {
        require(SetEvent(state->entered), "signal callback");
        require(WaitForSingleObject(state->resume, 30000) == WAIT_OBJECT_0,
                "resume callback");
        require(rb_espeak_synth("test", "pl", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                               capture, user) == RB_ESPEAK_BUSY, "reject callback reentry");
    }
    return state->cancel;
}

static DWORD WINAPI synthesize_thread(void *user)
{
    WorkerState *state = static_cast<WorkerState *>(user);
    require(espeak_text_locale == NULL, "new worker has no inherited selector");
    int mode = _configthreadlocale(0);
    int result = rb_espeak_synth(u8"Zażółć gęślą jaźń. ŻÓŁĆ, ĄĘĆŁŃÓŚŹŻ.", "pl", "m3",
                                  175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE, capture, state);
    require(result == (state->cancel ? RB_ESPEAK_ABORTED : RB_ESPEAK_OK), "worker synthesis result");
    require(espeak_text_locale == NULL, "worker selector restored after synthesis");
    require(_configthreadlocale(0) == mode, "CRT thread locale mode unchanged");
    require(strcmp(setlocale(LC_ALL, NULL), "C") == 0, "worker CRT locale restored");
    return 0;
}

int wmain(int argc, wchar_t **argv)
{
    require(argc == 3, "usage: test_windows_platform data-parent output-directory");
    char parent[MAX_PATH * 3];
    require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, argv[1], -1,
                               parent, sizeof(parent), NULL, NULL) > 0, "UTF-8 parent");
    require(setlocale(LC_ALL, "C") != NULL, "set main baseline locale");
    int mode = _configthreadlocale(0);
    require(rb_espeak_init("") == RB_ESPEAK_INVALID_ARGUMENT, "reject empty root");
    require(rb_espeak_init("\xc3\x28") < 0, "reject malformed UTF-8 path");
    char excessive[512];
    memset(excessive, 'a', sizeof(excessive) - 1);
    excessive[sizeof(excessive) - 1] = 0;
    require(rb_espeak_init(excessive) < 0, "reject excessive path");
    require(rb_espeak_init(parent) == 22050, "initialize after rejected roots");
    require(espeak_text_locale == NULL, "initialization restores selector");
    require(strcmp(setlocale(LC_ALL, NULL), "C") == 0, "initialization preserves global locale");
    require(rb_espeak_voice_count(false) == 54 && rb_espeak_voice_count(true) == 105,
            "complete language and variant lists");
    _locale_t previous = _create_locale(LC_CTYPE, "English_United States.1252");
    require(previous != NULL, "create alternate caller selector");
    espeak_text_locale = previous;
    {
        LocaleGuard outer;
        require(outer.valid() && espeak_text_locale == text_locale, "select synthesis locale");
        {
            LocaleGuard inner;
            require(inner.valid(), "nested locale guard");
        }
        require(espeak_text_locale == text_locale, "nested guard restores outer selector");
    }
    require(espeak_text_locale == previous, "guard restores caller selector");
    espeak_text_locale = NULL;
    _free_locale(previous);
    require(SetCurrentDirectoryW(argv[2]), "change working directory after initialization");
    require(rb_espeak_init(parent) == 22050, "resolved parent remains idempotent");
    const char *filename = u8"żółć-中文.txt";
    const char contents[] = "UTF-8 IO\n";
    FILE *output = espeak_fopen(filename, "wb");
    require(output != NULL, "open Unicode filename for writing");
    require(fwrite(contents, 1, sizeof(contents) - 1, output) == sizeof(contents) - 1,
            "write Unicode filename");
    require(fclose(output) == 0, "close Unicode filename");
    require(GetFileLength(filename) == sizeof(contents) - 1, "engine stat uses UTF-8 filenames");
    FILE *input = espeak_fopen(filename, "rb");
    require(input != NULL, "open Unicode filename for reading");
    char restored[sizeof(contents)] = {};
    require(fread(restored, 1, sizeof(restored) - 1, input) == sizeof(contents) - 1 &&
            strcmp(restored, contents) == 0, "read Unicode filename without ACP conversion");
    require(fclose(input) == 0, "close Unicode input");
    for (int iteration = 0; iteration < 3; ++iteration)
    {
        WorkerState state = {CreateEventW(NULL, TRUE, FALSE, NULL),
                             CreateEventW(NULL, TRUE, FALSE, NULL), 0, iteration == 1, false};
        require(state.entered && state.resume, "create test events");
        HANDLE worker = CreateThread(NULL, 0, synthesize_thread, &state, 0, NULL);
        require(worker != NULL, "create test worker");
        require(WaitForSingleObject(state.entered, 30000) == WAIT_OBJECT_0, "worker reaches callback");
        require(espeak_text_locale == NULL, "worker selector is thread-local");
        require(strcmp(setlocale(LC_ALL, NULL), "C") == 0, "global locale during synthesis");
        require((towlower)(0x017b) == 0x017b, "main case mapping during synthesis");
        require(rb_espeak_validate_voice("pl", "m3") == RB_ESPEAK_OK, "concurrent immutable validation");
        require(rb_espeak_synth("test", "pl", "", 175, 50, 100, 50, 0, RB_ESPEAK_PUNCT_NONE,
                               capture, &state) == RB_ESPEAK_BUSY, "reject concurrent synthesis");
        require(SetEvent(state.resume), "release worker callback");
        require(WaitForSingleObject(worker, 30000) == WAIT_OBJECT_0, "worker completes");
        DWORD status;
        require(GetExitCodeThread(worker, &status) && status == 0, "worker exit status");
        require(state.callbacks > 0 && (state.cancel || state.nonzero), "worker PCM output");
        require(!state.cancel || state.callbacks == 1, "cancellation emits no later callback");
        CloseHandle(worker);
        CloseHandle(state.entered);
        CloseHandle(state.resume);
    }
    require(_configthreadlocale(0) == mode, "main locale mode unchanged");
    puts("PASS: UTF-8 paths, Polish Unicode, TLS isolation/restoration, concurrent rejection, abort/recovery, cwd independence");
    return 0;
}
