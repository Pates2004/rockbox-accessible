# Kontenery książek

[English](BOOK-CONTAINERS.md)

`apps/book_archive.[ch]` to drugi etap podwalin. Odczytuje katalog klasycznego
ZIP na żądanie, znajduje konkretny plik i przekazuje dane STORE lub DEFLATE
fragmentami przez funkcje wywołania zwrotnego. Nie rozpakowuje plików na dysk
i nie buduje drzewa całej książki. To **nie jest jeszcze czytnik EPUB/DOCX/ODT
ani DAISY**: potrzebne są XML i adaptery formatów. Renderer PDF i OCR są poza
tym etapem.

Układ oparto na [PKWARE APPNOTE 6.3.10](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).
Początkowy zakres to jednodyskowy klasyczny ZIP, do 65 534 wpisów, wielkość
archiwum do `UINT32_MAX`, nazwy krótsze niż 1024 bajty, bez szyfrowania i ZIP64.
Inne metody kompresji zwracają brak obsługi przy odczycie danego pliku.
Nazwy są dokładnymi bajtami ZIP z rozróżnianiem wielkości liter. Interpretacja
Unicode/URI, tożsamość publikacji, rewizja i ścieżki należą do adapterów.

Otwarcie sprawdza układ katalogu bez ładowania go w całości. Lista i wyszukiwanie
przechowują ograniczoną metainformację; powtórzona szukana nazwa jest błędem.
Odczyt porównuje nagłówek lokalny z aktualnym wpisem katalogu i sprawdza deskryptor
danych z sygnaturą lub bez niej, limit wyniku, długość i CRC. Fragmenty wyniku są
tymczasowe do sukcesu całego pliku; przy błędzie trzeba je odrzucić. Istniejący
dekompresor nie podaje dokładnego zużycia ostatnich bitów; nadmiarowe bajty
wczytane z ostatnim blokiem wejścia nie są osobno klasyfikowane jako dopełnienie.

Wywołujący zapewnia niezmienny odczyt według offsetu, opcjonalne sprawdzanie
anulowania, odbiorcę danych i wyrównany obszar roboczy. DEFLATE potrzebuje
71 448 bajtów na zmierzonych hostach, niezależnie od długości dokumentu; rozmiar
i wyrównanie należy pobierać z API. STORE nie potrzebuje pamięci dekompresora.
Są to synchroniczne funkcje dla wątku roboczego, nie wznawialne zadania
interfejsu. Operacje wejścia/wyjścia muszą oddawać czas procesora. Stały bufor
nie jest pomiarem pamięci procesu R1. Arena 15 MiB i ABI pluginów są zachowane.

Wspólny dekompresor odczytuje teraz krótkie końcowe kody Huffmana bez żądania
bajtów poza strumieniem RAW. Składanie sum używa przesunięć bez znaku;
gzip dodatkowo sprawdza końcową długość. Testy obejmują RAW/zlib/gzip, ZIP
generowane niezależnie przez Pythona, nazwy Unicode, krótkie odczyty, anulowanie,
limity i błędne metadane. Uruchom `tools/tests/test_book_archive.py`;
`BOOK_ARCHIVE_SANITIZE=1` oraz na Linuksie `BOOK_ARCHIVE_ASAN=1` włączają
instrumentację. To nie potwierdza zgodności formatów, fizycznego odtwarzania ani NVDA.
