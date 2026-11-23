#include "m10v_roll_capture.h"

static uint32_t load(const uint32_t *word) {
    return __atomic_load_n(word, __ATOMIC_ACQUIRE);
}

static void publish(m10v_roll_capture_channel *channel, uint32_t state) {
    __atomic_store_n(&channel->state, state, __ATOMIC_RELEASE);
}

static int transition(m10v_roll_capture_channel *channel, uint32_t from) {
    return __atomic_compare_exchange_n(&channel->state, &from, M10V_ROLL_CAPTURE_TRANSITION,
                                       0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
}

int m10v_roll_capture_arm(m10v_roll_capture_channel *channel, uint32_t ticket,
                          const uint8_t marker[M10V_ROLL_MARKER_BYTES],
                          uint32_t tone, uint32_t aspect, uint32_t film) {
    if (!channel || !ticket || !marker || !tone || tone > 255u || aspect > 5u || !film ||
        !transition(channel, M10V_ROLL_CAPTURE_EMPTY))
        return 0;
    __atomic_store_n(&channel->ticket, ticket, __ATOMIC_RELAXED);
    for (uint32_t i = 0; i < M10V_ROLL_MARKER_BYTES; i++)
        __atomic_store_n(&channel->marker[i], marker[i], __ATOMIC_RELAXED);
    channel->expected_tone = tone;
    channel->expected_aspect = aspect;
    channel->expected_film = film;
    publish(channel, M10V_ROLL_CAPTURE_ARMED);
    return 1;
}

int m10v_roll_capture_revoke(m10v_roll_capture_channel *channel, uint32_t ticket) {
    if (!channel || !ticket || load(&channel->ticket) != ticket ||
        !transition(channel, M10V_ROLL_CAPTURE_ARMED))
        return 0;
    publish(channel, M10V_ROLL_CAPTURE_EMPTY);
    return 1;
}

int m10v_roll_capture_reserve(m10v_roll_capture_channel *channel, uint32_t si, uint32_t generation,
                              uint32_t tone, uint32_t aspect, uint32_t film) {
    if (!channel || !si || !transition(channel, M10V_ROLL_CAPTURE_ARMED)) return 0;
    if (tone != channel->expected_tone || aspect != channel->expected_aspect ||
        film != channel->expected_film) {
        publish(channel, M10V_ROLL_CAPTURE_ARMED);
        return 0;
    }
    __atomic_store_n(&channel->si, si, __ATOMIC_RELAXED);
    __atomic_store_n(&channel->si_generation, generation, __ATOMIC_RELAXED);
    __atomic_store_n(&channel->group, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&channel->writer, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&channel->reached_outputs, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&channel->marked_outputs, 0, __ATOMIC_RELAXED);
    channel->save.ticket = 0;
    publish(channel, M10V_ROLL_CAPTURE_CLAIMED);
    return 1;
}

static int matches(const m10v_roll_capture_channel *channel, uint32_t si, uint32_t generation) {
    return channel && load(&channel->state) == M10V_ROLL_CAPTURE_CLAIMED &&
        load(&channel->si) == si && load(&channel->si_generation) == generation;
}

static void copy_marker(const m10v_roll_capture_channel *channel, uint8_t *marker) {
    for (uint32_t i = 0; i < M10V_ROLL_MARKER_BYTES; i++)
        marker[i] = __atomic_load_n(&channel->marker[i], __ATOMIC_RELAXED);
}

int m10v_roll_capture_copy_marker(const m10v_roll_capture_channel *channel, uint32_t si,
                                  uint32_t generation, uint8_t marker[M10V_ROLL_MARKER_BYTES]) {
    if (!marker || !matches(channel, si, generation)) return 0;
    const uint32_t ticket = load(&channel->ticket);
    copy_marker(channel, marker);
    return matches(channel, si, generation) && load(&channel->ticket) == ticket;
}

int m10v_roll_capture_complete(m10v_roll_capture_channel *channel, uint32_t si,
                               uint32_t generation, int32_t saved_outputs) {
    if (saved_outputs < M10V_ROLL_SAVE_UNKNOWN ||
        saved_outputs > (M10V_ROLL_SAVE_JPEG | M10V_ROLL_SAVE_DNG) ||
        !matches(channel, si, generation) ||
        !transition(channel, M10V_ROLL_CAPTURE_CLAIMED))
        return 0;
    channel->result = saved_outputs;
    publish(channel, M10V_ROLL_CAPTURE_RESULT);
    return 1;
}

int m10v_roll_capture_take_result(m10v_roll_capture_channel *channel, uint32_t *ticket,
                                  uint8_t marker[M10V_ROLL_MARKER_BYTES], int32_t *saved_outputs) {
    if (!channel || !ticket || !marker || !saved_outputs ||
        !transition(channel, M10V_ROLL_CAPTURE_RESULT))
        return 0;
    *ticket = load(&channel->ticket);
    *saved_outputs = channel->result;
    copy_marker(channel, marker);
    publish(channel, M10V_ROLL_CAPTURE_EMPTY);
    return 1;
}
