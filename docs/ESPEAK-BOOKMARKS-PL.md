# Zakładki i menu tekstówek

Czytnik UTF-8 w rdzeniu Rockboksa korzysta z istniejącego ekranu zakładek,
jego udźwiękowienia, usuwania i listy ostatnich zakładek. Nie zmienia formatu
dotychczasowych zakładek audio ani nie zatrzymuje muzyki przy otwieraniu tekstu.

## Sterowanie

Na Clip+ i Clip Zip przytrzymaj środkowy przycisk Select/Enter, jak w muzyce.
W symulatorze Windows przytrzymaj Spację. Góra nie otwiera menu tekstu.
Góra/Dół zmieniają zakres nawigacji, Lewo/Prawo poruszają po tekście.
Krótkie naciśnięcie Select wstrzymuje lub wznawia czytanie.
Przyciski głośności zachowują dotychczasową zmianę zakresu w czytniku.

Menu „Opcje tekstu” zawiera:

- Wznów czytanie.
- Zakładki → Utwórz zakładkę / Pokaż zakładki.
- Właściwości: nazwa, ścieżka, wielkość, pozycja i zakres nawigacji.
- Przejdź na początek / Przejdź na koniec.
- Ustawienia czytania tekstu i Ustawienia eSpeak.

Otwarcie menu zatrzymuje mowę książki na słowie słyszalnym przy otwieraniu,
nie na końcu tekstu już przekazanego do syntezy. Po zamknięciu menu czytnik
pozostaje wstrzymany; wybierz „Wznów czytanie” lub krótkie Select. Mowa menu
korzysta z tego samego miksera i przyciszania muzyki. Powrót z menu odtwarza
tekst ponownie od zachowanego słowa; zwykła pauza bez menu zachowuje bufor PCM.

## Zapis i odczyt

Zakładki tekstowe zawierają pozycję bajtową UTF-8 oraz zakres nawigacji,
nie czas audio. Dla `książka.txt` plik ma nazwę `książka.txt.bmark` obok tekstu.
Nie edytuj ręcznie jego wpisów. Karta/katalog musi być zapisywalny.
Zapis sprawdza błędy i zastępuje stary plik dopiero po ukończeniu zapisu
tymczasowego. Zastane pliki tymczasowe pozostają nienaruszone: jeśli `.tmp`
już istnieje, zapis próbuje kolejno wolnych nazw od `.t01` do `.t0f`, bez
nadpisywania ich. Zajęcie wszystkich tych nazw lub inny błąd operacji plikowej
powoduje niepowodzenie zapisu. Błąd zapisu listy ostatnich może wystąpić już po
skutecznym zapisie zakładki przy książce. Czytnik odróżnia ten częściowy wynik
od całkowitego niepowodzenia; zapisaną pozycję można wczytać z listy lokalnej.
Jeśli w ogólnych ustawieniach zakładek jest włączona lista ostatnich,
zakładki tekstowe pojawiają się na niej razem z audio. Załadowanie tekstowej
nie zmienia listy odtwarzania, losowania ani prędkości aktualnej muzyki.

Na istniejącej liście zakładek wybierz pozycję i zatwierdź. Przytrzymanie
Select otwiera standardowe „Wznów” / „Usuń”; usuwanie wymaga potwierdzenia.
Po wczytaniu lokalnej zakładki wracasz do menu tekstu i możesz wznowić mowę.
Globalna lista ostatnich otwiera wskazany tekst od zapisanej pozycji.
Zakładki są ręczne: ta wersja nie dodaje automatycznego zapisu przy zamykaniu.
Nazwy własne zakładek oraz migracja zakładek wtyczki Text Viewer nie należą
do tego etapu. Po przeniesieniu lub zmianie nazwy książki odtwórz zakładki.

