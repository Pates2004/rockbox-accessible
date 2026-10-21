#include "rb_espeak.h"
#include "engine/speak_lib.h"
#include "espeak_file.h"

#ifndef RB_ESPEAK_HAVE_SONIC
#define RB_ESPEAK_HAVE_SONIC 1
#endif
#if RB_ESPEAK_HAVE_SONIC
#include "sonic/sonic.h"
#endif

#ifdef RB_ESPEAK_NATIVE
#include "native/native_runtime.h"
#else
#include <atomic>
#endif
#include <ctype.h>
#include <dirent.h>
#include <limits.h>
#include <locale.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <wctype.h>
#include "espeak_locale.h"

#ifdef _WIN32
thread_local _locale_t espeak_text_locale;
#endif

namespace {

struct VoiceChoice {
    char id[40];
    char name[96];
    char filename[40];
    char dictionary[40];
};

VoiceChoice language_choices[128];
VoiceChoice variant_choices[256];
int language_count;
int variant_count;
int sample_rate;
char data_directory[150];
char initialized_parent[150];
#ifndef RB_ESPEAK_NATIVE
#ifdef _WIN32
_locale_t text_locale;
#else
locale_t text_locale;
#endif
std::atomic<bool> ready(false);
std::atomic_flag engine_busy = ATOMIC_FLAG_INIT;
#endif
rb_espeak_callback active_callback;
rb_espeak_position_callback active_position_callback;
bool active_has_audio;
size_t active_text_characters;
void *active_user;
bool callback_aborted;

class EngineGuard {
public:
#ifdef RB_ESPEAK_NATIVE
    EngineGuard() : acquired(rb_espeak_engine_acquire()) {}
    ~EngineGuard() { if (acquired) rb_espeak_engine_release(); }
#else
    EngineGuard() : acquired(!engine_busy.test_and_set(std::memory_order_acquire)) {}
    ~EngineGuard() { if (acquired) engine_busy.clear(std::memory_order_release); }
#endif
    bool acquired;
};

bool engine_ready()
{
#ifdef RB_ESPEAK_NATIVE
    return rb_espeak_engine_ready();
#else
    return ready.load(std::memory_order_acquire);
#endif
}

class LocaleGuard {
public:
#if defined(RB_ESPEAK_NATIVE)
    LocaleGuard() = default;
    bool valid() const
    {
        return iswalpha(0x0105) && towlower(0x017b) == 0x017c;
    }
#elif defined(_WIN32)
    LocaleGuard() : previous(espeak_text_locale)
    {
        espeak_text_locale = text_locale;
    }
    ~LocaleGuard() { espeak_text_locale = previous; }
    bool valid() const
    {
        return espeak_text_locale && iswalpha(0x0105) && towlower(0x017b) == 0x017c;
    }
private:
    _locale_t previous;
#else
    LocaleGuard() : previous(uselocale(text_locale)) {}
    ~LocaleGuard() { if (previous) uselocale(previous); }
    bool valid() const { return previous != NULL; }
private:
    locale_t previous;
#endif
    LocaleGuard(const LocaleGuard &) = delete;
    LocaleGuard &operator=(const LocaleGuard &) = delete;
};

bool resolve_parent(const char *parent, char *resolved, size_t capacity)
{
#if defined(RB_ESPEAK_NATIVE)
    EspeakFileInfo details;
    size_t length = strlen(parent);
    if (parent[0] != '/' || length >= capacity ||
        espeak_stat(parent, &details) != 0 || !S_ISDIR(details.st_mode))
        return false;
    memcpy(resolved, parent, length + 1);
    return true;
#elif defined(_WIN32)
    wchar_t wide_parent[MAX_PATH];
    wchar_t final_path[MAX_PATH];
    if (!espeak_wide_path(parent, wide_parent, MAX_PATH))
        return false;
    HANDLE directory = CreateFileW(wide_parent, 0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
        OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL);
    if (directory == INVALID_HANDLE_VALUE)
        return false;
    BY_HANDLE_FILE_INFORMATION details;
    bool is_directory = GetFileInformationByHandle(directory, &details) &&
                        (details.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY);
    DWORD length = GetFinalPathNameByHandleW(directory, final_path, MAX_PATH,
                                            FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
    CloseHandle(directory);
    if (!is_directory || !length || length >= MAX_PATH)
        return false;
    wchar_t *path = final_path;
    if (wcsncmp(path, L"\\\\?\\UNC\\", 8) == 0)
    {
        path += 6;
        path[0] = L'\\';
    }
    else if (wcsncmp(path, L"\\\\?\\", 4) == 0)
        path += 4;
    return WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, path, -1,
                               resolved, static_cast<int>(capacity), NULL, NULL) != 0;
#else
    (void)capacity;
    return realpath(parent, resolved) != NULL;
#endif
}

bool copy_text(char *destination, size_t capacity, const char *source)
{
    size_t length = strlen(source);
    if (length >= capacity)
        return false;
    memcpy(destination, source, length + 1);
    return true;
}

bool join_path(char *destination, size_t capacity, const char *parent,
               const char *child)
{
    int length = snprintf(destination, capacity, "%s/%s", parent, child);
    return length >= 0 && static_cast<size_t>(length) < capacity;
}

bool readable_file(const char *path, size_t minimum, size_t *length = NULL)
{
    EspeakFileInfo details;
    if (espeak_stat(path, &details) != 0 || !S_ISREG(details.st_mode) ||
        details.st_size < static_cast<int64_t>(minimum) ||
        details.st_size > 64 * 1024 * 1024)
        return false;
    FILE *stream = espeak_fopen(path, "rb");
    if (!stream)
        return false;
    fclose(stream);
    if (length)
        *length = static_cast<size_t>(details.st_size);
    return true;
}

uint32_t little_endian_word(const unsigned char *bytes)
{
    return static_cast<uint32_t>(bytes[0]) |
           (static_cast<uint32_t>(bytes[1]) << 8) |
           (static_cast<uint32_t>(bytes[2]) << 16) |
           (static_cast<uint32_t>(bytes[3]) << 24);
}

bool validate_dictionary(const char *dictionary)
{
    if (!dictionary[0] || strspn(dictionary, "abcdefghijklmnopqrstuvwxyz0123456789_-") != strlen(dictionary))
        return false;
    char path[256];
    snprintf(path, sizeof(path), "%s/%s_dict", data_directory, dictionary);
    size_t length;
    if (!readable_file(path, 1033, &length))
        return false;
    FILE *stream = espeak_fopen(path, "rb");
    if (!stream)
        return false;
    unsigned char header[8];
    bool valid = fread(header, 1, sizeof(header), stream) == sizeof(header);
    if (valid)
    {
        uint32_t rules_offset = little_endian_word(header + 4);
        valid = little_endian_word(header) == 1024 &&
                rules_offset >= 1032 && rules_offset < length;
        for (int bucket = 0; valid && bucket < 1024; ++bucket)
        {
            for (;;)
            {
                long position = ftell(stream);
                if (position < 0 || static_cast<uint32_t>(position) >= rules_offset)
                {
                    valid = false;
                    break;
                }
                int entry_length = fgetc(stream);
                if (entry_length == 0)
                    break;
                if (entry_length < 2 || static_cast<uint32_t>(position) +
                    static_cast<unsigned>(entry_length) > rules_offset ||
                    fseek(stream, entry_length - 1, SEEK_CUR) != 0)
                {
                    valid = false;
                    break;
                }
            }
        }
    }
    fclose(stream);
    return valid;
}

bool validate_core_data()
{
    const char *files[] = {"phondata", "phonindex", "phontab", "intonations"};
    const size_t minimum[] = {8, 2, 4, 1};
    char path[256];
    for (size_t index = 0; index < sizeof(files) / sizeof(files[0]); ++index)
        if (!join_path(path, sizeof(path), data_directory, files[index]) ||
            !readable_file(path, minimum[index]))
            return false;
    join_path(path, sizeof(path), data_directory, "phondata");
    FILE *stream = espeak_fopen(path, "rb");
    if (!stream)
        return false;
    unsigned char header[4];
    bool valid = fread(header, 1, sizeof(header), stream) == sizeof(header) &&
                 little_endian_word(header) == 0x014404;
    fclose(stream);
    return valid;
}

int choice_compare(const void *left, const void *right)
{
    const VoiceChoice *first = static_cast<const VoiceChoice *>(left);
    const VoiceChoice *second = static_cast<const VoiceChoice *>(right);
    int order = strcmp(first->name, second->name);
    return order ? order : strcmp(first->id, second->id);
}

bool read_choice(const char *relative, const char *basename, bool variants)
{
    if ((!variants && strcmp(basename, "default") == 0) ||
        strchr(basename, '+') || strchr(basename, '\\'))
        return true;
    VoiceChoice choice = {};
    if (!copy_text(choice.id, sizeof(choice.id), basename) ||
        !copy_text(choice.filename, sizeof(choice.filename), relative) ||
        (variants && strlen(basename) > 16))
        return false;
    char path[512];
    if (snprintf(path, sizeof(path), "%s/voices/%s", data_directory, relative) >= static_cast<int>(sizeof(path)))
        return false;
    FILE *stream = espeak_fopen(path, "r");
    if (!stream)
        return false;
    char line[512];
    bool has_language = false;
    bool has_variant = false;
    bool mbrola = false;
    bool valid = true;
    while (fgets(line, sizeof(line), stream))
    {
        char *comment = strstr(line, "//");
        if (comment)
            *comment = 0;
        char *keyword = line;
        while (isspace(static_cast<unsigned char>(*keyword)))
            ++keyword;
        if (!*keyword || *keyword == '#')
            continue;
        char *value = keyword;
        while (*value && !isspace(static_cast<unsigned char>(*value)))
            ++value;
        if (*value)
            *value++ = 0;
        while (isspace(static_cast<unsigned char>(*value)))
            ++value;
        size_t length = strlen(value);
        while (length && isspace(static_cast<unsigned char>(value[length - 1])))
            value[--length] = 0;
        if (strcmp(keyword, "name") == 0)
            valid = copy_text(choice.name, sizeof(choice.name), value) && valid;
        else if (strcmp(keyword, "language") == 0 && !has_language)
        {
            char language[40] = {};
            if (sscanf(value, "%39s", language) == 1)
            {
                has_language = true;
                has_variant = strcmp(language, "variant") == 0;
                char *dialect = strchr(language, '-');
                if (dialect)
                    *dialect = 0;
                copy_text(choice.dictionary, sizeof(choice.dictionary), language);
            }
        }
        else if (strcmp(keyword, "dictionary") == 0)
            sscanf(value, "%39s", choice.dictionary);
        else if (strcmp(keyword, "mbrola") == 0)
            mbrola = true;
    }
    valid = valid && !ferror(stream);
    fclose(stream);
    if (!valid)
        return false;
    if (!has_language || has_variant != variants || mbrola)
        return true;
    if (!variants && !validate_dictionary(choice.dictionary))
        return true;
    if (!choice.name[0])
        copy_text(choice.name, sizeof(choice.name), choice.id);
    VoiceChoice *choices = variants ? variant_choices : language_choices;
    int &count = variants ? variant_count : language_count;
    int capacity = variants ? 256 : 128;
    if (count >= capacity)
        return false;
    for (int index = 0; index < count; ++index)
        if (strcmp(choices[index].id, choice.id) == 0)
            return false;
    choices[count++] = choice;
    return true;
}

bool scan_choices(const char *relative, bool variants, int depth)
{
    if (depth > 4)
        return false;
    char path[512];
    if (snprintf(path, sizeof(path), "%s/voices/%s", data_directory, relative) >= static_cast<int>(sizeof(path)))
        return false;
#ifdef _WIN32
    wchar_t wide_path[MAX_PATH];
    if (!espeak_wide_path(path, wide_path, MAX_PATH))
        return false;
    _WDIR *directory = _wopendir(wide_path);
#else
    DIR *directory = opendir(path);
#endif
    if (!directory)
        return variants && depth == 0;
    bool valid = true;
#ifdef _WIN32
    struct _wdirent *entry;
    while (valid && (entry = _wreaddir(directory)) != NULL)
#else
    struct dirent *entry;
    while (valid && (entry = readdir(directory)) != NULL)
#endif
    {
#ifdef _WIN32
        char name[MAX_PATH * 3];
        if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, entry->d_name, -1,
                                name, sizeof(name), NULL, NULL))
        {
            valid = false;
            break;
        }
#else
        const char *name = entry->d_name;
#endif
        if (name[0] == '.' || (!variants &&
            (strcmp(name, "!v") == 0 || strcmp(name, "mb") == 0)))
            continue;
        char child[128];
        int length = snprintf(child, sizeof(child), "%s%s%s", relative,
                              relative[0] ? "/" : "", name);
        if (length < 0 || static_cast<size_t>(length) >= sizeof(child))
        {
            valid = false;
            break;
        }
        snprintf(path, sizeof(path), "%s/voices/%s", data_directory, child);
        EspeakFileInfo details;
        if (espeak_lstat(path, &details) != 0)
            valid = false;
        else if (S_ISDIR(details.st_mode))
            valid = scan_choices(child, variants, depth + 1);
        else if (S_ISREG(details.st_mode))
            valid = read_choice(child, name, variants);
    }
