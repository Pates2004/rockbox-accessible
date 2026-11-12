"""Compile and execute the real ARM/Thumb byteswap and JPEG clamp helpers."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_tts_coverage import extract_block

ROOT = Path(__file__).resolve().parents[2]
PREAMBLE = r'''
#include <stdint.h>
#define CPU_ARM 1
#define ARM_ARCH 5
#define INLINE static inline
#ifdef DIVIDED_ASM
#define BEGIN_ARM_ASM_SYNTAX_UNIFIED ".syntax unified\n"
#define END_ARM_ASM_SYNTAX_UNIFIED ".syntax divided\n"
#else
#define BEGIN_ARM_ASM_SYNTAX_UNIFIED
#define END_ARM_ASM_SYNTAX_UNIFIED
#endif
'''
MAIN = r'''
static unsigned check(uint32_t v)
{
    uint32_t swap = (v >> 24) | ((v >> 8) & 0xff00u) |
                    ((v << 8) & 0xff0000u) | (v << 24);
    uint32_t pairs = ((v & 0xff00ff00u) >> 8) | ((v & 0x00ff00ffu) << 8);
    if (swap32_hw(v) != swap) return 1;
    if (swap_odd_even32_hw(v) != pairs) return 2;
    if (swaw32_hw(v) != ((v >> 16) | (v << 16))) return 3;
    /* Check flags and equal-value register allocation around inlined assembly. */
    if ((swap32_hw(v) == swap) != (swap_odd_even32_hw(v) == pairs)) return 4;
    return 0;
}
unsigned test_all(void)
{
    const uint32_t edges[] = {0,1,16,0x00ff00ffu,0xff00ff00u,0xffffffffu,
                             0x80000000u,0x7fffffffu,0x12345678u};
    for (unsigned i=0;i<sizeof(edges)/sizeof(edges[0]);++i)
        if (check(edges[i])) return 10+i;
    uint32_t v=0x91827364u;
    for (unsigned i=0;i<4096;++i)
    {
        v=v*1664525u+1013904223u;
        if (check(v)) return 40;
    }
    const int limits[] = {(-2147483647-1),-65536,-1,0,1,254,255,256,65536,2147483647};
    for (unsigned i=0;i<sizeof(limits)/sizeof(limits[0]);++i)
    {
        int v=limits[i];
        unsigned expected=v<0 ? 0 : v>255 ? 255 : (unsigned)v;
        if ((range_limit(v)&255u)!=expected) return 50+i;
    }
    for (int v=-1024;v<2048;++v)
    {
        unsigned expected=v<0 ? 0 : v>255 ? 255 : (unsigned)v;
        if ((range_limit(v)&255u)!=expected) return 70;
    }
    return 0;
}
'''


class ArmThumbHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which(os.environ.get('ARM_CC', 'arm-none-eabi-gcc'))
        cls.objcopy = shutil.which('arm-none-eabi-objcopy')
        cls.nm = shutil.which('arm-none-eabi-nm')
        if not all((cls.cc, cls.objcopy, cls.nm)):
            raise unittest.SkipTest('ARM bare-metal GCC/binutils required')
        cls.area = project_materials_root(ROOT) / 'arm-thumb-helper-tests' / uuid.uuid4().hex
        cls.area.mkdir(parents=True)
        arm = (ROOT / 'firmware/target/arm/system-arm.h').read_text(encoding='utf-8')
        arm = arm[arm.index('#else /* ARM_ARCH < 6 */'):]
        cls.helpers = '\n'.join(extract_block(arm, 'static inline uint32_t '+name+'(')
                                for name in ('swap32_hw','swap_odd_even32_hw','swaw32_hw'))
        cls.clamp = extract_block((ROOT / 'apps/recorder/jpeg_load.c').read_text(encoding='utf-8'),
                                  'INLINE unsigned range_limit(')

    def compile(self, text, label, mode='-mthumb', unified=True, optimization='-Os'):
        source = self.area / (label+'.c')
        source.write_text(PREAMBLE+text, encoding='utf-8')
        binary = source.with_suffix('.elf')
        command = [self.cc,'-mcpu=arm926ej-s',mode,optimization,'-std=gnu11',
                   '-ffreestanding','-fno-builtin','-nostdlib','-Wall','-Wextra','-Werror',
                   '-Wl,-Ttext=0x10000,-e,test_all',str(source),'-o',str(binary)]
        command += ['-masm-syntax-unified'] if unified else ['-DDIVIDED_ASM']
        result = subprocess.run(command,capture_output=True,text=True,timeout=60)
        source.with_suffix('.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        source.with_suffix('.json').write_text(json.dumps({'argv':command,'exit':result.returncode},indent=2)+'\n',encoding='utf-8')
        return result,binary

    def test_execute_arm_and_thumb_against_reference(self):
        if importlib.util.find_spec('unicorn') is None:
            self.skipTest('Optional Unicorn ARM instruction emulator required')
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_MODE_THUMB
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
        for mode in ('-mthumb','-marm'):
            for unified in (True,False):
                for optimization in ('-Os','-O2'):
                    label=f'{mode[2:]}-{unified}-{optimization[1:]}'
                    with self.subTest(label=label):
                        result,binary=self.compile(self.helpers+self.clamp+MAIN,label,mode,unified,optimization)
                        self.assertEqual(result.returncode,0,result.stderr)
                        raw=binary.with_suffix('.bin')
                        subprocess.run([self.objcopy,'-O','binary',str(binary),str(raw)],check=True,timeout=30)
                        symbols=subprocess.check_output([self.nm,'--defined-only',str(binary)],text=True,timeout=30)
                        match=re.search(r'^([0-9a-f]+)\s+T\s+test_all$',symbols,re.M)
                        self.assertIsNotNone(match,symbols)
                        thumb=mode=='-mthumb'
                        cpu=Uc(UC_ARCH_ARM, UC_MODE_THUMB if thumb else UC_MODE_ARM)
                        cpu.mem_map(0x10000,0x10000);cpu.mem_write(0x10000,raw.read_bytes())
                        cpu.mem_map(0x100000,0x10000)
                        cpu.reg_write(UC_ARM_REG_SP,0x10fff0)
                        cpu.reg_write(UC_ARM_REG_LR,0x1fff0 | int(thumb))
                        cpu.emu_start(int(match[1],16)|int(thumb),0x1fff0,timeout=5_000_000,count=2_000_000)
                        self.assertEqual(cpu.reg_read(UC_ARM_REG_PC),0x1fff0,'Instruction/time bound exhausted')
                        self.assertEqual(cpu.reg_read(UC_ARM_REG_R0),0,'Incorrect swap/clamp result')

    def test_legacy_asm_negative_controls_reproduce_thumb_failures(self):
        legacy=re.sub(r'\b(ands|eors|lsls|lsrs|orrs|movs|rors)\b',lambda m:m[0][:-1],self.helpers)
        result,_=self.compile(legacy+self.clamp+MAIN,'legacy-byteswap')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('cannot honor width suffix',result.stderr)
        legacy=self.clamp.replace('defined(CPU_ARM) && !defined(__thumb__)','defined(CPU_ARM)')
        self.assertNotEqual(legacy,self.clamp)
        result,_=self.compile(self.helpers+legacy+MAIN,'legacy-clamp')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('conditional instruction',result.stderr)


if __name__ == '__main__':
    unittest.main()
