# Rockbox Clip+ z eSpeakiem 1.44.05 — etap symulatora

Aktualny etap R1 (2026-10-11) używa dostarczonego silnika r34 i osobnego
symulatora Windows. Bieżący zakres i ograniczenia opisuje `ESPEAK-HIBYR1-PL.md`.
Wydania Sans pozostają niezmienione na r29. Opis etapu poniżej jest historyczny;
nie potwierdza działania R1, Bluetooth ani dotyku na fizycznym odtwarzaczu.

Odświeżenie z 2026-10-10: Clip+ alpha6 i Clip Zip alpha7, zgodnie
z parą firmware `r29-alpha6-20261010` / `r29-alpha7-20261010`. Każdą paczkę
należy sprawdzić oddzielnie; wynik odbioru zapisuje
`Workspace/speech-backends-r1-20261010/final-release-review.json`.
Wcześniejsze wyniki opisują historyczne wersje, nie odbiór tego odświeżenia.

Skrócone ścieżki `Workspace/...`, `Forme/...`, `snapshots/...` i `trash/...`
odnoszą się odpowiednio do `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` i `D:\work\Trash\rockbox` (w WSL pod `/mnt/d/work`).
Aktualne `installfiles/...` znajduje się w `D:\Rockbox\rockbox\installfiles`.
Źródła pozostają w `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` w WSL), a
silnik i dane w `D:\Rockbox\espeak-1.44.05-source`.
Ścieżki takie jak `simdisk` i `.rockbox` pozostają względne wobec programu/urządzenia.

To eksperymentalna integracja wewnątrz procesu Rockboksa, a nie generator
plików .talk ani usługa mowy Windows. Silnik pochodzi z dostarczonego
repozytorium Pates2004/espeak-1.44.05-x64, rewizja
2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f (r29). Zachowano jego słowniki,
w tym poprawki polskiego `ci`, oraz dostarczone warianty głosów.

**To jeszcze nie firmware dla fizycznej Sansy. Nie kopiuj tego programu na
odtwarzacz jako rockbox.sansa i nie zmieniaj nim bootloadera.** Symulator ma
interfejs Clip+, ale wykonuje kod na procesorze komputera. Nie dowodzi
wydajności ani dopasowania do 8 MB RAM urządzenia.

Osobne eksperymentalne wydanie sprzętowe opisuje `ESPEAK-CLIPPLUS-PL.md`.
Firmware ARM i symulator Windows to różne paczki; ten dokument opisuje symulator.
Dodatkowy firmware Clip Zip i jego osobny symulator Windows opisuje
`ESPEAK-CLIPZIP-PL.md`. Firmware Clip+ i Clip Zip nie są zamienne.

## Uruchamianie

Natywny pakiet Windows x64 znajduje się w `installfiles/simwindows` i uruchamia
się plikiem `rockboxui.exe`, bez WSL. Jego instrukcja to `ESPEAK-WINDOWS-PL.md`
w źródłach albo `CZYTAJ.md` w przenośnym pakiecie Windows; angielska instrukcja
w pakiecie nosi nazwę `README.md`. Pakiet zawiera też `ESPEAK.md`, `ESPEAK-PL.md`,
`ESPEAK-TARGETS.md` i `ESPEAK-TARGETS-PL.md`.
Poniższy opis uruchamiania dotyczy wcześniejszej, osobnej wersji Linux/WSL.

Poprzedni pakiet Linux jest archiwizowany w `snapshots`. Opcjonalne nowe
buildy Linux trafiają do `installfiles/clipplus-espeak-simulator`.
W takim pakiecie `Uruchom.cmd` wymaga WSL, Ubuntu-24.04 z WSLg
i biblioteki SDL2. Skrypt nie wymaga konkretnego bieżącego katalogu.
Bezpośrednio w Linuksie: `bash launch.sh`.

Konfiguracja, słowniki, pliki użytkownika i historia pozostają w `simdisk`
obok programu. To symulowany katalog główny odtwarzacza, nie katalog główny
dysku Windows. Wstawiaj tam własne teksty i muzykę. Zachowaj `simdisk/.rockbox`.
Skrypt zapisuje log w `simulator.log`, a pomocnicze dane bibliotek graficznych
i audio w `runtime`, również obok programu. Przekierowanie dotyczy tylko
procesu symulatora, nie globalnej konfiguracji WSL. Katalog programu musi
być zapisywalny; skrypt nie stosuje awaryjnego zapisu w profilu użytkownika.

