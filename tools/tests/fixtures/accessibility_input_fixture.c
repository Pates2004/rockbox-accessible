enum input_shortcut_service
{
    INPUT_SHORTCUT_ESPEAK,
    INPUT_SHORTCUT_VOICE_FILES,
    INPUT_SHORTCUT_SERVICE_COUNT
};

static unsigned int input_service_calls[INPUT_SHORTCUT_SERVICE_COUNT];
static unsigned int input_shortcut_gate_calls;
static bool input_service_success;

bool accessibility_shortcut_toggle_espeak(void)
{
    ++input_service_calls[INPUT_SHORTCUT_ESPEAK];
    return input_service_success;
}

bool accessibility_shortcut_toggle_voice_files(void)
{
    ++input_service_calls[INPUT_SHORTCUT_VOICE_FILES];
    return input_service_success;
}

bool accessibility_shortcut_enabled(void)
{
    ++input_shortcut_gate_calls;
    return false;
}

bool accessibility_shortcut_activate(void)
{
    ++input_shortcut_gate_calls;
    return false;
}

bool accessibility_services_activate(void)
{
    ++input_shortcut_gate_calls;
    return input_service_success;
}

void input_reset(void)
{
    probe_reset();
    memset(input_service_calls, 0, sizeof(input_service_calls));
    input_shortcut_gate_calls = 0;
    input_service_success = true;
    accessibility_init();
}

int input_install(const char *buffer, int length)
{
    struct accessibility_config candidate;
    if (length < 0 || !accessibility_parse(buffer, length, &candidate))
        return false;
    active_config = candidate;
    accessibility_apply();
    return true;
}

unsigned int input_calls(unsigned int service)
{
    return service < INPUT_SHORTCUT_SERVICE_COUNT ? input_service_calls[service] : 0;
}

unsigned int input_gate_calls(void) { return input_shortcut_gate_calls; }
void input_success(bool success) { input_service_success = success; }
unsigned int input_action_index(unsigned int action) { return accessibility_action_index(action); }

int input_edit_gesture(void) { return accessibility_edit_gestures(); }

#ifdef HIBY_R1
int input_repeat(unsigned int button, unsigned int slot, int context)
{
    if (button >= ACCESSIBILITY_BUTTON_COUNT || slot >= ACCESSIBILITY_BUTTON_SLOT_COUNT)
        return ACTION_UNKNOWN;
    struct accessibility_button_event event = {
        .consumed = true, .recognized = true, .repeat = true,
        .button = button, .slot = slot
    };
    return physical_action(&event, context, false);
}
#endif