#ifdef _WIN32
    _wclosedir(directory);
#else
    closedir(directory);
#endif
    return valid;
}

const VoiceChoice *find_choice(bool variants, const char *identifier)
{
    if (!identifier)
        return NULL;
    const VoiceChoice *choices = variants ? variant_choices : language_choices;
    int count = variants ? variant_count : language_count;
    for (int index = 0; index < count; ++index)
        if (strcmp(choices[index].id, identifier) == 0)
            return &choices[index];
    return NULL;
}

#if RB_ESPEAK_HAVE_SONIC
struct SonicOutput {
    struct Position {
        int character;
        int milliseconds;
    };
    sonicStream stream = NULL;
    int adjusted_rate = 0;
    uint64_t output_samples = 0;
    Position positions[256];
    unsigned head = 0;
    unsigned pending = 0;
    int last_character = 0;
    int last_milliseconds = 0;
    bool failed = false;

    ~SonicOutput() { if (stream) sonicDestroyStream(stream); }

    bool prepare(int rate)
    {
        adjusted_rate = espeak_SetSonicRate(rate);
        if (adjusted_rate <= 0)
            return false;
        stream = sonicCreateStream(sample_rate, 1);
        if (!stream)
            return false;
        sonicSetSpeed(stream, static_cast<float>(adjusted_rate) / espeakRATE_NORMAL);
        return true;
    }