## Klawiatura Clip+

- Góra/dół: wybór pozycji.
- Spacja lub prawo: wybór/wejście.
- Lewo: powrót.
- Insert: przycisk Home.
- Page Up / Page Down: przyciski głośności.
- Escape: przycisk zasilania; dłuższe przytrzymanie wyłącza Rockboksa.

Okno SDL przedstawia ekran graficzny, nie natywne kontrolki Windows.
Mowa pochodzi z Rockboksa. Nie deklarujemy drzewa UI Automation dla NVDA
ani potwierdzonej współpracy z rzeczywistym czytnikiem ekranu.

## Synteza mowy

Otwórz Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox.
Tutaj włączysz czytnik, ustawisz przyciszanie audio i czytanie tekstu. Podmenu
Ustawienia eSpeak zawiera język, wariant, tempo i jego skalę, wysokość,
głośność, modulację, odstęp między słowami i interpunkcję.
Zmiany zapisuje mechanizm ustawień Rockboksa. Domyślny język głosu „Zgodny z systemem”
śledzi język interfejsu z angielskim jako językiem zapasowym. Głos można też
wybrać niezależnie. Pakiet wybiera początkowo polski interfejs.

Domyślna skala tempa to względne procenty ze znakiem: `(WPM - 175) / 175 * 100`,
gdzie WPM to słowa na minutę. Przykłady po zaokrągleniu w razie potrzeby do jednego
miejsca po przecinku: `0% = 175 WPM`, `-54.3% = 80 WPM`, `-0.6% = 174 WPM`,
`+100% = 350 WPM`, `+157.1% = 450 WPM`, `+671.4% = 1350 WPM`.
Podstawową zapisaną wartością pozostaje całkowita liczba słów na minutę, a krok
w obu skalach wynosi 1 słowo/min. Zmiana skali zmienia tylko sposób prezentacji,
nie zapisaną prędkość ani dźwięk. W obrębie jednej instalacji
`tts rate: 450` nadal oznacza 450 słów/min i jest pokazywane jako `+157.1%`.
Zmiana skali nie zastępuje zapisu WPM zaokrąglonym procentem. Nowe wydania mają
czyste ustawienia domyślne: 175 słów/min / 0%, polski interfejs, głos „System”.
Poprzedni profil i dane pozostają w `snapshots`, nie trafiają do nowego pakietu.
Szczegóły opcji i pakowania opisuje `ESPEAK-WINDOWS-PL.md` w źródłach,
czyli `CZYTAJ.md` w pakiecie Windows.

Zakres wynosi 80–1350 słów/min. Powyżej 450 słów/min natywne przygotowanie
artykulacji i dołączony Sonic przyspieszają dźwięk. Sonic jest pomijany w zakresie
80–450 słów/min; zwykły korpus regresyjny zachowuje dźwięk identyczny bajt w bajt.
Zmiana metody artykulacji na granicy 450/451 może nieznacznie zmienić długość
wypowiedzi, więc nominalne WPM nie gwarantuje dokładnego czasu każdej frazy.
Testy silnika obejmują wszystkie dostarczone języki i warianty, rzeczywistą
długość i wysokość dźwięku, przeliczone pozycje słów, przerwania i odzyskiwanie
po błędach. Pochodzenie i ograniczenia pomiarów opisuje `lib/espeak/README.md`
w źródłach; nie oznacza to testów wydajności na odtwarzaczu ani odsłuchu przez człowieka.

Wysokość i modulacja: 0–99% skali eSpeaka, domyślnie 50%; głośność syntezatora: 0–200%; odstęp:
0–100 jednostek eSpeaka (nominalnie po 10 ms, efekt zależy też
od prędkości). Głośność TTS ma własne ustawienie i nie zależy od głośności
plików głosowych. Główna głośność odtwarzacza nadal wpływa na cały dźwięk.
Warianty odczytywane są
z danych eSpeaka. Wariant domyślny oznacza brak dodatkowej modyfikacji głosu.
Interpunkcja: Brak, Niektóre, Większość lub Wszystkie; korzysta z natywnego
odczytu symboli eSpeaka. Nazwy znaków zależą od słownika wybranego języka.
Nie ma tu SAPI, aplikacji Vario ani MBROLA.

