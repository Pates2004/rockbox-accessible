# Mowa we wtyczkach

Wtyczki korzystają ze wspólnego `talk_*` Rockboksa i wbudowanego eSpeaka,
nie z osobnego silnika. Włącz Talkbox w Dostępność -> Ustawienia Talkbox. Opcja „Używaj plików
głosowych do czytania interfejsu” dotyczy tylko nagranej mowy; jej wyłączenie
nie wyłącza komunikatów eSpeaka we wtyczkach. Osobne ustawienia opcjonalnych
komunikatów konkretnych wtyczek nie są wymuszane przez syntezator.
Nowe etykiety mają polskie i angielskie wersje.

## Rozszerzone narzędzia

| Wtyczka | Co jest odczytywane |
| --- | --- |
| Calculator — kalkulator | Wybrany klawisz, operacja i wynik, również wykładnik; funkcje podstawowe i naukowe. |
| Stopwatch — stoper | Start, pauza, czas, reset, nowe okrążenie i czas odcinka; przy przewijaniu pierwsze widoczne okrążenie. |
| Metronome — metronom | Stan, ręczna zmiana tempa, metrum, głośności i części. Szybkie zmiany są grupowane, a takty nie są stale zagadywane. |
| Dice — kości | Wyniki poszczególnych kości, suma i ustawienia rzutu. |
| Text Editor — edytor tekstu | Wybrany wiersz, także pusty; zmieniona zawartość po edycji/usunięciu. Obsługiwany wiersz do 2047 bajtów jest dzielony na części UTF-8 do odczytu. |
| Dictionary — słownik | Definicja podzielona na wybieralne fragmenty; strzałkami wybierz kolejny lub poprzedni. Wymaga zgodnych plików słownika użytkownika. |
| Stats — statystyki | Osiem wybieralnych wyników: pliki, rozmiar, utwory, playlisty, obrazy, filmy, podkatalogi i maksimum plików w katalogu. Środek powtarza wynik. |
| Calendar — kalendarz | Wybrana data i pierwsze wydarzenie; lista udostępnia pozostałe wydarzenia dnia. |
| Shortcuts — skróty | Pierwszy i kolejne wybrane skróty; poprawiony fokus po usunięciu. |
| Random Folder Advance Configuration | Foldery w edytorze listy i oznaczenie usuniętego folderu. |
| Countdown Timer — minutnik | Wybór czasu, start, pauza, wznowienie i jednokrotny komunikat końca. |
| Alarm Clock — budzik | Edytowane godziny/minuty, czas alarmu, uzbrojenie i pobudka. Jest to istniejący budzik wznawiający muzykę; wymaga utworu do wznowienia, nie uruchamia wyłączonego odtwarzacza. |
| Chess Clock — zegar szachowy | Ustawienia, gracz, start/pauza, pozostały czas na żądanie/zmianę, koniec rundy i menu czynności. Nie oznacza to udźwiękowienia gry w szachy. |

Narzędzia są w menu Wtyczki, głównie Aplikacje; kości są grą, a skróty
i edytor mogą być otwierane przez menu „Otwórz za pomocą”. Nazwy katalogów
i część wcześniejszych menu wtyczek nadal są angielskie. Wtyczki zachowują
własne mapy przycisków; nie wszystkie używają tego samego przycisku wyjścia.

## „Pusta lista” a błędy wtyczek

Przy włączonej mowie list wspólny kod w `apps/gui/list.c:391` wypowiada
`VOICE_EMPTY_LIST` („Pusta lista”), gdy `nb_items == 0`.
To informacja o zerowej liczbie pozycji, bez ustalenia przyczyny ani tego,
czy wtyczka ma błąd. Text Editor uruchomiony z Wtyczki -> Aplikacje otwiera
nowy dokument bez wierszy, więc ten komunikat jest tam oczekiwany. Użyj akcji
zatwierdzenia (OK/Enter), aby wpisać pierwszy wiersz, albo poleceń Insert Above /
Insert Below w menu edytora. Nie rozstrzyga to zgłoszeń dotyczących innych,
niezidentyfikowanych wtyczek.

Inne przykładowe wymagania dotyczące danych:

- Random Folder Advance Configuration: przed Edit przygotuj listę przez Scan Folders
  lub Import from Text File; używany plik to `.rockbox/folder_advance_list.dat`.
- Dictionary: wymaga zgodnych plików `dict.index` i `dict.desc`.
- Shortcuts: wybrany plik skrótów musi zawierać wpisy.

Nowe wydania celowo nie importują wcześniejszych danych użytkownika. Część
wtyczek-przeglądarek wymaga parametru pliku przekazanego przez „Otwórz za pomocą”,
zamiast samodzielnego uruchomienia. Shortcuts bez parametru zgłasza
`No parameter specified!`, a pusty plik skrótów —
`No shortcuts in the file!`. Brak indeksu Dictionary powoduje
`Failed to open index.`. To inne komunikaty niż `VOICE_EMPTY_LIST`;
braku danych nie należy automatycznie opisywać jako „Pusta lista”.

Do analizy zapisz nazwę/plik wtyczki, dokładną drogę uruchomienia, model i wersję,
dosłowny komunikat oraz użyte pliki danych. Zachowaj informację o pustej liście;
fikcyjne wpisy lub wyciszenie komunikatu ukrywałyby rzeczywisty stan.

## Czytanie TXT i rejestrator

Zwykłe otwarcie TXT uruchamia wspólny czytnik, nie Text Editor. Na Sansach
**przytrzymanie środkowego Select/Enter** otwiera menu tekstu z zakładkami,
właściwościami i ustawieniami. Krótkie naciśnięcie wstrzymuje/wznawia;
Góra/Dół zmieniają zakres nawigacji. Szczegóły: `ESPEAK-BOOKMARKS-PL.md`.

Rejestrator jest funkcją główną, nie wtyczką, i jest dostępny tylko na
odtwarzaczach z obsługą nagrywania. Symulator Windows pozwala sprawdzić mowę
jego kontrolek, ale **nie nagrywa mikrofonu**. Naprawa wspólnego miksera usuwa
zakleszczenie odtwarzania mowy przy końcu ciszy między komunikatami.
Nie jest to dowód naprawienia trzasków zgłaszanych na fizycznej Sansie.

## Granice dostępności

Wspólne listy, menu, pytania i komunikaty są obsługiwane przez rdzeń.
Własne interfejsy graficzne innych wtyczek wymagają osobnej pracy: gry,
plansze, obrazy, wizualizacje i oscyloskopy nie stają się dostępne przez samo
włączenie eSpeaka. Nie ogłaszamy dostępności wszystkich wtyczek.

Słownik zachowuje limit długości definicji swojego bufora. Edytor nie zyskuje
pełnego czytnika ekranu dla każdej operacji kursora. Skan folderów/statystyk
nie odczytuje każdego kroku. Alarm nie gwarantuje pracy po wyłączeniu.
Testy kodu, kompilacji i PCM nie zastępują prób na sprzęcie ani oceny słuchowej.
Symulator mówi sam; nie udostępnia pełnego natywnego drzewa kontrolek NVDA.

Używaj zgodnych wtyczek: obecne źródła R1 mają ABI `0xe006`, a zachowane
wydania Sans nadal `0xe003`. Nie mieszaj modułów tych generacji.
Moduły ze standardowego Rockboksa lub innego celu nie są zgodne.