    bool queue(int character, int milliseconds)
    {
        if (character <= last_character || milliseconds < 0)
            return true;
        if (pending == sizeof(positions) / sizeof(positions[0]))
            return false;
        int mapped = static_cast<int>((static_cast<int64_t>(milliseconds) *
            espeakRATE_NORMAL + adjusted_rate - 1) / adjusted_rate);
        if (mapped < last_milliseconds)
            mapped = last_milliseconds;
        positions[(head + pending) % 256] = { character, mapped };
        ++pending;
        last_character = character;
        last_milliseconds = mapped;
        return true;
    }

    void emit_positions(uint64_t samples, bool final)
    {
        uint64_t milliseconds = samples * 1000 / sample_rate;
        int end = milliseconds > INT_MAX ? INT_MAX : static_cast<int>(milliseconds);
        while (pending && (positions[head].milliseconds <= end || final))
        {
            Position position = positions[head];
            if (position.milliseconds > end)
                position.milliseconds = end;
            active_position_callback(position.character, position.milliseconds, active_user);
            head = (head + 1) % 256;
            --pending;
        }
    }

    bool drain(bool final)
    {
        short output[441];
        int available;
        while ((available = sonicSamplesAvailable(stream)) >= 441 ||
               (final && available > 0))
        {
            int requested = available < 441 ? available : 441;
            int count = sonicReadShortFromStream(stream, output, requested);
            if (count != requested)
                return false;
            uint64_t end = output_samples + count;
            emit_positions(end, final && sonicSamplesAvailable(stream) == 0);
            if (active_callback(output, count, active_user) != 0)
            {
                callback_aborted = true;
                return true;
            }
            output_samples = end;
        }
        if (final)
            emit_positions(output_samples, true);
        return true;
    }
};