Komunikaty korzystają z tekstów głosowych `.vstrings` z tych samych tłumaczeń
co interfejs. Nie wymagają `.voice`. Nazwy plików, katalogów i inne dynamiczne
teksty trafiają bezpośrednio do syntezatora. „Używaj plików głosowych do czytania
interfejsu”, „Głośność plików głosowych”, „Czytanie nazw katalogów” i „Czytanie
nazw plików” dotyczą wyłącznie nagranej mowy. Wyłączenie tych opcji lub ustawienie
głośności plików głosowych na zero nie wycisza eSpeaka. Przy włączonej syntezie
nazwy są wypowiadane naturalnie, bez numerowania ani używania klipów `.talk`.
eSpeak ma osobny przełącznik „Włącz syntezę mowy”. Tymczasowe blokowanie mowy
i jawnie opcjonalne komunikaty konkretnych wtyczek nadal zachowują swoje znaczenie.
Wyłączenie eSpeaka
przywraca standardowy mechanizm plików głosowych; bez właściwego `.voice`
interfejs wtedy nie mówi.

Nowe pozycje i komunikaty mają tłumaczenia polskie i angielskie. Pozostałe
języki interfejsu używają dla nich angielskiego tekstu zapasowego. Głosy
MBROLA nie są oferowane, ponieważ wymagają niezintegrowanego silnika.

## Czytanie tekstów

Przy włączonym eSpeaku otwarcie `.txt` uruchamia czytnik strumieniowy UTF-8,
również z BOM. Nie ładuje całego dokumentu. UTF-16, błędne UTF-8 i wykryte
dane binarne zgłasza jako nieobsługiwane; nie zgaduje kodowania.
Dotychczasowy Text Viewer pozostaje dostępny przez „Otwórz za pomocą”.

- Spacja: pauza/wznowienie zachowanego bufora mowy, bez powtarzania bloku.
- Góra/dół: zmiana zakresu — znaki, słowa, wiersze, akapity, strony.
- Lewo/prawo: poprzednia/następna jednostka wybranego zakresu.
- Krótkie Escape: zamknięcie i zatrzymanie mowy.
- Po końcu pliku spacja rozpoczyna czytanie ponownie.

Czytnik nie wypowiada automatycznie „rozpoczęto” ani „wstrzymano”. Ekran pokazuje
stan, pozycję bajtową oraz tekst od aktualnego słowa. Kursor podąża za dźwiękiem
pobranym przez mikser, z dokładnością około jednego bufora miksera. Podczas niektórych
nazw interpunkcji stary silnik nie podaje prawidłowej pozycji: kursor pozostaje przy
poprzednim słowie do następnego poprawnego zdarzenia. Zmiana zakresu
lub nawigacja zatrzymuje ciągłe czytanie i wypowiada wybór (dla większych zakresów
podgląd pierwszego wiersza); spacja rozpoczyna czytanie od nowego kursora.

W Ustawieniach eSpeak → Ustawienia czytania tekstu można zapisać zakres nawigacji
i liczbę wierszy na stronie: domyślnie 20, od 1 do 100. Wiersz oznacza rzeczywisty
wiersz pliku, nie zawinięcie na ekranie; akapity rozdzielają puste wiersze.
Znaki to punkty kodowe Unicode, nie całe złożone grafemy; CRLF jest jednym
przejściem do nowego wiersza. Nazwy znaków czyta natywny tryb znakowy eSpeaka,
niezależnie od ustawienia interpunkcji. Nowy wiersz ma własną etykietę; gdy silnik
nie zna nazwy znaku, czyta jego dziesiętny numer Unicode. Długie przeszukiwanie
można przerwać; wyszukanie strony skanuje plik od początku, bez indeksu w pamięci.
Trwałe zakładki korzystają ze wspólnej listy Rockboksa, także ostatnich zakładek.
Przytrzymanie Select (Spacja w symulatorze Sansa) otwiera mówiące menu tekstu:
zakładki, właściwości, początek/koniec i ustawienia. Góra zmienia zakres nawigacji;
pauzę przełącza krótkie Select.
Szczegóły i ograniczenia opisuje `ESPEAK-BOOKMARKS-PL.md`.
PDF, DOCX i EPUB nadal nie są obsługiwane.

