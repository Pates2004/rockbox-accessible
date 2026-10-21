# Rockbox Clip+ / Clip Zip z eSpeakiem — symulatory Windows x64

## Wydania z 2026-10-11

- Clip+: `0ed3734e5e-espeak-r29-win-alpha7-20261011`.
- Clip Zip: `0ed3734e5e-espeak-r29-clipzip-win-alpha8-20261011`.

Odpowiadają firmware `r29-alpha7-20261011` / `r29-alpha8-20261011`.
Manifesty paczek identyfikują osobno każdy target i jego program.
Wcześniejsze wyniki pozostają historyczne i nie potwierdzają nowych wydań.

Skrócone ścieżki `Workspace/...`, `Forme/...`, `snapshots/...` i `trash/...`
odnoszą się odpowiednio do `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` i `D:\work\Trash\rockbox` (w WSL pod `/mnt/d/work`).
Aktualne `installfiles/...` znajduje się w `D:\Rockbox\rockbox\installfiles`.
Źródła pozostają w `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` w WSL), a
silnik i dane w `D:\Rockbox\espeak-1.44.05-source`.
Ścieżki takie jak `simdisk` i `.rockbox` pozostają względne wobec programu/urządzenia.

Nowe menu i trwałe zakładki tekstówek opisuje `ESPEAK-BOOKMARKS-PL.md`.
Przytrzymaj Spację (środkowy Select/Enter); Góra służy tylko do zmiany zakresu.
Zakładki używają wspólnej listy Rockboksa.

Rozszerzone narzędzia i granice dostępności wtyczek opisuje
`ESPEAK-PLUGINS-PL.md`. Wcześniejsza aktualizacja Clip+ alpha4 / Clip Zip alpha5 naprawiła
także zatrzymanie miksera między komunikatami, odtworzone w teście rejestratora.

Uruchom `rockboxui.exe` z pakietu właściwego modelu. Zachowaj cały folder:

- Clip+: `installfiles/simwindows` (wydanie dla Clip+).
- Clip Zip: `installfiles/simwindows-clipzip` (osobne wydanie).

Dodanie Clip Zip nie zastępuje ani nie migruje instalacji Clip+. Każda ma własny
`simdisk`, ustawienia i log; nie mieszaj ich programów, modułów ani danych.
To natywny program Windows, nie skrypt WSL. Do uruchamiania nie potrzeba
Linuksa, Pythona, .NET ani systemowego eSpeaka. SDL2 i silnik mowy są
dołączone statycznie. Zachowaj całą zawartość folderu, nie tylko EXE.

To symulatory, nie firmware ani bootloadery żadnego z fizycznych odtwarzaczy.

W obu przenośnych pakietach Windows ta instrukcja nosi nazwę `CZYTAJ.md`, a angielska
`README.md`. Pakiet zawiera też `ESPEAK.md`, `ESPEAK-PL.md`, `ESPEAK-TARGETS.md`
i `ESPEAK-TARGETS-PL.md`.

Poniższe funkcje opisują wspólną implementację. Wcześniejsze wyniki testów paczki
Clip+ i wspólnego rdzenia są historycznymi dowodami, nie wynikami planowanych
paczek Clip+ lub Clip Zip. Każdy model/wersję sprawdź osobno: start, mowę PL/EN, odtwarzanie ze
ściszaniem, nawigację czytnika, klawiaturę i odmowę nagrywania. Ta instrukcja nie
deklaruje zaliczenia tych testów żadnej z planowanych wersji ani prób sprzętowych/z NVDA.

## Pliki i ustawienia

Własne teksty UTF-8 `.txt`, muzykę i katalogi umieszczaj w `simdisk` obok EXE.
Nie usuwaj `simdisk/.rockbox`: zawiera moduły, słowniki i ustawienia.
Symulator rozpoznaje swój katalog niezależnie od katalogu terminala czy skrótu.
Log `simulator.log` także zapisuje obok EXE i zastępuje przy uruchamianiu.
Katalog programu musi być zapisywalny; brak uprawnień jest błędem, bez
awaryjnego zapisu danych programu w AppData.
Wybierz stosunkowo krótki katalog instalacji: ta wersja eSpeaka ogranicza
pełną ścieżkę do `espeak-data` do 149 bajtów UTF-8. Polskie znaki i spacje
są obsługiwane, ale część znaków zajmuje więcej niż jeden bajt.

