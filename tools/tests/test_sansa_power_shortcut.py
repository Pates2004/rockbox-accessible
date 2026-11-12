"""Execute Sansa input polling, native mappings and the accessibility shortcut."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_hiby_r1_keymap import without_includes
from test_tts_coverage import extract_block

ROOT = Path(__file__).resolve().parents[2]
PREAMBLE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define HAVE_ESPEAK
#define HAVE_ACCESSIBILITY_POWER
#define HAVE_RDS_CAP
#define HAVE_HOTKEY
#define HAVE_VOLUME_IN_LIST
#define CONFIG_KEYPAD 42
#define SANSA_CLIP_PAD 42
#define INIT_ATTR
#define HZ 100
#define SYS_EVENT 0x40000000
#define SYS_BATTERY_UPDATE (SYS_EVENT|3)
#define SYS_CHARGER_CONNECTED (SYS_EVENT|4)
#define SYS_CHARGER_DISCONNECTED (SYS_EVENT|5)
#define SYS_USB_CONNECTED (SYS_EVENT|6)
#define GUI_EVENT_ACTIONUPDATE 1
#define REPEAT_WINDOW_TICKS (HZ/4)
#define logf(...) ((void)0)
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"line %d: %s\n",__LINE__,#c); exit(101); } } while(0)
'''
MOCKS = r'''
static action_last_t action_last;
static struct { bool accessibility_shortcut_enabled, hold_lr_for_scroll_in_list; } global_settings;
static long current_tick;
static int queued_button, observed_timeout, reads, activations;
static bool speech, fail_service;
long button_get_w_tmo(int timeout) { observed_timeout=timeout; ++reads; return queued_button; }
intptr_t button_get_data(void) { return 0; }
static bool accessibility_services_activate(void)
{ ++activations; if(fail_service) return false; speech=!speech; return true; }
static void send_event(int event,void *data) { (void)event; (void)data; }
static int autosoftlock_timeout(action_last_t *last) { (void)last; return -1; }
bool is_keys_locked(void) { return false; }
static void do_softlock(action_last_t *last,action_cur_t *cur) { (void)last; (void)cur; }
static void *core_get_data(int handle) { (void)handle; return NULL; }
static bool get_action_touchscreen(action_last_t *last,action_cur_t *cur)
{ (void)last; (void)cur; return false; }
static void keyclick_click(bool repeated,int action) { (void)repeated; (void)action; }
static void button_flip_horizontally(int context,int *button) { (void)context; (void)button; }
'''
MAIN = r'''
static void fresh(void)
{
    memset(&action_last,0,sizeof(action_last));
    action_last.button=BUTTON_REL;
    global_settings.accessibility_shortcut_enabled=true;
    accessibility_power_reset(&accessibility_power);
    accessibility_power_pending_button=BUTTON_NONE;
    current_tick=0;reads=activations=0;speech=fail_service=false;
}
static int event(int context,int button,int ticks,int timeout)
{
    current_tick+=ticks;queued_button=button;
    action_cur_t cur;init_act_cur(&cur,context,timeout,NULL);
    return get_action_worker(&action_last,&cur);
}
static void click(int context)
{
    CHECK(event(context,BUTTON_POWER,8,0)==ACTION_NONE);
    CHECK(event(context,BUTTON_POWER|BUTTON_REL,6,0)==ACTION_NONE);
}
static void triple(int context) { click(context);click(context);click(context); }
int main(void)
{
    const int contexts[]={CONTEXT_STD,CONTEXT_SETTINGS,CONTEXT_WPS,CONTEXT_FM,
                          CONTEXT_KEYBOARD,CONTEXT_LIST,CONTEXT_QUICKSCREEN};
    for(unsigned i=0;i<sizeof(contexts)/sizeof(contexts[0]);++i)
    {
        int context=contexts[i];fresh();triple(context);
        CHECK(activations==1 && speech);
        CHECK(event(context,BUTTON_POWER|BUTTON_REL,0,0)==ACTION_NONE);
        CHECK(event(context,BUTTON_NONE,50,0)==ACTION_NONE);
        triple(context);CHECK(activations==2 && !speech);
        /* Incomplete group reproduces BOTH actual native edges in order. */
        fresh();global_settings.accessibility_shortcut_enabled=false;
        int press=event(context,BUTTON_POWER,0,0);
        int release=event(context,BUTTON_POWER|BUTTON_REL,6,0);
        for(int count=1;count<=2;++count)
        {
            fresh();for(int c=0;c<count;++c)click(context);
            CHECK(event(context,BUTTON_NONE,29,-1)==ACTION_NONE);
            CHECK(observed_timeout==HZ/10);
            CHECK(event(context,BUTTON_NONE,1,-1)==press);
            int before=reads;
            CHECK(event(context,BUTTON_NONE,0,-1)==release);
            CHECK(reads==before); /* Synthetic release never blocks the caller. */
            CHECK(activations==0 && (action_last.button&BUTTON_REL));
        }
        fresh();global_settings.accessibility_shortcut_enabled=false;
        int native_press=event(context,BUTTON_POWER,1,0);
        int native_repeat=event(context,BUTTON_POWER|BUTTON_REPEAT,31,0);
        int native_held_release=event(context,BUTTON_POWER|BUTTON_REL,1,0);
        fresh();CHECK(event(context,BUTTON_POWER,1,0)==ACTION_NONE);
        CHECK(event(context,BUTTON_POWER|BUTTON_REPEAT,31,0)==native_press);
        CHECK(event(context,BUTTON_NONE,0,0)==native_repeat);
        CHECK(event(context,BUTTON_POWER|BUTTON_REL,1,0)==native_held_release);
        CHECK(!activations);
        /* A slow release without a delivered repeat must preserve press actions too. */
        fresh();CHECK(event(context,BUTTON_POWER,1,0)==ACTION_NONE);
        CHECK(event(context,BUTTON_POWER|BUTTON_REL,30,0)==native_press);
        CHECK(event(context,BUTTON_NONE,0,0)==release);
    }
    fresh();click(CONTEXT_STD);
    CHECK(event(CONTEXT_STD,BUTTON_NONE,0,0)==ACTION_NONE && observed_timeout==0);
    CHECK(event(CONTEXT_STD,BUTTON_NONE,0,5)==ACTION_NONE && observed_timeout==5);
    CHECK(event(CONTEXT_STD,BUTTON_DOWN,1,0)==ACTION_STD_NEXT);
    CHECK(event(CONTEXT_STD,BUTTON_DOWN|BUTTON_REL,6,0)!=ACTION_STD_CANCEL);
    CHECK(event(CONTEXT_STD,BUTTON_NONE,50,0)==ACTION_NONE && !activations);
    fresh();click(CONTEXT_STD);
    CHECK(event(CONTEXT_SETTINGS,BUTTON_NONE,50,0)==ACTION_NONE && !activations);
    fresh();click(CONTEXT_STD);
    CHECK(event(CONTEXT_STD,BUTTON_REDRAW,5,0)==ACTION_REDRAW);
    CHECK(event(CONTEXT_STD,SYS_BATTERY_UPDATE,1,0)==SYS_BATTERY_UPDATE);
    CHECK(event(CONTEXT_STD,SYS_CHARGER_CONNECTED,1,0)==SYS_CHARGER_CONNECTED);
    click(CONTEXT_STD);click(CONTEXT_STD);CHECK(activations==1);
    fresh();click(CONTEXT_STD);
    CHECK(event(CONTEXT_STD,SYS_USB_CONNECTED,1,0)==SYS_USB_CONNECTED);
    CHECK(event(CONTEXT_STD,BUTTON_NONE,50,0)==ACTION_NONE);
    fresh();click(CONTEXT_STD);
    global_settings.accessibility_shortcut_enabled=false;
    CHECK(event(CONTEXT_STD,BUTTON_NONE,50,0)==ACTION_NONE);
    CHECK(event(CONTEXT_STD,BUTTON_POWER,1,0)==ACTION_STD_CANCEL);
    fresh();click(CONTEXT_STD);
    CHECK(event(CONTEXT_PLUGIN|CONTEXT_STD,BUTTON_POWER,1,0)==ACTION_STD_CANCEL);
    CHECK(!activations);
    /* Native wait-for-release must still clear, even while the shortcut is enabled. */
    fresh();CHECK(event(CONTEXT_STD,BUTTON_POWER,1,0)==ACTION_NONE);
    action_last.wait_for_release=true;
    CHECK(event(CONTEXT_STD,BUTTON_POWER|BUTTON_REL,6,0)==ACTION_NONE);
    CHECK(!action_last.wait_for_release);
    triple(CONTEXT_STD);CHECK(activations==1);
    /* A context change during held input keeps the native release filter. */
    fresh();CHECK(event(CONTEXT_STD,BUTTON_POWER,1,0)==ACTION_NONE);
    CHECK(event(CONTEXT_SETTINGS,BUTTON_POWER|BUTTON_REL,6,0)==ACTION_NONE);
    triple(CONTEXT_SETTINGS);CHECK(activations==1);
    fresh();event(CONTEXT_STD,BUTTON_POWER,1,0);
    CHECK(event(CONTEXT_STD,BUTTON_POWER|BUTTON_REPEAT,31,0)==ACTION_STD_CANCEL);
    action_last.wait_for_release=true;
    CHECK(event(CONTEXT_SETTINGS,BUTTON_NONE,0,-1)==ACTION_NONE);
    CHECK(action_last.wait_for_release);
    CHECK(event(CONTEXT_SETTINGS,BUTTON_POWER|BUTTON_REL,1,0)==ACTION_NONE);
    CHECK(!action_last.wait_for_release);
    triple(CONTEXT_SETTINGS);CHECK(activations==1);
    /* A replayed Cancel can change screens before its synthetic release. */
    fresh();click(CONTEXT_STD);
    CHECK(event(CONTEXT_STD,BUTTON_NONE,30,0)==ACTION_STD_CANCEL);
    action_last.wait_for_release=true;
    CHECK(event(CONTEXT_SETTINGS,BUTTON_NONE,0,-1)==ACTION_NONE);
    CHECK(!action_last.wait_for_release);
    triple(CONTEXT_SETTINGS);CHECK(activations==1);
    /* Held/repeated buttons and Power combinations retain native mappings. */
    fresh();global_settings.accessibility_shortcut_enabled=false;
    int native_press=event(CONTEXT_WPS,BUTTON_POWER,1,0);
    int held=event(CONTEXT_WPS,BUTTON_POWER|BUTTON_REPEAT,30,0);
    int held_release=event(CONTEXT_WPS,BUTTON_POWER|BUTTON_REPEAT|BUTTON_REL,1,0);
    fresh();click(CONTEXT_WPS);event(CONTEXT_WPS,BUTTON_POWER,8,0);
    CHECK(event(CONTEXT_WPS,BUTTON_POWER|BUTTON_REPEAT,30,0)==native_press);
    CHECK(event(CONTEXT_WPS,BUTTON_NONE,0,0)==held);
    CHECK(event(CONTEXT_WPS,BUTTON_POWER|BUTTON_REPEAT|BUTTON_REL,1,0)==held_release);
    CHECK(event(CONTEXT_WPS,BUTTON_NONE,50,0)==ACTION_NONE && !activations);
    triple(CONTEXT_WPS);CHECK(activations==1);
    fresh();event(CONTEXT_WPS,BUTTON_POWER,1,0);
    CHECK(event(CONTEXT_WPS,BUTTON_POWER|BUTTON_RIGHT,1,0)==ACTION_WPS_ABSETB_NEXTDIR);
    CHECK(event(CONTEXT_WPS,BUTTON_POWER|BUTTON_REL,1,0)==ACTION_NONE);
    CHECK(event(CONTEXT_WPS,BUTTON_NONE,50,0)==ACTION_NONE && !activations);
    fresh();fail_service=true;triple(CONTEXT_STD);
    CHECK(activations==1 && !speech);
    CHECK(event(CONTEXT_STD,BUTTON_NONE,50,0)==ACTION_NONE);
    /* Wrap/backward discontinuities cannot create an accidental activation. */
    fresh();current_tick=429496720L;triple(CONTEXT_STD);CHECK(activations==1);
    fresh();current_tick=1000;click(CONTEXT_STD);current_tick=20;
    CHECK(event(CONTEXT_STD,BUTTON_NONE,0,0)==ACTION_NONE && !activations);
    triple(CONTEXT_STD);CHECK(activations==1);
    puts("PASS: native input, both-edge fallback, triple toggle, hold, wait, context, timeout and failures");
    return 0;
}
'''


class SansaPowerShortcutTests(unittest.TestCase):
    def test_actual_action_pipeline_and_native_fallbacks(self):
        compiler=shlex.split(os.environ.get('CC','cc'))
        if not shutil.which(compiler[0]):
            self.skipTest('Host C compiler required')
        area=project_materials_root(ROOT)/'sansa-power-shortcut-tests'/uuid.uuid4().hex
        area.mkdir(parents=True)
        action=(ROOT/'apps/action.c').read_text(encoding='utf-8')
        types=action[action.index('typedef struct'):action.index('/* holds the action state')]
        for target in ('clipplus','clipzip'):
            with self.subTest(target=target):
                paths=(f'firmware/target/arm/as3525/sansa-{target}/button-target.h',
                       'firmware/export/button.h','apps/action.h','apps/accessibility_power.h')
                headers='\n'.join(without_includes((ROOT/p).read_text(encoding='utf-8')) for p in paths)
                harness=PREAMBLE+headers+types+MOCKS
                harness+=without_includes((ROOT/'apps/keymaps/keymap-clip.c').read_text(encoding='utf-8'))
                harness+='\n'.join(extract_block(action, signature) for signature in (
                    'static inline bool has_flag(', 'static inline bool action_poll_button(',
                    'static bool accessibility_power_allowed(', 'static bool accessibility_power_filter(',
                    'static inline void update_screen_has_lock(', 'static inline int action_code_worker(',
                    'static inline int get_next_context(', 'static inline void action_code_lookup(',
                    'static inline int update_action_last(', 'static void init_act_cur(', 'static int get_action_worker('))
                harness+=MAIN
                source=area/(target+'.c');source.write_text(harness,encoding='utf-8')
                binary=source.with_suffix('.exe' if os.name=='nt' else '.out')
                command=compiler+['-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'apps'),
                    str(source),str(ROOT/'apps/accessibility_power.c'),'-o',str(binary)]
                result=subprocess.run(command,capture_output=True,text=True,timeout=60)
                source.with_suffix('.compile.log').write_text(result.stdout+result.stderr,encoding='utf-8')
                self.assertEqual(result.returncode,0,result.stderr)
                result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
                source.with_suffix('.run.log').write_text(result.stdout+result.stderr,encoding='utf-8')
                source.with_suffix('.json').write_text(json.dumps(dict(argv=command,run_exit=result.returncode),indent=2)+'\n',encoding='utf-8')
                self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
