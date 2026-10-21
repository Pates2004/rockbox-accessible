ifeq ($(ESPEAK),1)

ESPEAK_DIR := $(ROOTDIR)/lib/espeak
ESPEAK_BUILD := $(BUILDDIR)/lib/espeak
ESPEAK_ENGINE_NAMES := speak_lib compiledict dictionary intonation readclause \
    setlengths numbers synth_mbrola synthdata synthesize translate \
    tr_languages voices wavegen phonemelist klatt
ESPEAK_OBJECTS := $(ESPEAK_BUILD)/rb_espeak.o \
    $(addprefix $(ESPEAK_BUILD)/engine/,$(addsuffix .o,$(ESPEAK_ENGINE_NAMES)))
ESPEAK_LIB := $(BUILDDIR)/lib/libespeak.a
ifeq ($(APP_TYPE),)
ESPEAK_CXXFLAGS ?= -Os -g
else
ESPEAK_CXXFLAGS ?= -O2 -g
endif
ESPEAK_CFLAGS ?= $(ESPEAK_CXXFLAGS)
ESPEAK_SONIC ?= 1
ifeq ($(ESPEAK_SONIC),1)
ESPEAK_OBJECTS += $(ESPEAK_BUILD)/sonic/sonic.o
endif
ifneq ($(strip $(CROSS_COMPILE)),)
ifneq ($(filter default undefined,$(origin CXX)),)
CXX := $(CROSS_COMPILE)g++
endif
ifneq ($(filter default undefined,$(origin CC)),)
CC := $(CROSS_COMPILE)gcc
endif
endif
ifeq ($(APP_TYPE),sdl-sim)
ESPEAK_PLATFORM_FLAGS := -fPIC $(filter -m32 -m64,$(GCCOPTS))
ESPEAK_HOST_FLAGS := -std=c++11 -fno-exceptions -fno-rtti -fPIC \
    $(filter -m32 -m64,$(GCCOPTS)) -I$(ESPEAK_DIR) -I$(ESPEAK_DIR)/engine \
    -DRB_ESPEAK_HAVE_SONIC=$(ESPEAK_SONIC)

GLOBAL_LDOPTS += -lstdc++ -lm
else ifeq ($(filter-out hibyos,$(APP_TYPE)),)
CXX := $(patsubst %gcc,%g++,$(CC))
ESPEAK_PLATFORM_FLAGS := $(filter-out -std=% -Wstrict-prototypes -Wmissing-prototypes -Wno-pointer-sign -Wno-override-init,$(GCCOPTS)) \
    -DRB_ESPEAK_NATIVE=1 -I$(ESPEAK_DIR)/native/include \
    -I$(ESPEAK_DIR)/native -ffunction-sections -fdata-sections \
    -fno-unwind-tables -fno-asynchronous-unwind-tables -fstack-usage
ESPEAK_HOST_FLAGS := $(ESPEAK_PLATFORM_FLAGS) -std=c++11 \
    -nostdinc++ -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit \
    -I$(ESPEAK_DIR) -I$(ESPEAK_DIR)/engine \
    -DRB_ESPEAK_HAVE_SONIC=$(ESPEAK_SONIC)
ESPEAK_OBJECTS += $(ESPEAK_BUILD)/native/native_runtime.o $(ESPEAK_BUILD)/native/native_text.o
CORE_LIBS += $(TLSFLIB)
CORE_LDOPTS += -Wl,--start-group $(call a2lnk,$(CORE_LIBS)) -lm -lgcc -Wl,--end-group
else
$(error Unsupported integrated eSpeak platform $(APP_TYPE))
endif

CORE_LIBS += $(ESPEAK_LIB)
INCLUDES += -I$(ESPEAK_DIR)

.PHONY: espeak
espeak: $(ESPEAK_LIB)

$(ESPEAK_LIB): $(ESPEAK_OBJECTS)
	$(SILENT)mkdir -p $(dir $@)
	$(SILENT)$(AR) rcs $@ $(ESPEAK_OBJECTS)

$(ESPEAK_BUILD)/sonic/%.o: $(ESPEAK_DIR)/sonic/%.c $(ESPEAK_DIR)/espeak.make
	$(SILENT)mkdir -p $(dir $@)
	$(SILENT)$(CC) $(ESPEAK_PLATFORM_FLAGS) $(ESPEAK_CFLAGS) -std=c11 -MMD -MP -c $< -o $@

$(ESPEAK_BUILD)/native/%.o: $(ESPEAK_DIR)/native/%.c $(ESPEAK_DIR)/espeak.make
	$(SILENT)mkdir -p $(dir $@)
	$(SILENT)$(CC) $(CFLAGS) -I$(ESPEAK_DIR)/native -fstack-usage -MMD -MP -c $< -o $@

$(ESPEAK_BUILD)/%.o: $(ESPEAK_DIR)/%.cpp $(ESPEAK_DIR)/espeak.make
	$(SILENT)mkdir -p $(dir $@)
	$(SILENT)$(CXX) $(ESPEAK_HOST_FLAGS) $(ESPEAK_CXXFLAGS) -MMD -MP -c $< -o $@

-include $(ESPEAK_OBJECTS:.o=.d)

endif
