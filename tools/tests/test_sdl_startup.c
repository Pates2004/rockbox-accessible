#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <SDL.h>

#define HIGHEST_IRQ_LEVEL 1
#define HZ 100
#define enable_irq() ((void)set_irq_level(0))

static int allocation_number;
static int failure_number;
static volatile long current_tick;

static SDL_mutex *create_test_mutex(void)
{
    if (++allocation_number == failure_number)
        return NULL;
    return SDL_CreateMutex();
}

static SDL_cond *create_test_condition(void)
{
    if (++allocation_number == failure_number)
        return NULL;
    return SDL_CreateCond();
}

static void call_tick_tasks(void)
{
    ++current_tick;
}

#define SDL_CreateMutex create_test_mutex
#define SDL_CreateCond create_test_condition
#include "kernel-functions.h"

struct interrupt_state
{
    SDL_sem *ready;
    SDL_atomic_t entered;
};

static int early_interrupt(void *data)
{
    struct interrupt_state *state = data;
    SDL_SemPost(state->ready);
    sim_enter_irq_handler();
    SDL_AtomicSet(&state->entered, 1);
    sim_exit_irq_handler();
    return 0;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    failure_number = atoi(argv[1]);
    assert(SDL_Init(SDL_INIT_TIMER) == 0);
    bool initialized = sim_kernel_init();
    if (failure_number)
    {
        assert(!initialized);
        SDL_DestroyMutex(sim_irq_mtx);
        SDL_DestroyCond(sim_thread_cond);
#ifndef HAVE_SDL_THREADS
        SDL_DestroyCond(wfi_cond);
        SDL_DestroyMutex(wfi_mutex);
#endif
        SDL_Quit();
        puts("Allocation failure returned before event delivery");
        return 0;
    }
    assert(initialized);
    struct interrupt_state state = { .ready = SDL_CreateSemaphore(0) };
    assert(state.ready);
    SDL_Thread *worker = SDL_CreateThread(early_interrupt, "early-event", &state);
    assert(worker);
    assert(SDL_SemWaitTimeout(state.ready, 1000) == 0);
    SDL_Delay(30);
    assert(SDL_AtomicGet(&state.entered) == 0);
    SDL_mutex *original_mutex = sim_irq_mtx;
    SDL_cond *original_condition = sim_thread_cond;
    tick_start(1000 / HZ);
    assert(original_mutex == sim_irq_mtx && original_condition == sim_thread_cond);
    assert(set_irq_level(0) == HIGHEST_IRQ_LEVEL);
    SDL_WaitThread(worker, NULL);
    assert(SDL_AtomicGet(&state.entered) == 1);
    SDL_DestroySemaphore(state.ready);
    SDL_Delay(30);
    sim_kernel_shutdown();
    SDL_Quit();
    puts("Early event waited on initialized synchronization; timer retained it");
    return 0;
}