SonicOutput *active_sonic;
#endif

class SynthesisReset {
public:
    SynthesisReset() { espeak_SetSonicRate(0); }
    ~SynthesisReset()
    {
        espeak_SetSonicRate(0);
        active_callback = NULL;
        active_position_callback = NULL;
        active_user = NULL;
#if RB_ESPEAK_HAVE_SONIC
        active_sonic = NULL;
#endif
    }
};

int receive_pcm(short *samples, int count, espeak_EVENT *events)
{
    if (callback_aborted)
        return 1;
#if RB_ESPEAK_HAVE_SONIC
    if (active_sonic && active_sonic->failed)
        return 1;
#endif
    if (samples && !active_has_audio)
        for (int index = 0; index < count; ++index)
            if (samples[index])
            {
                active_has_audio = true;
                break;
            }
    if (active_position_callback && events)
        for (espeak_EVENT *event = events; event->type != espeakEVENT_LIST_TERMINATED;
             ++event)
            if (event->type == espeakEVENT_WORD && event->length > 0 &&
                event->text_position > 0 &&
                static_cast<size_t>(event->text_position) <= active_text_characters)
            {
#if RB_ESPEAK_HAVE_SONIC
                if (active_sonic)
                {
                    if (!active_sonic->queue(event->text_position, event->audio_position))
                    {
                        active_sonic->failed = true;
                        return 1;
                    }
                }
                else
#endif
                    active_position_callback(event->text_position, event->audio_position,
                                             active_user);
            }
#if RB_ESPEAK_HAVE_SONIC
    if (active_sonic)
    {
        if (samples && count > 0 &&
            (!sonicWriteShortToStream(active_sonic->stream, samples, count) ||
             !active_sonic->drain(false)))
            active_sonic->failed = true;
        return active_sonic->failed || callback_aborted ? 1 : 0;
    }
#endif
    if (samples && count > 0 && active_callback &&
        active_callback(samples, count, active_user) != 0)
        callback_aborted = true;
    return callback_aborted ? 1 : 0;
}

}

