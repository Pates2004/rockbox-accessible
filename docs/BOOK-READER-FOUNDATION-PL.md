# Podwaliny wspólnego czytnika książek

[English](BOOK-READER-FOUNDATION.md)

To pierwszy etap implementacji: niezależny od formatu rdzeń C w
`apps/book_reader.[ch]`. **Nie otwiera jeszcze DAISY, EPUB, PDF, MOBI ani
dokumentów biurowych.** Opcje książek pojawią się w menu wraz z działającym
adapterem. Obecny czytnik TXT, domyślne wyszukiwanie, przypisania przycisków
i zakładki tekstowe oraz muzyczne korzystają z dotychczasowej implementacji.

Moduł kompiluje się z wbudowanym eSpeakiem dla każdego dopuszczonego celu.
Nie zależy od wejścia, ekranu, audio ani systemu plików HiBy. Dopóki adapter
go nie wywołuje, linker może usunąć nieużywany kod. Etap nie zmienia ABI
pluginów i nie potwierdza obsługi kolejnego odtwarzacza.

## Publikacja i pozycja

`book_source` dostarcza niezmienne dane publikacji i funkcję pobierającą po
jednym wpisie nawigacji. Adapter zarządza indeksem, który może znajdować się
na nośniku. Rdzeń nie przydziela pamięci na stercie ani nie ładuje całego drzewa
książki. Identyfikatory zasobów i wpisów należą do jednej rewizji. Wpisy mają
kolejność czytania, a rodzice poprzedzają dzieci. Tytuły oraz etykiety stron
pochodzą z adaptera; numer wpisu nie jest numerem strony wydawcy.

Pozycja zawiera logiczny zasób i kotwicę, lokalny offset bajtów zdekodowanego
UTF-8 oraz, jeśli istnieje nagranie, osobny zasób audio i bezwzględny czas
mediów w milisekundach. Tekst i lektor mogą pochodzić z różnych plików.
Flagi rozróżniają tekst, dźwięk i obraz oraz ich połączenia. Strona PDF
z samym obrazem może mieć pozycję wizualną bez tekstu. **OCR odkładamy;
obrazy PDF mają być wyświetlane na ekranie.** Parser i renderer PDF wymagają
jeszcze implementacji. Flaga obrazu sama nie wyświetla strony ani nie tworzy
tekstu do odczytania głosem.

Adapter nadaje stałe identyfikatory w obrębie rewizji, sprawdza granice kotwic,
plików, klipów i znaków UTF-8. Musi zmienić rewizję, kiedy zmieniają się treść,
schemat indeksu, identyfikatory lub zasady liczenia offsetów. Osobne odciski
32-bajtowe identyfikują publikację oraz dokładną rewizję treści/indeksu.
Powinny być deterministyczne, np. SHA-256. Służą wykrywaniu nieaktualnych
pozycji; nie potwierdzają autentyczności książki.

## Nawigacja z ograniczeniem pracy

`book_nav_begin` wybiera dostępną jednostkę, opcjonalny dokładny poziom
nagłówków, kierunek i zatrzymanie lub zawijanie na granicy. Jednostki to
nagłówki publikacji, strony wydawcy, frazy, akapity, zdania, słowa i znaki.
Adapter zgłasza tylko jednostki, które potrafi rzeczywiście wskazać.
Niedostępna jednostka zwraca `BOOK_UNSUPPORTED`; samo nagranie nie zapewnia
granic słów.

Po poprawnym rozpoczęciu (`BOOK_AGAIN` lub `BOOK_END`) kolejne wywołania
`book_nav_step` mają dodatni limit wywołań adaptera. `BOOK_AGAIN` oddaje
sterowanie interfejsowi. Zadanie można anulować. Gdy adapter zwróci
`BOOK_AGAIN`, następny krok ponawia ten sam wpis. Limit wywołań i stały
rozmiar zadania nie dowodzą ograniczenia czasu ani pamięci samego adaptera;
jego operacje wejścia/wyjścia i parsowanie także muszą być dzielone na kroki.

Punkt początkowy jest pomijany także po zawinięciu. `BOOK_ID_NONE` oznacza
start przed pierwszym lub za ostatnim wpisem. Tylko `BOOK_OK` zapisuje wynik.
Koniec, błędy, anulowanie i zmienione źródło pozostawiają argumenty wyjściowe
bez zmian. Zmiana tożsamości, rewizji, liczników, jednostek, funkcji adaptera
lub kontekstu unieważnia zadanie. Źródło i kontekst muszą istnieć do jego
zakończenia. Obowiązuje jeden wątek interfejsu, bez równoległych zmian
i ponownych wywołań z adaptera. Powiązanie bieżącej pozycji czytania z wpisem
początkowym należy do adaptera; rdzeń nie zgaduje go z czasu ani offsetu.

## Zapis pozycji, wersja 1

Nowy rekord nie zmienia ani nie migruje starych zakładek. Ma 108 bajtów,
bez wyrównania struktur C. Liczby są zapisane od najmłodszego bajtu:

| Bajt | Pole |
| --- | --- |
| 0 | cztery bajty `RBKP` |
| 4 | wersja uint16 = 1 |
| 6 | długość uint16 = 108 |
| 8 | tożsamość publikacji, 32 bajty |
| 40 | rewizja treści i indeksu, 32 bajty |
| 72 | zasób logiczny, uint32 |
| 76 | kotwica, uint32 (`UINT32_MAX` oznacza korzeń zasobu) |
| 80 | lokalny offset tekstu po dekodowaniu, uint64 |
| 88 | zasób audio, uint32 (`UINT32_MAX`, gdy nie istnieje) |
| 92 | bezwzględny czas audio w ms, uint64 |
| 100 | flagi tekstu/dźwięku/obrazu, uint32 |
| 104 | CRC-32/ISO-HDLC poprzednich 104 bajtów, uint32 |

Brak tekstu wymaga offsetu zero. Brak audio wymaga specjalnego identyfikatora
i czasu zero. Zasoby muszą należeć do publikacji. Odczyt sprawdza dokładną
długość, CRC, wersję, tożsamość i rewizję; błąd nie nadpisuje wyniku.
Zapis przygotowuje wyłącznie poprawny kompletny rekord. Atomowy zapis pliku,
wznowienie i podłączenie do menu zakładek to dalsze prace. Ten moduł sam
nie zapisuje danych użytkownika.

## Weryfikacja i dalsze etapy

Testy uruchamia `python3 -B tools/tests/test_book_reader.py -v`, z kompilatorem
C hosta. `BOOK_READER_SANITIZE=1` włącza kontrolę niezdefiniowanych zachowań,
a `BOOK_READER_ASAN=1` na Linuksie dodatkowy program z kontrolą pamięci.
Testy wykonują właściwy rdzeń i CRC, używają dużych syntetycznych publikacji
oraz niezależnych wzorców nawigacji i rekordu (`struct`/`zlib` Pythona).
Dowody pozostają w centralnym obszarze roboczym projektu. To testy rdzenia,
bez deklaracji zgodności formatów i działania na fizycznym sprzęcie.

Dalej potrzebne są dostęp do kontenerów i XML z ograniczeniem pamięci,
adaptery formatów, kolejność czytania i bloki tekstu, sterowanie klipami audio,
odsyłacze z powrotem, pomijanie i wyjście ze struktury. Następnie mówiące menu
oraz preferencje globalne i dla książki. Pełne DAISY obejmuje warianty audio,
tekstowe i zsynchronizowane; sam spis treści i playlista MP3 nie wystarczają.
EPUB, PDF i pozostałe adaptery wymagają osobnej weryfikacji.