Domyślne ustawienia to polski interfejs i język głosu „Zgodny z systemem”. Otwórz:
Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox.
Podmenu Ustawienia eSpeak zawiera parametry syntezy; czytanie tekstu i pozostałe
funkcje czytnika są obok niego. „Zgodny z systemem” śledzi język Rockboksa, również po jego zmianie; brak pasującego
głosu oznacza angielski. Możesz zamiast tego wybrać konkretny język głosu.
Wariant pozostaje niezależny. Ustawienia zapisują się między uruchomieniami.

„Używaj plików głosowych do czytania interfejsu”, „Głośność plików głosowych”,
„Czytanie nazw katalogów” i „Czytanie nazw plików” sterują tylko nagraną mową.
Ich wyłączenie ani głośność plików głosowych ustawiona na zero nie wyciszają
eSpeaka. Synteza ma własne włączenie i głośność; główna głośność odtwarzacza
nadal wpływa na cały dźwięk. Nazwy są syntezowane naturalnie, bez numerowania
i klipów `.talk`. Ta zasada jest wspólna z wydaniami sprzętowymi.

- Skala prędkości: domyślnie względne procenty ze znakiem, obliczane jako
  `(WPM - 175) / 175 * 100`, gdzie WPM to słowa na minutę.
  `0% = 175 WPM`, `-54.3% = 80 WPM`, `-0.6% = 174 WPM`,
  `+100% = 350 WPM`, `+157.1% = 450 WPM`, `+671.4% = 1350 WPM`.
  Procenty są w razie potrzeby zaokrąglane do jednego miejsca po przecinku.
  Podstawową zapisaną wartością pozostaje całkowita liczba słów na minutę;
  jeden krok w obu skalach to 1 słowo/min. Zmiana skali zmienia tylko sposób
  prezentacji, nie zapisaną prędkość ani dźwięk.
- Wysokość i modulacja: 0–99% skali eSpeaka, domyślnie 50%. Zapisane wartości
  i brzmienie pozostają bez zmian; nie są to procenty częstotliwości w hercach.
  Modulacja steruje zakresem zmian wysokości,
  czyli intonacją, a nie dodatkowym efektem dźwiękowym.
- Głośność eSpeaka: 0–200%; odstęp między słowami: 0–100 jednostek silnika.
- Interpunkcja: Brak, Niektóre, Większość lub Wszystkie; korzysta z natywnego
  mechanizmu eSpeaka. Nazwy znaków zależą od słownika wybranego języka.
- Przyciszanie audio: włączone domyślnie. Poziom audio podczas mowy to
  pozostająca głośność muzyki, domyślnie 25%; 0% wycisza, 100% nie ścisza.
  Po zakończeniu albo przerwaniu mowy muzyka wraca do zwykłego poziomu.
  Wyłączenie opcji nie zatrzymuje ani nie wycisza głosu.

Zakres wynosi 80–1350 słów/min. Powyżej 450 słów/min dostarczony silnik przygotowuje
wyraźną artykulację, a dołączony Sonic skraca czas dźwięku bez zamierzonej zmiany
wysokości głosu. Natywny zakres 80–450 słów/min omija Sonic; wcześniejsze testy
wspólnego silnika wykazały identyczny bajtowo dźwięk zwykłego korpusu, nie jest to
nowy wynik testu paczki Clip Zip. Na granicy 450/451 zmienia się metoda
artykulacji, więc możliwa jest niewielka różnica długości wypowiedzi; WPM to
nominalne tempo silnika, nie dokładny pomiar każdej frazy. Nie włącza to SAPI,
Vario ani MBROLA. Licencja i pochodzenie Sonic są dołączone do pakietu.