int rb_espeak_init(const char *data_parent)
{
    if (!data_parent || !data_parent[0])
        return RB_ESPEAK_INVALID_ARGUMENT;
    EngineGuard guard;
    if (!guard.acquired)
        return RB_ESPEAK_BUSY;
#ifdef RB_ESPEAK_NATIVE
    char resolved[RB_ESPEAK_PATH_MAX];
#else
    char resolved[PATH_MAX];
#endif
    if (!resolve_parent(data_parent, resolved, sizeof(resolved)))
        return RB_ESPEAK_ERROR;
    if (engine_ready())
        return strcmp(initialized_parent, resolved) == 0 ? sample_rate : RB_ESPEAK_ERROR;
    if (!copy_text(initialized_parent, sizeof(initialized_parent), resolved) ||
        !join_path(data_directory, sizeof(data_directory), resolved, "espeak-data") ||
        !validate_core_data())
        return RB_ESPEAK_ERROR;
    language_count = 0;
    variant_count = 1;
    variant_choices[0] = VoiceChoice();
    copy_text(variant_choices[0].name, sizeof(variant_choices[0].name), "Default");
    if (!scan_choices("", false, 0) || !scan_choices("!v", true, 0) || !language_count)
        return RB_ESPEAK_ERROR;
    qsort(language_choices, language_count, sizeof(VoiceChoice), choice_compare);
    qsort(variant_choices + 1, variant_count - 1, sizeof(VoiceChoice), choice_compare);
#ifndef RB_ESPEAK_NATIVE
#ifdef _WIN32
    text_locale = _create_locale(LC_CTYPE, "Polish_Poland.1250");
#else
    text_locale = newlocale(LC_CTYPE_MASK, "C.UTF-8", NULL);
    if (!text_locale)
        text_locale = newlocale(LC_CTYPE_MASK, "en_US.UTF-8", NULL);
#endif
    if (!text_locale)
        return RB_ESPEAK_ERROR;
#endif
    bool initialized = false;
    {
        LocaleGuard locale;
        if (locale.valid())
        {
            sample_rate = espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 20, resolved, 0);
            initialized = sample_rate == 22050;
        }
        if (!initialized)
            espeak_Terminate();
    }
    if (!initialized)
    {
#ifndef RB_ESPEAK_NATIVE
#ifdef _WIN32
        _free_locale(text_locale);
#else
        freelocale(text_locale);
#endif
        text_locale = NULL;
#endif
        return RB_ESPEAK_ERROR;
    }
    espeak_SetSynthCallback(receive_pcm);
