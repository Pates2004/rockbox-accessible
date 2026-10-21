# Firmware startowy Rockboxa dla HiBy R1

Pobrany plik: `hibyr1_1.8b2_bahusoid_rb_26.09.17.zip`.
Źródło: [wydanie Bahusoida26.09.17](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2).
To społecznościowa modyfikacja **HiBy R1 1.8b2** z loaderem Rockboxa,
nie nasza synteza ani firmware R1 MIDI lub R3. Nie zmienialiśmy tego obrazu.

SHA-256 ZIP,38540535 bajtów:
`770fd83626b7899a254628670856408f07415061589820ac2991d685aa9443d9`.
W środku jest tylko `r1.upt`,42113024 bajty, SHA-256:
`19231b97e19c429da101b1fa2ed670a79a74408ba45e29de446f9fd249410dc6`.
Sprawdzono sumy, strukturę aktualizacji i osadzony loader; nie jest to test
flashowania na Twoim egzemplarzu ani gwarancja bezpiecznego downgrade.

## Jak połączyć dwie paczki

1. Przygotuj kopię danych karty, właściwy stockowy firmware do powrotu i pomoc
   przy nieudźwiękowionym aktualizatorze, jeśli jej potrzebujesz. Sprawdź model,
   obecną wersję i możliwość zainstalowania wybranego obrazu przed flashowaniem.
2. Rozpakuj nasz osobny ZIP z `installfiles/hibyr1` do katalogu głównego karty.
   Bezpośrednio na karcie ma powstać `.rockbox/rockbox.r1` z całą resztą paczki.
3. Rozpakuj ten ZIP firmware. Jego `r1.upt` umieść w katalogu głównym tej samej
   karty, obok `.rockbox`, nie wewnątrz niej. Nie kopiuj samego ZIP na kartę.
4. Po potwierdzeniu zgodności uruchom fabryczny aktualizator:
   **System → Firmware update → TF/SD-card update**. Nie wyłączaj odtwarzacza,
   nie wyjmuj karty i nie odłączaj zasilania w trakcie zapisu.
5. Nasza `.rockbox` zawiera domyślny wybór Rockboxa dla tego loadera. Po
   restarcie uruchamia się on automatycznie, bez obowiązkowego wyboru OS.
   Selektor może być widoczny przez około sekundę; nie jest to cały czas startu.
6. Po udanym zapisie usuń `r1.upt` z karty. Zachowaj ten oryginalny ZIP na
   komputerze. Kolejne aktualizacje Rockboxa zwykle wymieniają tylko `.rockbox`.

Powrót do aplikacji HiBy Player nie usuwa modyfikacji firmware. Z zapisanego
wyboru Rockboxa w selektorze służy do tego krótko **Głośność −**, potem **Next**.
Nie przytrzymuj Next podczas włączania. Szczegóły i alternatywę przez plik na
karcie opisuje `HIBY-R1-INSTALL-PL.md` w dokumentacji naszej paczki.

Nie wykonuj losowych kombinacji ratunkowych: źródła podają sprzeczne klawisze.
Nie używaj obrazu burn/factory zamiast zwykłej aktualizacji. Ta dokumentacja nie
potwierdza wszystkich wersji firmware, Bluetooth, baterii ani sprzętowej obsługi
dotyku. Windows `rockboxui.exe` służy wyłącznie do symulacji na komputerze.