Kontrolki i etykiety rejestratora są udźwiękowione, ale nagrywanie, pauza
i wznowienie nagrania nie mogą być wykonywane w SDL: buildy symulatora wykluczają
inicjalizację, obsługę poleceń i odczyt stanu nagrywania. Dodatkowo DMA nagrywania
w SDL jest atrapą i nie może przechwytywać dźwięku z mikrofonu. Dodanie silnika mowy
nie zapewnia działającego rejestratora. Start wypowiada
„Nagrywanie jest niedostępne w symulatorze” bez zmiany stanu i tworzenia nagrania.
Testy polskiego i angielskiego interfejsu potwierdzają komunikat głosowy oraz
działające sterowanie i wyjście. Nagrywanie i mowa na fizycznym odtwarzaczu wymagają oddzielnych testów
routingu audio, pamięci i wydajności.
Ograniczenia nagrywania opisuje `ESPEAK-WINDOWS-PL.md` w źródłach lub `CZYTAJ.md`
w pakiecie Windows.

Mapowanie modeli i ograniczenia opisuje `ESPEAK-TARGETS-PL.md`. Instrukcje native
opisują ograniczony przegląd licencji, niezależnie napisane konwersje liczb,
notices bibliotek oraz przekazanie odpowiadających źródeł. Nie stanowią pełnej
certyfikacji prawnej wszystkich zależności i zasobów do szerszej publikacji.

## Odtwarzanie buildu

```sh
apt-get install build-essential libsdl2-dev libsdl2-image-dev zip unzip
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_simulator.py --platform linux --target sansaclipplus \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source --jobs 12
```

Planowany identyfikator Clip+ dla Linuksa to `0ed3734e5e-espeak-r29-alpha6-20261010`.
Dla Clip Zip wybierz `--target sansaclipzip`: planowany identyfikator to
`0ed3734e5e-espeak-r29-clipzip-alpha7-20261010`, a osobne wydanie trafia do
`installfiles/clipzip-espeak-simulator`. Odpowiedniki Windows opisuje
`ESPEAK-WINDOWS-PL.md`. Źródłowy eSpeak pozostaje w
`/mnt/d/Rockbox/espeak-1.44.05-source` we wskazanej rewizji.
Budowanie Clip+ odbywa się w centralnym `Workspace/build-espeak`, a Clip Zip
w `Workspace/build-espeak-simulator-clipzip`. Silnik linkowany
jest statycznie do Rockboksa; PCM przechodzi przez jego DSP i mikser głosu.
Nie uruchamia się polecenia systemowego `espeak`.

Skrypt nie nadpisuje istniejącej instalacji z danymi użytkownika. Przed
przygotowaniem następcy należy przenieść całe wydanie wraz z danymi do `snapshots`.
Nowa paczka ma pozostać czysta: nie przenoś do niej profilu ani własnych plików.
Odzyskiwanie danych wymaga odrębnej, wyraźnej prośby użytkownika.
Do samej kompilacji służy `--build-only`;
poprzedni rozwojowy plik wykonywalny trafi wcześniej do `snapshots`.
Aktualny finalny plik wykonywalny trafia wyłącznie do `installfiles`;
obiekty kompilacji i raporty pozostają w `Workspace`.

## Dalszy port na sprzęt

Adaptacja usług libc/plików/pamięci i locale jest już zaimplementowana dla
eksperymentalnych buildów ARM Clip+ i Clip Zip. Nadal wymagane są pomiary
pamięci, stosów i wydajności na rzeczywistym urządzeniu oraz testy muzyki,
nagrywania i zapisu ustawień. Konfigurator dopuszcza te dwa cele native oraz
symulatory SDL; pozostałe cele firmware nadal odrzuca. Udana kompilacja i testy
na komputerze nie potwierdzają działania na sprzęcie.

eSpeak jest GPL-3.0-or-later. Licencja i pochodzenie kopii integracyjnej
znajdują się w `lib/espeak` w źródłach, a licencja w pakiecie portable nosi nazwę
`eSpeak-LICENSE.txt`.
