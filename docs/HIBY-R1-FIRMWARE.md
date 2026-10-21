# Rockbox startup firmware for HiBy R1

Downloaded file: `hibyr1_1.8b2_bahusoid_rb_26.09.17.zip`.
Origin: [Bahusoid release26.09.17](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2).
This is a community modification of **HiBy R1 1.8b2** with the Rockbox launcher,
not our speech engine or firmware for R1 MIDI/R3. We did not modify the image.

ZIP SHA256,38540535 bytes:
`770fd83626b7899a254628670856408f07415061589820ac2991d685aa9443d9`.
It contains only `r1.upt`,42113024 bytes, SHA256:
`19231b97e19c429da101b1fa2ed670a79a74408ba45e29de446f9fd249410dc6`.
Checksums, update structure and embedded launcher were inspected; this is not
a flashing test on your unit or a guarantee of safe downgrading.

## Combining the two packages

1. Back up card data, obtain an appropriate stock recovery update and arrange
   assistance with the unvoiced updater if needed. Check the exact model,
   installed version and supported transition before flashing the chosen image.
2. Extract our separate ZIP from `installfiles/hibyr1` into the card root,
   directly creating `.rockbox/rockbox.r1` and all its matching resources.
3. Extract this firmware ZIP. Put `r1.upt` in the same card root, beside
   `.rockbox`, not inside it. Do not copy the unopened ZIP to the card.
4. After confirming compatibility, use the stock updater:
   **System → Firmware update → TF/SD-card update**. Do not turn off the player,
   remove the card or disconnect power while flashing.
5. Our `.rockbox` seeds Rockbox as this launcher's default. It starts
   automatically after reboot without a mandatory OS selection. The selector
   may appear for about one second; that is not total power-on-to-speech time.
6. After a successful flash remove `r1.upt` from the card, retaining the original
   ZIP on the computer. Later Rockbox updates normally replace only `.rockbox`.

Selecting HiBy Player does not remove the modified firmware. From saved Rockbox,
briefly press **Volume Down**, then **Next** during the selector. Do not hold
Next while powering on. See `HIBY-R1-INSTALL.md` in our application documentation
for details and the alternative card-file selection method.

Do not try random recovery chords: the published sources conflict. Do not use
a burn/factory image instead of an ordinary update. This guide does not certify
every firmware version, Bluetooth, battery life or physical touchscreen access.
Windows `rockboxui.exe` is only a computer simulator.
