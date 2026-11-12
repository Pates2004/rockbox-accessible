"""Regression effects for selectively integrated upstream settings/RDS fixes."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest
import uuid

from test_radio_dynamic import ROOT
from test_tts_coverage import extract_block
from project_materials import project_materials_root

PREAMBLE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define logf(...) ((void)0)
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"line %d: %s\n",__LINE__,#c); exit(101); } } while(0)
enum {F_T_CUSTOM=1,F_T_INT,F_T_UINT,F_T_BOOL,F_T_CHARPTR,F_T_UCHARPTR,F_T_MASK=7,
      F_THEMESETTING=8,F_INT_SETTING=16,F_TABLE_SETTING=32,F_ALLOW_ARBITRARY_VALS=64};
struct int_setting { int min,max; };
struct custom_setting { void (*load_from_cfg)(void*,char*); };
struct bool_setting { void (*option_callback)(bool); };
struct table_setting { const int *values; int count; };
struct filename_setting { int max_len; };
struct settings_list { uint32_t flags; void *setting; const char *cfg_name;
 const struct int_setting *int_setting; const struct custom_setting *custom_setting;
 const struct bool_setting *bool_setting; const struct table_setting *table_setting;
 const struct filename_setting *filename_setting; union {int int_;} default_val; };
static struct settings_list setting;
static int callbacks;
static void changed(bool value) { callbacks += value ? 1 : 100; }
static const struct settings_list *find_setting_by_cfgname(const char *name)
{ return strcmp(name,"test") ? NULL : &setting; }
static const char *setting_get_cfgvals(const struct settings_list *s) { (void)s; return NULL; }
static bool cfg_string_to_int(const struct settings_list *s,int *out,const char *value)
{ (void)s; if(!strcmp(value,"on")){*out=1;return true;} if(!strcmp(value,"off")){*out=0;return true;} return false; }
static bool copy_filename_setting(char *out,size_t n,const char *in,const struct filename_setting *f)
{(void)out;(void)n;(void)in;(void)f;return true;}
enum { RDS_INFO_PS, RDS_INFO_RT };
static const unsigned char *packet;
static size_t packet_size, pushed_size;
static int pushes;
static void rds_push_info(int field,uintptr_t value,size_t size)
{ CHECK(field==RDS_INFO_PS || field==RDS_INFO_RT); CHECK((const unsigned char*)value==packet+4);
  CHECK(size<=packet_size-4); pushed_size=size; pushes++; }
'''
MAIN = r'''
int main(void) {
 bool theme=false, enabled=true; int value=5;
 struct int_setting range={1,10}; struct bool_setting boolean={changed};
 setting=(struct settings_list){.flags=F_T_INT|F_INT_SETTING,.setting=&value,.int_setting=&range};
 CHECK(string_to_cfg("test","999",&theme) && value==10);
 CHECK(string_to_cfg("test","-9",&theme) && value==1);
 range=(struct int_setting){10,1};
 CHECK(string_to_cfg("test","-99",&theme) && value==1);
 CHECK(string_to_cfg("test","99",&theme) && value==10);
 CHECK(string_to_cfg("test","7",&theme) && value==7);
 CHECK(string_to_cfg("test","9999999999999999999999999",&theme) && value==10);
 CHECK(string_to_cfg("test","-9999999999999999999999999",&theme) && value==1);
 setting.flags=F_T_BOOL; setting.setting=&enabled; setting.bool_setting=&boolean;
 CHECK(!string_to_cfg("test","nonsense",&theme) && enabled && callbacks==0);
 CHECK(string_to_cfg("test","off",&theme) && !enabled && callbacks==100);
 CHECK(string_to_cfg("test","on",&theme) && enabled && callbacks==101);
 for(unsigned int length=0;length<=20;length++) {
   unsigned char *buf=malloc(length ? length : 1); CHECK(buf); memset(buf,0,length);
   packet=buf; packet_size=length; pushes=0;
   if(length>=3)buf[2]=0x1e;
   rmt_tuner_rds_data(length,buf);
   CHECK(pushes==(length>=4)); if(length>=4)CHECK(pushed_size==MIN(length-4,8u));
   if(length>=3)buf[2]=0x04;
   pushes=0; rmt_tuner_rds_data(length,buf);
   CHECK(pushes==(length>=4)); if(length>=4)CHECK(pushed_size==length-4);
   free(buf);
 }
 puts("PASS"); return 0;
}
'''


class UpstreamSettingsRdsTests(unittest.TestCase):
    def test_real_configuration_effects_and_short_packets(self):
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        if not shutil.which(compiler[0]):
            self.skipTest('Host C compiler required')
        area = project_materials_root(ROOT) / 'upstream-settings-rds-tests' / uuid.uuid4().hex
        area.mkdir(parents=True)
        settings = (ROOT / 'apps/settings.c').read_text(encoding='utf-8')
        tuner = (ROOT / 'firmware/drivers/tuner/ipod_remote_tuner.c').read_text(encoding='utf-8')
        source = area / 'fixture.c'
        source.write_text(PREAMBLE + extract_block(settings, 'bool string_to_cfg(') + '\n' +
                          extract_block(tuner, 'void rmt_tuner_rds_data(') + MAIN, encoding='utf-8')
        binary = area / ('fixture.exe' if os.name == 'nt' else 'fixture')
        command = compiler + ['-std=c99', '-O1', '-Wall', '-Wextra', '-Werror',
                              '-fsanitize=undefined', '-fno-sanitize-recover=all', str(source), '-o', str(binary)]
        compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (area / 'compile.log').write_text(compile_result.stdout + compile_result.stderr, encoding='utf-8')
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        (area / 'run.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
