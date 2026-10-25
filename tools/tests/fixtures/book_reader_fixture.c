/* ABI probes and an executable sanitizer exercise of the production core. */
#include "book_reader.h"
#include <assert.h>
#include <string.h>

size_t book_test_size(unsigned int type)
{
    switch (type)
    {
        case 0: return sizeof(struct book_position);
        case 1: return sizeof(struct book_info);
        case 2: return sizeof(struct book_nav_entry);
        case 3: return sizeof(struct book_source);
        default: return sizeof(struct book_nav_job);
    }
}

#ifdef BOOK_TEST_EXECUTABLE
static enum book_result generated(void *context, uint32_t index,
                                  struct book_nav_entry *out)
{
    unsigned int *calls = context;
    ++*calls;
    *out = (struct book_nav_entry){
        .parent = index ? 0 : BOOK_ID_NONE,
        .units = index % 997 == 0 ? BOOK_UNIT_HEADING : 0,
        .heading_level = index % 997 == 0 ? 1 : 0,
        .position = { .resource = 0, .anchor = index,
                      .audio_resource = BOOK_ID_NONE,
                      .flags = BOOK_POSITION_VISUAL }
    };
    return BOOK_OK;
}

int main(void)
{
    unsigned int calls = 0;
    struct book_source source = {
        .info = { .resource_count = 1, .entry_count = 100000,
                  .units = BOOK_UNIT_HEADING },
        .read_entry = generated, .context = &calls
    };
    struct book_nav_job job;
    struct book_nav_entry entry;
    uint32_t index = BOOK_ID_NONE;
    assert(book_nav_begin(&job, &source, 0, BOOK_UNIT_HEADING, 0,
                          BOOK_NEXT, BOOK_EDGE_STOP) == BOOK_AGAIN);
    enum book_result result;
    do { result = book_nav_step(&job, 7, &index, &entry); }
    while (result == BOOK_AGAIN);
    assert(result == BOOK_OK && index == 997 && calls == 997);
    unsigned char record[BOOK_POSITION_RECORD_SIZE];
    assert(book_position_encode(&source.info, &entry.position,
                                 record, sizeof(record)) == BOOK_OK);
    struct book_position restored;
    assert(book_position_decode(&source.info, record, sizeof(record),
                                 &restored) == BOOK_OK);
    assert(restored.anchor == index && restored.flags == BOOK_POSITION_VISUAL);
    for (size_t size = 0; size < sizeof(record); ++size)
        assert(book_position_decode(&source.info, record, size,
                                     &restored) == BOOK_CORRUPT);
    for (size_t byte = 0; byte < sizeof(record); ++byte)
    {
        record[byte] ^= 1;
        assert(book_position_decode(&source.info, record, sizeof(record),
                                     &restored) == BOOK_CORRUPT);
        record[byte] ^= 1;
    }
    book_nav_cancel(&job);
    assert(book_nav_step(&job, 1, &index, &entry) == BOOK_CANCELLED);
    return 0;
}
#endif