Każde nowe wydanie ma czysty profil: polski interfejs, głos „System” oraz
175 słów/min / 0%. Nie zawiera poprzednich ustawień, stanu wznowienia ani plików
użytkownika. Zastępowana instalacja tego samego modelu trafia do `snapshots`
wyłącznie do odzyskiwania; dodanie Clip Zip pozostawia dotychczasowy Clip+ na miejscu.
W obrębie jednej instalacji `tts rate: 450` oznacza 450 słów/min i wyświetla się
jako `+157.1%`; zmiana skali nie zastępuje zapisanego WPM zaokrąglonym procentem.
Udźwiękowienie obejmuje
podłączone menu, listy i komunikaty, nie dowolną grafikę ani wszystkie własne
ekrany wszystkich pluginów.
Dołączone pluginy są przebudowane dla ABI tej integracji. Pluginy ze zwykłego
Rockboksa i poprzedniego wydania są odrzucane z komunikatem o niezgodnej wersji;
nie podmieniaj nimi modułów nowego pakietu.

## Klawiatura

Oba modele używają `uisimulator/buttonmap/sansa-clip.c` (w tym gałęzi
`SANSA_CLIPZIP`) i wspólnych działań `apps/keymaps/keymap-clip.c`.
Te mapowania ze źródeł zależą od kontekstu ekranu; nie zastępują testów
dostarczonej paczki.

- Na zwykłych listach Góra/Dół wybiera pozycję, Spacja lub Prawo zatwierdza,
  Lewo lub krótkie Escape anuluje, a Insert emuluje Home/menu.
- Page Up / Page Down emuluje Vol+/Vol-: głośność na ekranie odtwarzania,
  dodatkowy wybór jednostki w czytniku; inne ekrany mogą używać ich inaczej.
- Na ekranie odtwarzania Góra przełącza odtwarzanie/pauzę, Lewo/Prawo zmienia
  utwór (przytrzymanie przewija), a krótkie Escape zatrzymuje odtwarzanie.
- Przytrzymany Escape: bezpieczne wyłączenie i zapis stanu.
- W czytniku tekstu: Spacja lub Insert pauzuje/wznawia zachowany dźwięk, bez powtarzania bloku.
  Góra/dół wybiera znaki, słowa, wiersze, akapity lub strony; lewo/prawo przesuwa
  o wybraną jednostkę. Krótkie Escape zamyka czytnik. Nawigacja pauzuje czytanie
  i wypowiada podgląd; spacja kontynuuje od nowego kursora.
  Zakres i liczbę wierszy na stronie zapisują Ustawienia Talkbox → Ustawienia czytania tekstu.

Zamienniki na klawiaturze numerycznej: 8/2/4/6 = Góra/Dół/Lewo/Prawo,
5 = Select, mnożenie (`*`) = Home, 9/3 = Vol+/Vol-, 1 = Power.
To nie cyfry z górnego rzędu. Spacja, nie Enter, emuluje Select;
Insert, nie klawisz Home komputera, emuluje Home. Escape emuluje Power,
więc działanie krótkiego naciśnięcia/przytrzymania zależy od kontekstu.

Kursor podąża za odtwarzanymi słowami, nie za wyprzedzającą je syntezą.
Start i pauza nie mają automatycznych komunikatów; błędy i koniec tekstu są czytane.
Szczegóły znaków Unicode, stron i podglądu opisuje `ESPEAK-PL.md`, a odtwarzaczy
`ESPEAK-TARGETS-PL.md`. Trwałe zakładki dokumentu korzystają ze wspólnej listy
Rockboksa; opisuje je `ESPEAK-BOOKMARKS-PL.md`.

Najlepiej zamykać program przytrzymując Escape. Nie uruchamiaj równocześnie
dwóch kopii korzystających z tego samego `simdisk`.
Okno SDL samo wypowiada podłączone elementy interfejsu. Nie ma natywnego
drzewa kontrolek Windows dla NVDA; samodzielna mowa nie oznacza jego obsługi.
Czytnik przyjmuje UTF-8, także z BOM, ale nie PDF, DOCX, EPUB ani UTF-16.

## Recorder i wtyczki

Ekran nagrywania w symulatorze ma odczyt wybranego ustawienia i jego wartości,
nazwy pliku, czasu oraz rozmiaru. Czas i rozmiar można wybrać na liście zamiast
polegać na samych wskaźnikach graficznych. Udźwiękowione kontrolki i etykiety nie
oznaczają działającego rejestratora: nagrywanie, pauza i wznowienie nagrania nie
mogą być wykonywane w symulatorze SDL. Buildy symulatora wykluczają inicjalizację,
obsługę poleceń i odczyt stanu nagrywania; dodatkowo DMA nagrywania w SDL jest
atrapą i nie może przechwytywać dźwięku z mikrofonu. Nie jest to tylko brak testu
mikrofonu ani ograniczenie usunięte przez dodanie silnika mowy.