#ifdef RB_ESPEAK_NATIVE
    rb_espeak_engine_mark_ready();
#else
    ready.store(true, std::memory_order_release);
#endif
    return sample_rate;
}

int rb_espeak_validate_voice(const char *language, const char *variant)
{
    if (!engine_ready())
        return RB_ESPEAK_NOT_INITIALIZED;
    return find_choice(false, language) && find_choice(true, variant ? variant : "")
        ? RB_ESPEAK_OK : RB_ESPEAK_INVALID_VOICE;
}

int rb_espeak_synth(const char *text, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, int punctuation,
                   rb_espeak_callback callback, void *user)
{
    return rb_espeak_synth_tracked(text, language, variant, rate, pitch, volume,
        range, wordgap, punctuation, callback, NULL, user);
}

static int synthesize(const char *text, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, int punctuation,
                   rb_espeak_callback callback,
                   rb_espeak_position_callback position_callback, void *user,
                   unsigned int character)
{
    if (!text || !callback || punctuation < RB_ESPEAK_PUNCT_NONE ||
        punctuation > RB_ESPEAK_PUNCT_ALL)
        return RB_ESPEAK_INVALID_ARGUMENT;
    int validation = rb_espeak_validate_voice(language, variant);
    if (validation != RB_ESPEAK_OK)
        return validation;
    EngineGuard guard;
    if (!guard.acquired)
        return RB_ESPEAK_BUSY;
    LocaleGuard locale;
    if (!locale.valid())
        return RB_ESPEAK_ERROR;
    SynthesisReset reset;
#ifdef RB_ESPEAK_NATIVE
    size_t allocation_failures = rb_espeak_heap_failures();
#endif
    const VoiceChoice *selected = find_choice(false, language);
    const VoiceChoice *selected_variant = find_choice(true, variant ? variant : "");
    if (!validate_dictionary(selected->dictionary))
        return RB_ESPEAK_ERROR;
    char identifier[60];
    int length = snprintf(identifier, sizeof(identifier), "%s%s%s", selected->filename,
                          selected_variant->id[0] ? "+" : "", selected_variant->id);
    if (length < 0 || static_cast<size_t>(length) >= sizeof(identifier) ||
        espeak_SetVoiceByName(identifier) != EE_OK)
        return RB_ESPEAK_ERROR;
    rate = rate < 80 ? 80 : rate > 1350 ? 1350 : rate;
    espeak_SetParameter(espeakRATE, rate > 450 ? 450 : rate, 0);
    espeak_SetParameter(espeakPITCH, pitch, 0);
    espeak_SetParameter(espeakVOLUME, volume, 0);
    espeak_SetParameter(espeakRANGE, range, 0);
    espeak_SetParameter(espeakWORDGAP, wordgap, 0);
    const wchar_t *punctuation_list = L"";
    int punctuation_mode = espeakPUNCT_NONE;
    if (punctuation == RB_ESPEAK_PUNCT_SOME || punctuation == RB_ESPEAK_PUNCT_MOST)
    {
        punctuation_mode = espeakPUNCT_SOME;
        punctuation_list = punctuation == RB_ESPEAK_PUNCT_SOME
            ? L".,;:!?" : L".,;:!?\"'()[]{}-";
    }
    else if (punctuation == RB_ESPEAK_PUNCT_ALL)
        punctuation_mode = espeakPUNCT_ALL;
    if (espeak_SetPunctuationList(punctuation_list) != EE_OK ||
        espeak_SetParameter(espeakPUNCTUATION, punctuation_mode, 0) != EE_OK)
        return RB_ESPEAK_ERROR;
#if RB_ESPEAK_HAVE_SONIC
    SonicOutput sonic;
    if (rate > 450)
    {
        if (!sonic.prepare(rate))
            return RB_ESPEAK_ERROR;
        if (sonic.stream)
            active_sonic = &sonic;
    }
#endif
    active_callback = callback;
    active_position_callback = position_callback;
    active_text_characters = 0;
    if (position_callback)
        for (const unsigned char *byte = reinterpret_cast<const unsigned char *>(text);
             *byte; ++byte)
            if ((*byte & 0xc0) != 0x80)
                ++active_text_characters;
    active_user = user;
    callback_aborted = false;
    active_has_audio = false;
    espeak_ERROR result = espeak_Synth(text, strlen(text) + 1, 0, POS_CHARACTER, 0,
                                     espeakCHARS_UTF8 | espeakENDPAUSE |
                                     (character ? espeakSSML : 0), NULL, user);
    if (result == EE_OK && character && volume > 0 && !active_has_audio &&
        !callback_aborted
#if RB_ESPEAK_HAVE_SONIC
        && !sonic.failed
#endif
       )
    {
        char fallback[40];
        snprintf(fallback, sizeof(fallback), "Unicode %u", character);
        result = espeak_Synth(fallback, strlen(fallback) + 1, 0, POS_CHARACTER, 0,
                             espeakCHARS_UTF8 | espeakENDPAUSE, NULL, user);
    }
#if RB_ESPEAK_HAVE_SONIC
    if (result == EE_OK && sonic.stream && !callback_aborted && !sonic.failed)
        sonic.failed = !sonicFlushStream(sonic.stream) || !sonic.drain(true);
    if (sonic.failed)
        return RB_ESPEAK_ERROR;
#endif
    if (result != EE_OK)
        return RB_ESPEAK_ERROR;
#ifdef RB_ESPEAK_NATIVE
    if (rb_espeak_heap_failures() != allocation_failures)
        return RB_ESPEAK_ERROR;
#endif
    return callback_aborted ? RB_ESPEAK_ABORTED : RB_ESPEAK_OK;
}

