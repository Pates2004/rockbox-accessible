# Accessible typing

## Echo and capital letters

Typing settings now contains Typing mode, Typing echo, Capital letter
announcement, Capital voice pitch change, and Deletion announcement. The three
input modes below remain available. Mode data stays in
`/.rockbox/accessibility-typing.cfg`; the other four preferences use the atomic
`/.rockbox/accessibility-typing-echo.cfg` file.

Typing echo selects None, Characters, Words, or Characters and words (default).
Words are announced when a word boundary is entered; accepting a newly edited
final word can also announce it. Failed insertions and empty deletions do not
announce an edit. Moving the caret or cancelling does not pretend that a new
word was entered. Focus/key identification remains available independently of
edit echo, including when echo is None.

Capital letter announcement selects None (default, preserving earlier speech),
Say capital, or Change voice pitch. The pitch adjustment is relative to the
current eSpeak pitch, from -80% to +100%, initially +20%. It is attached to that
character's queued utterance and clamped to eSpeak's pitch range; it never
changes the saved voice pitch or subsequent normal utterances.

Deletion announcement selects Say deleted and character (default), Deleted
character only, or None. The default says, for example, “deleted b”. Unicode
character boundaries and the actual text cursor are used, not byte positions.
The keyboard has no secret/password-field flag; do not assume these speech
preferences supply a password privacy mode.

Open **Settings → General Settings → Accessibility → Talkbox settings → Typing settings**. The choice is saved separately in `.rockbox/accessibility-typing.cfg`. It does not change existing accessibility assignments or the plugin settings layout. A missing or invalid file selects **Explore and type on lift**, matching the previous point keyboard's lift behavior. A failed save reports an error and keeps the previous mode.

- **Explore and type on lift:** touch a key to hear it. Slide across keys to hear each newly focused key immediately. Lift inside a valid key to enter the focused key once. A quick stationary tap also enters its key. A contact that leaves valid keyboard regions is cancelled until a fresh press.
- **Explore and double-tap to type:** slide to hear and focus a key immediately, then lift without entering it. Holding a stationary touch briefly also focuses its key. Two quick stationary taps enter the focused key once; their coordinates do not choose another key. Each tap must end inside a valid keyboard region. The interval between the first release and the second release must be at most 320 ms. Exploration, invalid contact, physical input, lock or context change cancels the pending double tap.
- **Arrows and Enter; hold Enter to finish:** use directional buttons or the configured accessibility navigation gestures to move focus, then press Enter to enter a character. Hold Enter to finish. Below the character rows, Up/Down also reaches the spoken **OK**, **Delete** and **Cancel** controls; Left/Right selects between them. The edit line above the grid retains text cursor navigation and Enter deletes there. The existing page and cursor button combinations remain available.

The same key focus and speech apply to uppercase/lowercase letters, punctuation, Polish characters, spaces and custom keyboard layouts. A space is spoken as a blank. Touch exploration speaks the **OK**, **Delete**, **Cancel**, next page and left/right text cursor regions; activate them using the selected typing mode. **Delete** removes the preceding character, **OK** accepts the text and **Cancel** returns the keyboard's cancellation result to its caller. Cursor movement announces the character at the new position, or **End of text**. Buffer limits remain in force; an insertion that does not fit is not performed.

On HiBy R1, Enter is the Power button by default. A short press types; its first hold repeat finishes text entry, and its release must not type another character or activate the next screen. Continue to use the existing physical Power emergency shutdown behavior if needed; typing does not change its firmware threshold. Finish-before-shutdown timing and the physical touchscreen still require testing on an R1. User remappings can change physical actions.

Direct touch modes treat movement as keyboard exploration; global navigation swipes remain available in the arrows mode. Locking, leaving the keyboard, connecting USB or cancelling touch discards unfinished touch sequences. A fresh touch press is required afterwards. Accessibility being disabled and Morse input retain their existing keyboard handling. Typing exploration emits no click for each motion; a committed touch action produces one gesture feedback request using the existing click settings.

If the keyboard cannot create its views, it announces **Cannot open keyboard**, returns cancellation without accepting text, and restores the previous theme. No typing session remains active after this error.

These modes apply to the shared core keyboard, including core keyboard entry opened by a plugin. Independent plugin keyboards need their own integration. Host tests can verify state transitions, UTF-8 editing and persistence failures; they do not establish physical R1, NVDA or complete packaged application acceptance.