Start wypowiada „Nagrywanie jest niedostępne w symulatorze”, pozostawiając
działające sterowanie i wyjście. Wcześniejsze testy PL/EN wspólnej obsługi
rejestratora potwierdziły ten komunikat, brak zmiany stanu i tworzenia pliku oraz
dalszą nawigację. To wyniki historyczne, nie nowo wykonane testy paczki Clip Zip.
Nie deklarujemy działających przejść stanów nagrywania w żadnym symulatorze.
Nagrywanie, poziomy sygnału, AGC i mowa podczas
nagrywania na fizycznym odtwarzaczu wymagają oddzielnych testów routingu audio,
pamięci i wydajności.

Wspólne menu i listy wtyczek korzystają z rdzenia mowy. Wtyczki rysujące własny
interfejs bez tych mechanizmów nie stają się automatycznie dostępne: wymagają
osobnego podłączenia komunikatów i nawigacji. Nie jest to obietnica udźwiękowienia
każdej gry, przeglądarki grafiki i każdego własnego ekranu.

## Odtworzenie kompilacji

Kompilacja używa WSL Ubuntu; gotowy program już go nie wymaga.
Wymagane pakiety: `build-essential`, `g++-mingw-w64-x86-64`, `zip`, `unzip`.
Pobierz oficjalny `SDL2-devel-2.32.10-mingw.tar.gz` z wydania SDL2 2.32.10
repozytorium `libsdl-org/SDL` i rozpakuj `SDL2-2.32.10/x86_64-w64-mingw32`
oraz `SDL2-2.32.10/LICENSE.txt` do `/mnt/d/work/Workspace/rockbox/toolchains`.
SHA-256 archiwum: `83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2`.
Windows używa domyślnego mechanizmu wątków Rockboksa opartego na Win32 Fibers.
Nie używaj SDL 2.30.0: jej błąd oczekiwania na zdarzenia zamyka tę wersję
symulatora na Windows.

Z katalogu źródeł Rockboksa w WSL wybierz **jeden model**. Domyślny pozostaje
Clip+; dodanie Clip Zip nie wymaga przebudowania Clip+. Kompilację wydania
rozpocznij dopiero po uzgodnionym zamrożeniu źródeł.

Clip+ (tylko przy celowej przebudowie zachowanego wydania):

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_simulator.py --platform windows --target sansaclipplus \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 12
```

Clip Zip:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_simulator.py --platform windows --target sansaclipzip \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 12
```

Clip+ używa `Workspace/build-espeak-windows` i `installfiles/simwindows`;
Clip Zip używa `Workspace/build-espeak-windows-clipzip` oraz
`installfiles/simwindows-clipzip`. Natywny firmware buduje się osobno;
nie instaluj wyniku symulatora jako `rockbox.sansa`.

Źródłowy eSpeak pozostaje w `/mnt/d/Rockbox/espeak-1.44.05-source`
(`D:\Rockbox\espeak-1.44.05-source` w Windows), rewizja
`2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f`. Skrypt odmawia nadpisania
istniejącej instalacji; przed ponownym pakowaniem wybranego modelu przenieś całe
jego poprzednie wydanie wraz z danymi do unikalnej lokalizacji w `snapshots`,
po sprawdzeniu ścieżek, zawartości i tego, że nie jest używane. Poprzednie buildy
również zachowaj tam przed zastąpieniem. Nie przenoś wydania drugiego modelu
tylko po to, aby dodać Clip Zip. Nowy pakiet pozostaw na czystych ustawieniach domyślnych;
nie kopiuj do niego starego profilu, stanu wznowienia ani plików użytkownika.
Opcjonalne narzędzie odzyskiwania `tools/migrate_espeak_simulator.py` nie jest
częścią pakowania i wolno je uruchomić tylko na wyraźną prośbę o przywrócenie
starych danych. Przed przenoszeniem lub przywracaniem oba programy muszą być
zamknięte. `--build-only` buduje wersję roboczą.
Domyślną platformą skryptu budującego jest Windows.
Szczegóły silnika i poprawek integracyjnych znajdują się w `lib/espeak`.