int rb_espeak_synth_tracked(const char *text, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, int punctuation,
                   rb_espeak_callback callback,
                   rb_espeak_position_callback position_callback, void *user)
{
    return synthesize(text, language, variant, rate, pitch, volume, range, wordgap,
                      punctuation, callback, position_callback, user, 0);
}

int rb_espeak_synth_character(unsigned int character, const char *language,
                   const char *variant, int rate, int pitch, int volume,
                   int range, int wordgap, rb_espeak_callback callback, void *user)
{
    if (!character || character > 0x10ffff ||
        (character >= 0xd800 && character <= 0xdfff))
        return RB_ESPEAK_INVALID_ARGUMENT;
    char text[80];
    snprintf(text, sizeof(text), "<say-as interpret-as=\"tts:char\">&#%u;</say-as>", character);
    return synthesize(text, language, variant, rate, pitch, volume, range, wordgap,
                      RB_ESPEAK_PUNCT_NONE, callback, NULL, user, character);
}

int rb_espeak_voice_count(bool variants)
{
    if (!engine_ready())
        return 0;
    return variants ? variant_count : language_count;
}

const char *rb_espeak_voice_name(bool variants, int index)
{
    if (index < 0 || index >= rb_espeak_voice_count(variants))
        return NULL;
    return variants ? variant_choices[index].name : language_choices[index].name;
}

const char *rb_espeak_voice_id(bool variants, int index)
{
    if (index < 0 || index >= rb_espeak_voice_count(variants))
        return NULL;
    return variants ? variant_choices[index].id : language_choices[index].id;
}