Rozmiar i sygnatura próbek początku, końca oraz otoczenia pozycji pomagają
wykryć zmianę dokumentu. Nie jest to pełna suma całej książki: zmiana wyłącznie
poza próbkami, bez zmiany długości, może pozostać niewykryta. Niepoprawna
pozycja UTF-8 lub wykryta zmiana jest zgłaszana zamiast cichego skoku.
Zachowuj książki niezmienione podczas czytania; odrębna walidacja na fizycznym
odtwarzaczu pozostaje konieczna. Działa odczyt TXT UTF-8, nie PDF/EPUB/DOCX.

Rdzeń jest wspólny dla odtwarzaczy. Mapa przycisków, sterowniki i zasoby
sprzętowe nadal wymagają osobnego buildu i testów dla każdego nowego targetu.
Udźwiękowienie nowych ekranów nie oznacza pełnej dostępności wszystkich
zewnętrznych wtyczek ani natywnego interfejsu UIA dla NVDA w symulatorze SDL.

## Wyszukiwanie i wpisywanie pozycji

Opcje tekstu dodają „Znajdź”, „Znajdź następne” i „Znajdź poprzednie”.
Ostatnie skuteczne zapytanie, do 128 bajtów UTF-8, jest pamiętane wyłącznie
podczas bieżącego otwarcia czytnika. Anulowanie, USB, brak wyniku, błędny tekst
lub odrzucone dodanie komunikatu do kolejki zachowuje poprzednie zapytanie
i wstrzymaną pozycję słyszalnego tekstu. Następne wyszukiwanie pomija początek
bieżącego znaku. Poprzednie wybiera ostatni wcześniejszy początek; wyniki mogą
na siebie nachodzić.

Osobna zapisywana opcja „Wielkość liter przy wyszukiwaniu” domyślnie ignoruje
wielkość liter. Używa prostego mapowania Unicode na małe litery, w tym polskich
par, bez usuwania znaków diakrytycznych. Nie normalizuje złożonych i rozłożonych
znaków ani nie rozwija wieloznakowych odpowiedników takich jak SS/ß.
„Wyszukiwanie na granicy tekstu” oferuje domyślne „Zatrzymaj i ogłoś”,
„Pytaj o zawinięcie” i „Zawijaj automatycznie”. Zawinięcie przeszukuje drugi
zakres tylko raz i zostaje ogłoszone przy wyniku; koniec nie łączy się z początkiem.

„Przejdź do linii” i „Przejdź do strony” numerują istniejące pozycje od jedynki.
CRLF to jeden separator; osobne CR, LF, NEL, U+2028 i U+2029 także kończą linię.
Puste linie liczą się, lecz końcowy separator nie dodaje fikcyjnej linii/strony.
Pusty dokument i sam BOM nie mają linii/stron treści. Strona używa bieżącej
liczby linii na stronę. Zero, błędny zapis, przepełnienie i pozycje poza tekstem
są odrzucane.

„Przejdź do procentu” przyjmuje dziesiętne 0–100 i liczy pozycję w bajtach.
Pozycja wewnątrz znaku UTF-8 cofa się do jego początku, a LF pary CRLF przed CR.
0 wybiera pierwszy bajt treści po początkowym BOM, 100 koniec pliku. Skuteczne
wyszukanie i przejście ogłasza wynik i pozostawia pauzę. Przyjęcie komunikatu
przez kolejkę nie dowodzi późniejszej poprawnej syntezy, wyjścia ani usłyszenia.

Dwie prywatne opcje zapisują się w /.rockbox/tts-reader.cfg. Nowe paczki nie
zawierają tego pliku ani jego tymczasowego rodzeństwa. Błędy zapisu/odczytu są
ogłaszane; nieznane/przyszłe pliki i istniejący plik tymczasowy pozostają zachowane.
Zapis opróżnia bufor, zamyka plik jeden raz i przemianowuje przed zmianą ustawień
w pamięci. Nie gwarantuje to odporności na każdy zanik zasilania. Czytnik nadal
przyjmuje UTF-8; format zakładek, lista muzyki i ABI ustawień pluginów nie zmieniają się.
