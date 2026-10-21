#ifndef RB_ESPEAK_SHADOW_NATIVE_ONLY_H
#define RB_ESPEAK_SHADOW_NATIVE_ONLY_H
#if !defined(RB_ESPEAK_NATIVE) || RB_ESPEAK_NATIVE != 1
#error eSpeak shadow headers require RB_ESPEAK_NATIVE=1 and must not enter core includes
#endif
#endif
