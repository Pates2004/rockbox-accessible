# Zintegrowany eSpeak: lista celów i testy symulatorów

## Przenośny rdzeń Talkbox i tok pracy, 2026-10-20

[English version](ESPEAK-TARGETS.md)

Talkbox to nazwa interfejsu wspólnej integracji eSpeak działającej wewnątrz
programu. Dalsze prace nad Sansami i iPodem Classic powinny korzystać z tego
rdzenia oraz dostosowywać wejście i usługi platformy. Ekran dotykowy lub usługa
HiBy to osobna możliwość, nie warunek syntezy menu czy czytania tekstu.
Ta sekcja opisuje nowy etap; nie dodaje wyników kompilacji ani prób sprzętowych.

Zamknięty odbiór programowy R1 native alpha13 / Windows alpha16, jego zamrożenie
źródeł, raporty, paczki i sumy pozostają dowodami wyłącznie tego wydania.
Nowe zmiany źródeł
wymagają nowego zamrożenia i świeżej walidacji. Zachowaj istniejące wydania Sans;
ich silniki r29 i ABI wtyczek nie stają się bieżącymi buildami r34 przez zmianę
dokumentacji. Datowane zestawienia poniżej zachowują swój pierwotny zakres.

### Wspólna architektura i granice celu

| Warstwa | Wspólna odpowiedzialność | Odpowiedzialność danego celu |
| --- | --- | --- |
| Synteza | `lib/espeak`, `apps/tts.c`, `apps/talk.c` i `apps/voice_thread.c`: dostarczony silnik, zasady mowy, anulowanie i kolejka PCM | Ograniczony budżet pamięci/stosów, katalogi danych, wątki i integracja wyjścia audio |
| Listy i mowa interfejsu | `apps/gui/list.c`, wspólne menu, ustawienia i katalogi PL/EN: nazwy wybranych pozycji, indeksy, granice, pytania i błędy | Akcje fizyczne/mapy klawiszy oraz obsługiwane możliwości ekranu i wejścia |
| Tekst i zakładki | `apps/tts_reader.c` i `apps/bookmark.c`: nawigacja znak/słowo/wiersz/akapit/strona, kursor powiązany z odczytem, pauza/wznowienie i zakładki tekstowe obok muzycznych | Przypisanie nawigacji, wyboru i menu kontekstowego; zapis i obsługa błędów na tym celu |
| Wtyczki | Wspólne API `talk_*`, listy rdzenia i jawne komunikaty wtyczek | Kompilacja dla celu, mapy klawiszy, dostępne funkcje wtyczek i zgodne ABI |
| Dostępność dotykowa | Wspólna logika gestów, eksploracji i pisania po włączeniu odpowiednich bramek | Kontakty dotyku, współrzędne, wybudzanie/blokada i przypisania przycisków danego celu |
| Usługi platformy | Wspólne kontrakty mowy/miksera i zasady ogłaszania | Natywne sterowniki PCM lub ALSA pod Linuksem; interfejsy Bluetooth, Wi-Fi, zasilania i USB producenta HiBy |

Utrzymuj silnik mowy, czytnik i formaty zakładek we wspólnym kodzie. Nie powielaj
ich dla każdego odtwarzacza. Synteza interfejsu/nazw pozostaje niezależna od
ustawień nagranych plików głosowych; zachowaj działanie lokalnych ustawień
szczegółowości i czasowego wyciszenia mowy. Wspólne listy nie udostępniają
automatycznie własnych pętli rysowania/obsługi wejścia wtyczek. Zobacz
[zakres mowy wtyczek](ESPEAK-PLUGINS-PL.md) i [zakładki tekstowe](ESPEAK-BOOKMARKS-PL.md).

Wspólne zapamiętywane preferencje są w Ustawienia → Ustawienia ogólne →
Dostępność → Ustawienia Talkbox:

- **Ogłaszaj pozycję elementu na liście** (`tts_announce_position`): wspólne
  listy dopowiadają zlokalizowany indeks i liczbę elementów po nazwie wybranej
  pozycji. Sprawdź grupowane wiersze jako logiczne elementy, puste listy i szybkie
  ruchy; wyłączenie opcjonalnego indeksu ma zachować odczyt nazwy. Dostępnych jest
  pięć trybów: Wszędzie, Tylko w interfejsie, Tylko na listach plików, Wszędzie
  oprócz suwaków (domyślnie w czystym profilu) i Wyłączone. Suwaki to wyłącznie
  regulacje zakresów liczbowych; zwykły wybór języka, wariantu i Włącz/Wyłącz
  nadal domyślnie ma indeksy. Zapisane wcześniej Włącz/Wyłącz zachowują znaczenie.
  [Ustawienia list](ACCESSIBILITY-LISTS-PL.md).
- **Informuj o dynamicznych zmianach treści** (`tts_announce_dynamic`):
  automatyczne komunikaty radia korzystają ze wspólnej polityki
  `talk_dynamic_enabled()`. Zachowaj niezależne komunikaty jawnej nawigacji,
  zapytań, ukończenia, błędów i ostrzeżeń bezpieczeństwa. Ogłoszenia FM/RDS nadal
  wymagają rzeczywistych możliwości celu; preferencja nie dodaje tunera ani
  dekodera RDS. Ta osobna preferencja nadal jest domyślnie włączona.

Te preferencje należą do `HAVE_ESPEAK`, nie do `HAVE_TOUCHSCREEN` lub `HIBY_R1`.
To zachowanie źródeł nowego etapu, wymagające świeżych testów, nie wynik
zamkniętego odbioru alpha13/Windows16. Nowe pola `user_settings`, widoczne dla
wtyczek, oraz role list wymagają ABI integracji **`0xe006`**. Zachowane wydania
Sans pozostają przy **`0xe003`**; wcześniejsze generacje R1 używały `0xe004`
i `0xe005`. Ich paczki nie są zgodne z nowym układem źródeł.
Przebuduj wszystkie dołączone wtyczki dla wybranego celu i ABI zgodnego z rdzeniem
w każdej przyszłej paczce native oraz wydaniu symulatora. Odrzucaj moduły
standardowego Rockboxa, starszego ABI i innych celów; zgodna nazwa pliku nie
uzasadnia ich ponownego użycia.

### Bramki możliwości i rzeczywisty stan obsługi

Sprawdź `tools/configure`, dokładny nagłówek celu w `firmware/export/config/`,
wygenerowany `autoconf.h`, `apps/SOURCES`, `firmware/SOURCES` i warunki menu.
Obecność źródeł oraz oznaczenie stabilnego celu w Rockboxie nie potwierdzają
obsługi Talkbox. Najważniejsze istniejące granice:

| Bramka | Znaczenie dla portu |
| --- | --- |
| `--integrated-espeak` / `HAVE_ESPEAK` | Configure dopuszcza obecnie symulatory SDL, natywne `sansaclipplus`/`sansaclipzip` i aplikację `hibyos:hibyr1`; odrzuca bootloadery oraz pozostałe porty urządzeń, w tym natywny `ipod6g`. |
| `HAVE_ESPEAK` bez `HAVE_TOUCHSCREEN` | Wspólna synteza, listy, czytnik, zakładki i mowa wtyczek pozostają ścieżką rdzenia. Wejście fizyczne nadal wymaga integracji akcji/mapy klawiszy danego celu. |
| `HAVE_ESPEAK` z `HAVE_TOUCHSCREEN` | Włącza źródła/menu dostępności dotykowej. `accessibility_buttons.c` jest obecnie wewnątrz tej bramki źródeł mimo swojej nazwy; nie jest automatycznie ogólnym backendem wejścia Sans/iPoda. |
| `HAS_BUTTON_HOLD`, `HAVE_SCREEN_CURTAIN` | Sprzętowa blokada, blokada programowa i kurtyna podlegają istniejącym warunkom. Sprawdź ich połączenie w menu zamiast udostępniać wszędzie kontrolki R1. Kółko iPoda nie jest ekranem dotykowym. |
| `HIBY_R1` z `HAVE_ESPEAK` | Wybiera integrację aplikacji R1 z łącznością/Bluetooth. Natywne backendy producenta wymagają dodatkowo ścieżki urządzenia zamiast `SIMULATOR`; PCM R1 korzysta z osobno warunkowanego backendu HiBy. |
| `CONFIG_TUNER`, `HAVE_RECORDING` i możliwości konkretnego tunera | Sterują FM, nagrywaniem i związanymi komunikatami. RDS sprawdź osobno w sterowniku tunera; ogólna flaga FM nie dowodzi RDS ani działającego nagrywania mikrofonu/radia. |

Nie zakładaj na Sansach ani iPodzie Classic protokołów usług Bluetooth/Wi-Fi
HiBy R1 czy jego routingu ALSA. Te cele wymagają własnych, zweryfikowanych
możliwości platformy; wspólne menu lub zewnętrzny nadajnik Bluetooth nie
przenoszą usługi producenta R1. Inny model pod systemem HiBy także wymaga jawnego
przeglądu. SDL korzysta z backendu komputera, nie z rzeczywistego radia, PCM czy
sprzętu nagrywającego odtwarzacza. Zachowaj bramki kodu platformy i nie pokazuj
nieobsługiwanych kontrolek.

| Cel | Zapisany stan i następny warunek |
| --- | --- |
| `sansaclipplus`, `sansaclipzip` | Zachowane natywne wydania r29 i zgodne symulatory Windows opisują [Clip+](ESPEAK-CLIPPLUS-PL.md), [Clip Zip](ESPEAK-CLIPZIP-PL.md) i [Windows](ESPEAK-WINDOWS-PL.md). Nie walidują nowych wspólnych preferencji, źródeł r34 ani ABI `0xe006`; powrót do Sans wymaga osobno zleconego etapu kompilacji/testów. Nie deklarujemy odbioru sprzętowego. |
| `ipod6g` | Poniżej istnieją historyczne dowody linkowania/startu rdzenia Windows. Natywny zintegrowany eSpeak pozostaje zablokowany w configure; nie ustalono tu istnienia bieżącej natywnej paczki Talkbox ani pełnego odbioru symulatora nowego etapu. |
| `hibyr1` | Zamknięte wyniki programowe native alpha13 / Windows alpha16 dotyczą wyłącznie zapisanych wejść. Odbiór fizycznego R1, dostępności dotyku, Bluetooth/RF, baterii i NVDA pozostaje otwarty. Zobacz [R1](ESPEAK-HIBYR1-PL.md). |
| Inne cele dotykowe lub linuksowe | Makro możliwości pozwala wybrać właściwy kod; nie przenosi odbioru R1 ani zgodności z usługą producenta. Przygotuj osobny zapis kompilacji i testów danego celu. |

### Włączenie nowego celu i kompilacja

1. Ustal dokładny model/rewizję, nazwę celu Rockboxa, CPU/ABI, budżet pamięci,
   modyfikacje pamięci masowej, bootloader i firmware producenta. Dla rozpoznanej
   rodziny Classic używaj `ipod6g`, nie `ipodvideo`; odróżniaj Clip+, Clip Zip
   i Clip. Zachowaj podane niżej uwagi identyfikacji sprzętu. Instalacja
   i operacje firmware wymagają osobnej procedury dla konkretnego urządzenia.
2. Przed włączeniem funkcji ustal możliwości i akcje: nawigację list/czytnika,
   menu kontekstowe, pauzę/wznowienie, powrót/wyjście, blokadę oraz ewentualny
   dotyk/kurtynę. Zachowaj konwencję czytnika Sans: krótki środkowy Select
   wstrzymuje/wznawia, przytrzymanie otwiera menu kontekstowe, a Up pozostaje
   nawigacją. Sprawdź mapowanie kółka/przycisków Classic zamiast kopiować gesty R1.
3. Zapisz zależności i pochodzenie danych. W nowych pracach r34 korzystaj
   z dostarczonych danych drzewa roboczego eSpeak 1.44.05 r34 oraz manifestów,
   zachowując dostarczone zmiany słowników i oryginalny katalog źródłowy.
   Zmierz natywny alokator, stosy, słownik i równoczesne bufory muzyki; RAM
   komputera i `MEMORYSIZE` nie uzasadniają zwiększenia areny ani nie dowodzą
   zmieszczenia programu w urządzeniu.
4. Skoordynuj osoby zmieniające wspólne źródła, zakończ ich poprawki, przejrzyj
   całość i zamroź nowy stan źródeł/danych/narzędzi przed kompilacją. Zapisz cel,
   bramki funkcji, ABI wtyczek `0xe006`, wersje i sumy. Kompilacje natywne wykonuj
   pod Linuksem/WSL z właściwymi narzędziami urządzenia; skrośne Windows używają
   MinGW i sprawdzonego SDK SDL2 opisanego niżej. Nie uruchamiaj testów komputera
   na nagłówkach celu podczas ich wymiany przy przygotowaniu czystej kompilacji.
5. Wybierz istniejący skrypt poniżej. Nowy cel natywny wymaga przeglądu obsługi
   kompilacji, środowiska i pakowania oraz świadomej zmiany bramki configure;
   samo usunięcie odmowy lub ręczne zdefiniowanie `HAVE_ESPEAK` nie wystarcza.

| Zastosowanie | Istniejący skrypt i ograniczenia |
| --- | --- |
| Wykaz / wybrany rdzeń symulatora | `tools/tests/test_tts_targets.py --list-targets` tylko odczytuje listę. Nowe przebiegi `--platform windows --targets ipod6g` lub wybranych Sans budują diagnostyczne rdzenie SDL, nie firmware urządzeń ani pełne wydanie wtyczek. `--build-only` pomija dane uruchomieniowe; pomiń tę opcję przy przygotowaniu nowego raportu testu startu. Pełne przykłady pozostają niżej. |
| Utrzymywany builder symulatora | `tools/build_espeak_simulator.py --platform windows --target ... --build-only` przyjmuje tylko `sansaclipplus`, `sansaclipzip`, `hibyr1`. `--package-only` pakuje istniejący zgodny build; pakowanie jest osobnym krokiem wydania, nie kolejnym testem. Ten builder nie przyjmuje `ipod6g`. |
| Natywne Sansy | `tools/build_espeak_clipplus.py --target sansaclipplus` lub `--target sansaclipzip`, z `--source-frozen` i unikalnym `--version`, kompiluje i pakuje dla tego celu. Nie ma trybu przygotowania `--build-only`; nie traktuj go jako nieszkodliwej próby rdzenia na zachowanych wydaniach. |
| Natywny R1 | `tools/build_espeak_hiby.py --build-only` tworzy diagnostykę. `--stage-hardware-test` wymaga `--source-frozen`, unikalnego `--version`, rzeczywistych `--toolchain-notices` i `--alsa-source`. Późniejsze `--staged ... --publish-hardware-test` jest jawnie eksperymentalne; `--publish` wymaga zamiast tego powiązanego z buildem `--runtime-evidence`. Żaden tryb nie dowodzi odbioru sprzętowego. |
| Natywny Classic / inne nowe porty | Nie podajemy tu obsługiwanej natywnej recepty integracji. Najpierw zaimplementuj i przejrzyj włączenie celu, ograniczone środowisko/integrację audio, pełne kompilacje wtyczek/paczek i walidację odpowiadających źródeł; potem wykonaj świeże kontrole celu. |

### Bramki testów i wydania

1. Po zakończeniu i ustabilizowaniu konfiguracji wykonaj celowane testy syntezy,
   polityki mowy, list, czytnika, zakładek i wtyczek, a następnie odpowiednie
   zestawy regresyjne komputera z rzeczywistymi wygenerowanymi nagłówkami celu.
   Istniejące przykłady to `test_tts_voice_policy.py`, `test_accessibility_lists.py`,
   `test_tts_reader.py`, `test_text_bookmarks.py` i testy polityki/list wtyczek
   w `tools/tests/`. Przebuduj też pełny rdzeń/kodeki/wtyczki: `make bin`
   i obecność symboli po linkowaniu nie walidują takiej paczki.
2. Sprawdź PL i EN z czystymi, odizolowanymi ustawieniami. Skontroluj start
   i rzeczywisty ciąg żądanie → synteza → niezerowy PCM, przerywanie/powrót,
   szybką nawigację pierwsza/ostatnia pozycja, puste/grupowane listy, obie nowe
   preferencje włączone/wyłączone i ich zapamiętywanie. Wyłączenie opcjonalnych
   komunikatów nie może wyciszać nazw, jawnych operacji, błędów i ostrzeżeń
   bezpieczeństwa. Sprawdź nawigację czytnika, kursor/pauzę/wznowienie, zgodność
   zakładek tekstowych/muzycznych oraz błędy zapisu bez zakłócania równoczesnej
   muzyki. Sprawdź uruchamianie wtyczek, błędy danych i odrzucanie złego ABI.
3. Osobno sprawdź wejście i granicę audio platformy. Dla Sans/Classic użyj
   mapowania przycisków/kółka; dotyk, eksplorację, pisanie i wybudzanie/blokadę
   sprawdzaj tylko na właściwych celach. Skontroluj miksowanie muzyki, ponowny
   start PCM, anulowanie, stan/błędy radia i obsługiwane FM/RDS/nagrywanie.
   Atrapy nagrywania SDL nie walidują przechwytywania. Testy środowiska
   linuksowego lub próby MIPS/QEMU nie walidują całego odtwarzacza, usługi
   radiowej producenta ani czasu pracy na baterii.
4. Powiąż każdy raport ze świeżymi wejściami, sumami EXE/paczek, rzeczywistym
   kodem zakończenia, pominięciami i ograniczeniami. Próby symulatora Windows
   wykonuj w prywatnym środowisku bez profilu użytkownika, przejmowania fokusu,
   globalnego wejścia i zmian radia/audio komputera. Sprawdź klawiaturę i mówione
   nazwy/stany; test NVDA odnotuj osobno, ponieważ własna mowa SDL nie stanowi
   natywnego dostępnego drzewa kontrolek. Odsłuch fizyczny, dotyk, RF i energię
   oznaczaj jako niesprawdzone do faktycznego wykonania. Nie awansuj starego
   FAIL ani nie przypisuj dawnego PASS do zmienionych źródeł.
5. Przed wydaniem sprawdź pełną paczkę celu, przebudowane zgodne wtyczki,
   dokładne dane, katalogi/dokumentację PL/EN, odpowiadające źródła, informacje
   licencyjne i sumy. Użyj odczytowego `--verify` istniejących natywnych builderów
   z `--source-archive` oraz właściwego `--target` dla Sans; osobno sprawdź
   rzeczywistą końcową paczkę Windows, w tym czyste ustawienia i przeniesienie.
   Zachowaj zaakceptowane wydania do przejścia bramek przez nowego kandydata.
   Dostarcz jedną aktualną kopię w projektowym `installfiles`: istniejące
   katalogi Sans to `clipplus`, `clipzip`, `simwindows`, `simwindows-clipzip`;
   R1 używa `hibyr1`, `simwindows-hibyr1`. Przyszły skrypt pakujący Classic musi
   określić własną ścieżkę celu. Dane aplikacji zachowaj obok programu.
   Przydatna diagnostyka należy do centralnego `Workspace`, audyt/pochodzenie
   do `Forme`; snapshoty zachowuj tylko do udokumentowanego bieżącego użycia,
   a potwierdzone zbędne materiały przenoś do centralnego `Trash` po kontroli
   ścieżek/procesów/integralności. Nie usuwaj dawnych dowodów i nie twórz
   niepotrzebnych duplikatów wydań.

## Wcześniejszy wykaz i szczegóły odtwarzania prób

Rozwój HiBy R1 ma teraz osobną ścieżkę kompilacji eSpeaka pod Linuksem i osobny
cel symulatora Windows. Zobacz `ESPEAK-HIBYR1-PL.md`, `HIBY-R1-CONTROLS-PL.md`
i `HIBY-R1-INSTALL-PL.md`. Nie oznacza to testu fizycznego R1, stabilnego
Bluetooth ani dostępnej eksploracji dotykiem. Starsze tabele poniżej zachowują
historyczne wyniki symulatorów, a nie pomiary nowej aplikacji R1.

Aktualizacja 2026-10-10: para native to Clip+ `r29-alpha6-20261010`
i Clip Zip `r29-alpha7-20261010`, z odpowiadającymi symulatorami opisanymi
w `ESPEAK-WINDOWS-PL.md`. Wynik ich osobnego odbioru zapisuje
`Workspace/speech-backends-r1-20261010/final-release-review.json`.
Tabele i raporty pomiarowe poniżej zachowują historyczne wersje i daty.

Skrócone ścieżki `Workspace/...`, `Forme/...`, `snapshots/...` i `trash/...`
odnoszą się odpowiednio do `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` i `D:\work\Trash\rockbox` (w WSL pod `/mnt/d/work`).
Aktualne `installfiles/...` znajduje się w `D:\Rockbox\rockbox\installfiles`.
Źródła pozostają w `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` w WSL), a
silnik i dane w `D:\Rockbox\espeak-1.44.05-source`.
Ścieżki takie jak `simdisk` i `.rockbox` pozostają względne wobec programu/urządzenia.

Migrację katalogów dokumentuje
`D:\work\Forme\rockbox\CENTRAL-MATERIALS-2026-10-10.md` i wskazane tam raporty
integralności. Krótkie ścieżki do materiałów poniżej odnoszą się do obszaru
centralnego. Dawne ścieżki zapisane wewnątrz niezmiennych raportów opisują
pierwotny przebieg; odszukuj przeniesione pliki przez audyt migracji, bez
przepisywania dowodów ani przypisywania starych sum nowym testom.

[English version](ESPEAK-TARGETS.md)

Aktualizacja 2026-10-09: tabele opisują historyczne testy symulatorów, nie odbiór
nowych zmian rejestratora/zakładek na każdym celu. Bieżący firmware Sans opisują
`ESPEAK-CLIPPLUS-PL.md` i `ESPEAK-CLIPZIP-PL.md`, zakładki
`ESPEAK-BOOKMARKS-PL.md`. Kompletne stare buildy/raporty A/B/C przeniesiono do
wskazanych lokalizacji `snapshots`, bez zmiany zawartości i sum. Ścieżki wewnątrz
raportów opisują pierwotne uruchomienie. Nie odświeżaj archiwów w miejscu:
utwórz nowy build przez `--targets`; starsze polecenia refresh są historyczne.

Data przeglądu: 2026-10-04. Podstawa źródłowa: commit Rockboxa
`0ed3734e5e34ea6c47ece2ef2c7c8a0fe0fcf325` oraz lokalna integracja eSpeak,
która nie została jeszcze zapisana w commicie. Dokument opisuje ten stan
źródeł, a nie gwarantuje obsługi każdego urządzenia sprzedawanego pod podanymi
nazwami. Poniżej zapisano kompilacje i testy symulatorów Windows; nie budowano
firmware urządzeń ani nie wykonywano zapisu do odtwarzaczy.

## Dokładna tabela celów

Aktualizacja, 2026-10-07: wyniki z 4 października poniżej są historycznymi wynikami
symulatorów, nie bieżącym wykazem buildów native. Eksperymentalne wydanie Clip+
już istnieje; Clip Zip ma osobny cel pakowania native i katalog wydania Windows.
Aktualne instrukcje sprzętowe, źródła/licencje i ograniczenia testów opisują
`ESPEAK-CLIPPLUS-PL.md` oraz `ESPEAK-CLIPZIP-PL.md`. Żaden build nie stanowi
weryfikacji na fizycznym urządzeniu. Późniejsze poprawki licencyjne native opisano
w tych instrukcjach; ustalenia dotyczące libc z 4 października opisują stare źródła.

`tools/configure` określa nazwę celu, numer w menu i wartość `memory`;
`firmware/export/config/<target>.h` określa procesor i możliwości nagrywania.
Liczba przed nazwą celu to **numer w menu configure**, a nie `MODEL_NUMBER`
ani identyfikator celu w katalogu komunikatów głosowych.

RAM w tabeli oznacza skonfigurowane `MEMORYSIZE` w MiB, nie wolną pamięć
dostępną dla eSpeak. Dla portów uruchamianych pod Linuksem jest to budżet
pamięci/buforów Rockboxa, **nie fizyczna pojemność zainstalowanego RAM**.
Fizycznej pojemności RAM tych wariantów tutaj nie ustalono. Wartości portów
natywnych opisują konfigurację pamięci Rockboxa, a nie nowy pomiar.
Nagrywanie oznacza zdefiniowanie `HAVE_RECORDING` przez dany natywny lub
linuksowy cel Rockboxa. Nie oznacza możliwości fabrycznego oprogramowania
ani przetestowania nagrywania razem z syntezą mowy.

| Wskazany odtwarzacz | Numer configure / dokładna nazwa celu | Sposób działania na urządzeniu / architektura | Konfiguracja RAM | Nagrywanie w Rockboxie | Dowody dotyczące symulatora |
| --- | --- | --- | --- | --- | --- |
| Sansa Clip+ | 62 / `sansaclipplus` | Natywnie; AS3525v2, ARM926EJ-S, little-endian | 8 | Tak: mikrofon, radio FM | Istniejąca paczka Windows i szersze testy regresyjne PL/EN |
| Sansa Clip Zip | 65 / `sansaclipzip` | Natywnie; AS3525v2, ARM926EJ-S, little-endian | 8; configure nadal zawiera komentarz `not sure` oznaczający niepewność | Tak: mikrofon, radio FM | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| xDuoo X3 | 241 / `xduoox3` | Natywnie; Ingenic JZ4760B, MIPS32, little-endian | 64 | Nie | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| xDuoo X3 II | 242 / `xduoox3ii` | Pod systemem Linux/HiBy; MIPS32r2, little-endian, ABI kompilacji hard-float | Budżet 8; fizyczny RAM niezweryfikowany | Nie | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| xDuoo X20 | 243 / `xduoox20` | Pod systemem Linux/HiBy; MIPS32r2, little-endian, ABI kompilacji hard-float | Budżet 8; fizyczny RAM niezweryfikowany | Nie | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| Shanling Q1 | 260 / `shanlingq1` | Natywnie; Ingenic X1000, MIPS32r2, little-endian | 64 | Nie | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| iPod Classic | 29 / `ipod6g` | Natywnie; Samsung S5L8702, ARM926EJ-S, little-endian | 64 | Tak: możliwość użycia mikrofonu i wejścia liniowego; wymaga odpowiedniego wejścia/akcesorium, nie oznacza wbudowanego mikrofonu | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| FiiO M3K, port natywny | 246 / `fiiom3k` | Natywnie; Ingenic X1000, MIPS32r2, little-endian | 64 | Tak: mikrofon; `HAVE_RECORDING_WITHOUT_MONITORING` | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| FiiO M3K, starszy port linuksowy | 244 / `fiiom3klinux` | Pod Linuksem; MIPS32r2, little-endian, ABI kompilacji hard-float | Budżet 16; fizyczny RAM niezweryfikowany | Nie | Pominięty w tym przebiegu Windows: przestarzały port linuksowy; rejestr kompilacji oznacza go jako niezdatny do użytku |
| Aigo Eros Q/K; HiFi Walker H2; Surfans F20, rodzina natywna | 247 / `erosqnative` | Natywnie; Ingenic X1000, MIPS32r2, little-endian | 32 | Nie | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| Ta sama rodzina Q/K/H2/F20, port linuksowy | 245 / `aigoerosq` (configure przyjmuje też `erosq`) | Pod systemem Linux/HiBy; MIPS32r2, little-endian, ABI kompilacji hard-float | Budżet 8; fizyczny RAM niezweryfikowany | Nie | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |
| iRiver H320 i H340 | 11 / `iriverh300` | Natywnie; Motorola/Freescale MCF5249 ColdFire, big-endian | 32 | Tak: mikrofon, wejście liniowe, radio FM | Końcowe: E003 + symbole Sonic / start Windows zaliczone; piąta runda |

Dla tych nazw istnieją definicje interfejsu i mapowania klawiszy symulatora,
również dla starszego portu M3K. Obecność źródeł nie dowodzi jednak udanej
kompilacji. W `tools/builds.pm` cel `fiiom3klinux` ma status 1 (niezdatny do
użytku; symulator nie jest domyślnie oferowany), `aigoerosq` ma status 2
(niestabilny), a pozostałe wymienione główne cele mają status 3 (stabilny).
Te oznaczenia projektu Rockbox **nie potwierdzają** obsługi zintegrowanego eSpeak.
Skrypt testowy przyjmuje celowo nazwy kanoniczne, a nie alias `erosq` ani nazwy
handlowe takie jak `hifiwalkerh2`, `surfansf20`, `iriverh320` lub `iriverh340`.

## Identyfikacja sprzętu przed pracami nad firmware

Nazwa „Aigo Eros” nie wystarcza: zestawienie obejmuje **Eros Q/K i rozpoznane
modele pokrewne**, a nie wszystkie odtwarzacze marki Eros. Potrzebne są pełna
nazwa modelu i wersja fabrycznego oprogramowania. Dotyczy to także H2/F20;
nie należy ustalać rewizji wyłącznie na podstawie oferty sprzedaży lub obudowy.

Poniższe zakresy pochodzą z `utils/rbutilqt/rbutil.ini` w tym stanie źródeł.
Są to lokalne dane instalatora, a nie gwarancja dla późniejszych rewizji
producentów.

| Rodzina sprzętu w instalatorze natywnym | Fabryczna wersja Aigo Eros Q | Fabryczna wersja HiFi Walker H2 | Fabryczna wersja Surfans F20 | Cel configure bootloadera |
| --- | --- | --- | --- | --- |
| hw1/hw2 | 1.8-2.0 | 1.1-1.2, 1.4-1.6; **1.3 wymaga innej paczki aktualizacji** | 2.2-2.7 | 247 / `erosqnative` |
| hw3 | 2.1 | 1.7-1.8 | 3.0-3.3 | 248 / `erosqnative_v3` |
| hw4 | 2.2-2.3 | 1.9-2.3 | 3.4-3.5 | 249 / `erosqnative_v4` |

Cele v3/v4 służą **wyłącznie do kompilacji bootloaderów**, co wymusza
`tools/configure`. Nie są dodatkowymi celami firmware ani symulatora i nie
występują na liście skryptu testowego. Wszystkie wiersze korzystają z głównego
celu Rockboxa `erosqnative`. W szczególności H2 1.3 wymaga
`erosqnative-hw1hw2-eros_h2.upt`, a nie używanej w pozostałych przypadkach
paczki `erosqnative-hw1hw2-erosq.upt`. Przyporządkowanie wersji Eros K oraz
niewymienionych wersji producentów pozostaje do potwierdzenia; nie należy
przenosić na nie zakresów Eros Q. Wpisy instalatora dla linuksowych portów H2/F20
są wyłączone i również wskazują paczki zależne od wersji. Port linuksowy nie
jest sposobem na instalację niezależną od rewizji sprzętu.

Cel Classic obejmuje rodzinę Classic, w tym późniejsze modele często nazywane
6.5G/7G; nie jest to `ipodvideo` ani dowolny starszy iPod. Lokalny
`utils/mks5lboot/README` wymienia warianty 80/160 GB z końca 2007 r., 120 GB
z końca 2008 r. oraz 160 GB z końca 2009 i 2012 r., z różnymi wersjami
oprogramowania Apple. Przed instalacją należy potwierdzić urządzenie, jego
firmware oraz ewentualne modyfikacje pamięci masowej. X3 i X3 II to różne porty,
a nie zamienne rewizje. Clip+, Clip Zip i oryginalny Clip również mają odrębne
nazwy celów.

## Co można sprawdzić w symulatorze

Opcja `--integrated-espeak` obsługuje symulatory SDL, eksperymentalne natywne
buildy Clip+/Clip Zip i aplikację linuksową HiBy R1. Pozostałe cele natywne
oraz inne Linux/HiBy pozostają wyłączone.
Osobną paczkę firmware i granice jej walidacji opisuje `ESPEAK-CLIPPLUS-PL.md`.
Pliku wykonywalnego symulatora nie wolno instalować jako firmware odtwarzacza.

Wszystkie opisane symulatory Windows wykonują kod x86-64 komputera, a nie
instrukcje ARM/MIPS/ColdFire odtwarzacza. Plik
`firmware/export/config/sim.h` zeruje `CONFIG_CPU` i wybiera platformę SDL.
Alokacja pamięci, wątki, libc i wydajność komputera nie dowodzą dopasowania do
RAM urządzenia, wystarczającego stosu, poprawnej kolejności bajtów, obciążenia
procesora ani czasu pracy na baterii. Zwłaszcza modele Clip z 8 MiB wymagają
pomiarów pamięci silnika, słowników, stosów i buforów odtwarzania przed
deklarowaniem obsługi firmware. Natywne narzędzia kompilacji MIPS używają flag
soft-float; porty linuksowe korzystają z innych interfejsów systemowych i ABI.

**Symulator nie realizuje rzeczywistego wejścia nagrywania**: funkcje nagrywania
w `firmware/target/hosted/sdl/pcm-sdl.c` są atrapami. Menu nagrywania lub flaga
tej funkcji nie potwierdzają więc nagrywania mikrofonu/radia FM, nagrywania
podczas mówienia ani zachowania sprzężenia mikrofonowego na urządzeniu.

Poniższe raporty diagnostyczne potwierdzają tylko linkowanie rdzenia i ograniczony
test PCM po uruchomieniu. Nie obejmują pełnego odtwarzania, wtyczek, obsługi
wejścia, nagrywania, poprawnego zamknięcia ani dostępności. Interfejs SDL nie
udostępnia natywnego drzewa kontrolek dla NVDA; własna synteza mowy nie dowodzi
dostępności dla NVDA. Przy sporządzaniu zestawienia nie testowano fizycznych
odtwarzaczy ani NVDA.

## Końcowe wyniki celów Windows, 2026-10-05 (piąte odświeżenie)

**10/10 przyrostowych odświeżeń rdzenia i 10/10 natywnych testów startu Windows
zaliczone** z końcową poprawką bloków Sonic i pięcioma poprawionymi polskimi
etykietami. Wszystkie graficzne EXE PE x64 zawierają osiem symboli mowy i siedem
Sonic, porównują ABI wtyczek `0xe003` w zlinkowanym mechanizmie ładowania i nie
importują DLL eSpeak/Sonic. Potwierdza to kompilację, linkowanie i polski start
symulatorów, nie zgodność sprzętu ani pełny odbiór aplikacji na każdym celu.

- A: `snapshots/historical-target-validation-20261004T191216472833Z-20261009T145217378144Z/Workspace/tts-target-tests/20261004T191216472833Z/report.json`; SHA-256 `6908d00a566ec58cdad82c5b0e1b2eb2af36b7d2fdbd15cca5b1545224f82fd2`; refresh `20261004T220142333946Z`.
- B: `snapshots/historical-target-validation-20261004T191216434977Z-20261009T145732427896Z/Workspace/tts-target-tests/20261004T191216434977Z/report.json`; SHA-256 `f0e07ef3bce4379ff6687fd2ba8a18ea7cfa66008d43a5b84a1a06b417d51b74`; refresh `20261004T220203759458Z`.
- C: `snapshots/historical-target-validation-20261004T191216433147Z-20261009T150905061939Z/Workspace/tts-target-tests/20261004T191216433147Z/report.json`; SHA-256 `125a5adec8a4c2cfb66c00c294d64956bc2f02a48f2d0349059be967caa3fffb`; refresh `20261004T220206076166Z`.

| Cel | Grupa | Refresh E003 / start Windows | Sekundy make w refresh | Niezerowe próbki PCM | SHA-256 EXE piątej rundy |
| --- | --- | --- | --- | --- | --- |
| `sansaclipzip` | A | ZALICZONY / ZALICZONY | 25.154 | 30704 | `a3e5bde7f148660e5a0a5a59d1cc1b406d319021ec602c7ba1fe6588325ff577` |
| `xduoox3` | B | ZALICZONY / ZALICZONY | 21.676 | 30704 | `8e4f2bb462e09ef4af7f68eefe8cca7347490a6a9859b62fa50a698caf96ffda` |
| `xduoox3ii` | B | ZALICZONY / ZALICZONY | 21.651 | 30704 | `f7e2eaccc05530268d6a631b3c0ae8cca7b8bd61bc507cf9b42e8ee42f5d2246` |
| `xduoox20` | B | ZALICZONY / ZALICZONY | 21.311 | 30704 | `1b5e6aa0c0cc6e194f1254fac43877acc04154e3fd6b77152e0b30c6ec9c68be` |
| `shanlingq1` | B | ZALICZONY / ZALICZONY | 22.306 | 30906 | `c3efa55dc31ba15131710352056a56c3f75ce9dab7b6b0ddec210d1c3af64cc9` |
| `ipod6g` | A | ZALICZONY / ZALICZONY | 23.039 | 30704 | `4738e1a700bd968215765c6189eacdead5773ff23c7cdc87cc7fbc29c2bf21aa` |
| `fiiom3k` | C | ZALICZONY / ZALICZONY | 23.070 | 30906 | `3c38a0a4fc35abe7e9c08ab54827acb731bb24010bc8a39406c10d330b1ffcbc` |
| `erosqnative` | C | ZALICZONY / ZALICZONY | 22.813 | 147242 | `bbf63bad918058c33593cc2d91e7f359526c9bd875df41b68c27a46d1e77d681` |
| `aigoerosq` | C | ZALICZONY / ZALICZONY | 21.663 | 30704 | `fc3c57ac32ce9d499ea104d1831b1eb59325dc1fc22227b5ef3f38313c833746` |
| `iriverh300` | A | ZALICZONY / ZALICZONY | 23.660 | 30704 | `735b50f8bd04afb2d3816b73f49af1fbcebd001a2df26ec95db7e8a2cad032cf` |

Wszystkie 41 sum źródeł przed/po kompilacji jest zgodnych między dziesięcioma
celami i stanem źródeł podczas niezależnej kontroli końcowej. SHA-256 kanonicznego
słownika źródeł (posortowane klucze JSON, separatory `(',', ':')`, UTF-8):
`b8eccced0995394ee231d147d5c7d825eb5316819656fd2bab34303c75fdaee6`.
Najważniejsze sumy źródeł:
- `lib/espeak/rb_espeak.cpp`: `3e0c3c8087776497a26a29422ed05bc79cdf1fdc62683fe875243f3985e435f4`.
- `apps/lang/polski.lang`: `39e8fab5231ee26dea135dfbed3122ca56471ef38866a8e9cf1a0c9d78c6d1d8`.

Pełne sumy źródeł, rozmiary EXE, sumy katalogów/audio/logów, ostrzeżenia i kontrole
archiwizacji: `Workspace/tts-target-tests/final-sonic-pl-round5-20261005.json`,
SHA-256 `ae2882360353de113bc56880a9a2b41f865dbf77c66ded8549e6487bffc09749`.
Zgodne są także 51 sum źródeł w
`Workspace/espeak-sonic-chunks-20261004/source-freeze.json`;
SHA-256 tego pliku: `f0aeb7ec6cf1414a185338b390bbea266d3c923dd7857a393056be8d5544d70b`.
Jego logi testów backendu normal, ASan, UBSan, Windows i bez Sonic zawierają PASS.

Każde odświeżenie wygenerowało ponownie `english.list` oraz katalogi tekstu/mowy
PL/EN: łącznie 50 plików. Cztery katalogi binarne każdego celu zawierają wszystkie
38 niepustych etykiet TTS, w tym komunikat o niedostępnym nagrywaniu. Wszystkie
polskie katalogi tekstu/mowy zawierają `Wymuś` oraz
`Wyjątek: przewijanie/pomijanie/odtwarzanie/głośność` jako pięć osobnych etykiet;
sprawdzono też odpowiadające im etykiety angielskie. To kontrola katalogów, nie
test działania nagrywania ani pełnego interfejsu w obu językach.

Odświeżanie używało WSL Ubuntu-24.04, przyrostowego `make bin` oraz
`--jobs 4 --timeout 1800` na grupę. Natywne testy startu przebiegły kolejno
**2026-10-05 CEST**: A 00:03:09.692-00:03:17.680,
C 00:03:41.613-00:03:49.627, B 00:04:22.082-00:04:32.995.
Wszystkie polecenia refresh/smoke zakończyły się kodem 0. Obraz: Windows, nie
dummy; dźwięk do pliku, ukrywanie wyłącznie okna PID danego testu, bez wysyłania
klawiszy. Każdy profil zachował 175 WPM (0% w skali ze znakiem) i wypowiedział
`Pliki`. Kod 1 symulatora oznacza celowe zakończenie po kontroli startu, nie test
poprawnego zamykania. Licznik PCM natywnego Eros obejmuje resztkowe próbki -1;
nie oznacza dłuższej wypowiedzi.

Osobny test wysokiego tempa Clip+:
`Workspace/sonic-simulator-tests/20261004T214738084909Z/report.json`.
451 WPM trwało 22.430476 s, 1350 WPM 8.219864 s; iloraz 0.3664596273.
Zapisano zaliczenie kontroli pauzy/kursora/wznawiania/nawigacji/miksera/zamykania.
SHA-256 użytego tam EXE:
`28b12ef3da4f3bf85ce5a2ae19def2765e368f120dd5d9e726c4bbfbe618675c`.
Wynik zastępuje wcześniejszą bazę z głodzeniem potoku i ilorazem 1.018181818;
**nie jest** testem GUI wysokiego tempa tych dziesięciu celów ani oceną późniejszej
paczki użytkowej.

Logi make piątej rundy nie zawierają ostrzeżeń/błędów. Kompilacja przyrostowa nie
unieważnia wcześniejszych ostrzeżeń MinGW o intrinsic ani Win64 o szerokości
wskaźników. Pozostają komunikaty SYSFONT i braku opcjonalnych ikon/teł (bez
komunikatów o brakujących zasobach dla X3). Wpisy `CRITICAL` sterownika SDL disk
wskazują celowe przechwytywanie audio do pliku. Te testy startu nie potwierdzają
sprzętu, NVDA, pełnego UI, angielskiego interfejsu w działaniu, czytnika przy
wysokim tempie na każdym celu, nagrywania, miksowania ani dołączonych wtyczek.

Czwarta runda była zaliczona, lecz zastąpiła ją końcowa zmiana polskiego katalogu;
zachowano ją w historii piątej rundy. Nie usunięto raportów ani wcześniejszych
błędów. Niezależnie sprawdzono 12 archiwalnych raportów grup, 348 przeniesień
z manifestów czterech rund historii, 50 snapshotów EXE odświeżeń, dwa pierwotne
snapshoty X3/Q1, 2830 plików danych silnika i 50 bieżących katalogów. Starsze EXE
są w `snapshots`, raporty/logi/historia katalogów w `Workspace`. Dziesięć
izolowanych środowisk zachowano do powtarzalnych testów diagnostycznych, nie jako
wydania dla użytkownika. Poniższe historyczne odwołania wskazują niezmienne wersje.

## Historyczna baza Sonic Windows, 2026-10-04 (trzecie odświeżenie)

**10/10 odświeżeń rdzenia E003 i 10/10 natywnych testów startu Windows zaliczone**
dla wskazanego stanu źródeł. To zakończona baza diagnostyczna,
**nie końcowy odbiór funkcji Sonic**. W tej bazie zgłoszono problem wydajności czytnika/kursora
przy wysokim tempie, niebadany w tej macierzy celów. Późniejszą poprawkę
i odrębny test Clip+ opisano w końcowych wynikach powyżej.
Wyniki nie potwierdzają późniejszych zmian backendu ani zgodności z urządzeniami.

Wszystkie graficzne rdzenie PE x64 zawierają osiem symboli mowy i siedem Sonic,
ABI `0xe003` w zlinkowanym mechanizmie ładowania, bez zewnętrznej DLL eSpeak/Sonic.
Zregenerowano pięć plików katalogów każdego celu; katalogi tekstu i mowy PL/EN
zawierają wszystkie 38 identyfikatorów TTS, w tym etykietę niedostępnego nagrywania.
Obecność etykiety nie dowodzi działania zabezpieczenia nagrywania. Start używa
języka polskiego i kanonicznego tempa 175 WPM (0% w skali ze znakiem), a nie
ścieżki Sonic przy tempie 1350 WPM.

- A: `snapshots/historical-target-validation-20261004T191216472833Z-20261009T145217378144Z/Workspace/tts-target-tests/20261004T191216472833Z/refresh-history/20261004T215250603457Z/report.json`; SHA-256 `3b1b930f603b5d10bb000cd595db6bf5420deb9f56b7472006ed0ba06051ad45`; refresh `20261004T212619264801Z`.
- B: `snapshots/historical-target-validation-20261004T191216434977Z-20261009T145732427896Z/Workspace/tts-target-tests/20261004T191216434977Z/refresh-history/20261004T215308757558Z/report.json`; SHA-256 `79335446220c8dcd2e3064a065da5a490d4315c30036004d12a1f5d5859436a2`; refresh `20261004T212637090837Z`.
- C: `snapshots/historical-target-validation-20261004T191216433147Z-20261009T150905061939Z/Workspace/tts-target-tests/20261004T191216433147Z/refresh-history/20261004T215358448847Z/report.json`; SHA-256 `43f237f8bdb6c1c26c42b901c24c897bee296938f631e00dae524784c68bd131`; refresh `20261004T212845522206Z`.

| Cel | Grupa | Refresh E003 / start Windows | Sekundy make w refresh | Niezerowe próbki PCM | SHA-256 EXE trzeciej rundy |
| --- | --- | --- | --- | --- | --- |
| `sansaclipzip` | A | ZALICZONY / ZALICZONY | 63.868 | 30704 | `b5ddde138e72e47034883db358cc6e66be555e42e8acc09aad6a4cc82f29df90` |
| `xduoox3` | B | ZALICZONY / ZALICZONY | 55.072 | 30704 | `61f32a63383c41c89cc506b238eb35eb932c2ea6a243abcf2d0d5d76e0dc8e4d` |
| `xduoox3ii` | B | ZALICZONY / ZALICZONY | 62.051 | 30704 | `25430e53a1f62809d463e3bf691260d523fe8fdc1d66efe849e14e19048c9177` |
| `xduoox20` | B | ZALICZONY / ZALICZONY | 70.908 | 30704 | `0f9950b67a06e7fad00b2d3902d333ee10b575a02d7ea026fa2da35896c8e77f` |
| `shanlingq1` | B | ZALICZONY / ZALICZONY | 60.722 | 30906 | `a27600f52ae5f83978b0d0a8fc3e03114e6c10b1f320d5fd4d228b13d35cd386` |
| `ipod6g` | A | ZALICZONY / ZALICZONY | 69.567 | 30704 | `a448954fa96e4f4b3f0d4b791d1d44d0bf907af4fd48371afa88f8a449b7931b` |
| `fiiom3k` | C | ZALICZONY / ZALICZONY | 74.979 | 30906 | `3544e470190fa72394dfae38f254955cedfa77817b67a4d9d07fc87460399d9f` |
| `erosqnative` | C | ZALICZONY / ZALICZONY | 57.250 | 134954 | `8914f45ccd829e8fbbd849cc80febe6b849b36fffc75f269a2a3856e7b02f1aa` |
| `aigoerosq` | C | ZALICZONY / ZALICZONY | 48.166 | 30704 | `7b04749c0be8890f3e15e4621ba9459aeb7d498b557f31620d2ce5cbb8426ede` |
| `iriverh300` | A | ZALICZONY / ZALICZONY | 78.086 | 30704 | `023c1b43527e943503f850386c5d00098690700cec3c21fbad08df3af89d63f0` |

Wszystkie 41 sum źródeł przed/po kompilacji było zgodnych między dziesięcioma
celami i stanem źródeł podczas niezależnej kontroli (21:35:08 UTC). SHA-256
kanonicznego JSON (posortowane klucze, separatory `(',', ':')`, UTF-8) wynosi
`62565adcf4c242a9e119dd170123fafc3b34d6ccb859917bd84fc82e5450e9f9`.
Zgodne były też wszystkie 51 sum przekazanych plików backendu. Pełne sumy wejść
oraz niezależne kontrole EXE/katalogów/danych/historii zachowano w
`Workspace/tts-target-tests/sonic-baseline-round3-20261004.json`, SHA-256
`b96a3da33a80edb46c905c2dd64c048606dfeccbc9b16049ddd9b90b2b1d5038`.

Testy startu przebiegły kolejno, z obrazem Windows (nie dummy), dźwiękiem do
pliku i ukrywaniem okna należącego do danego PID, bez klawiatury:
A 23:31:07-23:31:15, B 23:31:55-23:32:06, C 23:32:52-23:33:00 CEST.
Wszystkie polecenia refresh/smoke zakończyły się kodem 0; każdy symulator
celowo zakończono kodem 1. Nie jest to test poprawnego zamykania programu.

Dziesięć poprzednich EXE przeniesiono do
`snapshots/tts-target-before-abi-validation-<cel>-<runda>/rockboxui.exe`.
Poprzednie raporty, testy startu, katalogi i logi ich generowania zachowano według
mapowań `refresh-history/<runda>/manifest.json`: 110 przeniesień w tej rundzie,
168 w obu zapisanych rundach historii. Niezależna kontrola objęła te artefakty,
2830 plików danych silnika i 50 bieżących plików katalogów. Nie utracono
poprzednich błędów ani wersji raportów; odwołania do raportów wcześniejszej bazy poniżej
wskazują teraz ich niezmienne kopie w historii.

Pozostało osiem wierszy ostrzeżeń make: cztery pary o przyszłym czasie pliku
oraz rozbieżności zegarów, dla Clip Zip (0,19 s), iPoda (0,043 s), X3 (0,36 s)
i natywnego Eros (0,25 s). Sprawdzono odpowiednie wygenerowane nagłówki i
przebudowane pliki obiektowe: obiekty są nowsze od źródeł/nagłówków, a EXE od
obiektów. Ostrzeżenia zachowano, nie wyciszono. Te przyrostowe logi nie zawierają
ostrzeżeń kompilatora C/C++; nie oznacza to czystej kompilacji bez ostrzeżeń.
Wcześniejsze ostrzeżenia o szerokości wskaźników Win64 nadal stanowią ryzyko
renderowania. Pozostają komunikaty SYSFONT i brak opcjonalnych ikon/teł; liczby
niezerowych próbek obejmują wartości resztkowe i nie mierzą czasu mowy.
Pozostałe ograniczenia opisane niżej nadal obowiązują.

## Historyczne wyniki Windows, 2026-10-04 (drugie odświeżenie)

Wyniki dotyczą wyłącznie zakończonego drugiego odświeżenia, sprzed skali tempa
ze znakiem, integracji Sonic, zmiany polskiej etykiety interpunkcji i dalszych
poprawek katalogów PL/EN. Pozostają historycznymi dowodami, nie potwierdzeniem
tych późniejszych zmian. Określenie wyników jako końcowych w tej sekcji oznacza
końcowe wyniki drugiej rundy.

**10/10 końcowych odświeżeń E003 i 10/10 natywnych testów uruchomienia Windows
zaliczone** po poprawkach etykiet nagrywania i kolejności inicjalizacji SDL.
Clip+ ma osobną paczkę i testy regresyjne; nie jest jedenastym wynikiem tutaj.
Przestarzały, niezdatny do użytku `fiiom3klinux` jest celowo
pominięty; aliasy handlowe i cele bootloaderów `erosqnative_v3`/`erosqnative_v4`
nie tworzą dodatkowych celów symulatora.

Każdy graficzny PE Windows x64 używa SDL 2.32.10, zawiera osiem wymaganych symboli
mowy i porównanie `0xe003` w zlinkowanej funkcji `plugin_load`, bez zewnętrznej DLL
eSpeak. To diagnostyka rdzenia, nie pełne paczki wtyczek/kodeków/programu. Dowody:

- A: `snapshots/historical-target-validation-20261004T191216472833Z-20261009T145217378144Z/Workspace/tts-target-tests/20261004T191216472833Z/refresh-history/20261004T212619264801Z/report.json`; SHA-256 `1a3d6c610a66da1ba7396a24a7a7524a08d4798ef914462c80e12a1fedcb9450`; refresh `20261004T202259171769Z`.
- B: `snapshots/historical-target-validation-20261004T191216434977Z-20261009T145732427896Z/Workspace/tts-target-tests/20261004T191216434977Z/refresh-history/20261004T212637090837Z/report.json`; SHA-256 `4a2d3346fd45aab8bf55c1dbb3de17dfd1d5552daeb3f2cfb1b69f3966fe68f6`; refresh `20261004T202456612777Z`.
- C: `snapshots/historical-target-validation-20261004T191216433147Z-20261009T150905061939Z/Workspace/tts-target-tests/20261004T191216433147Z/refresh-history/20261004T212845522206Z/report.json`; SHA-256 `25144507faca1c220732a290ce1a14c3c408e56e01592c544111f80a0095e0f2`; refresh `20261004T202500354544Z`.

| Cel | Grupa | Refresh E003 / start Windows | Sekundy make w refresh | Niezerowe próbki PCM | SHA-256 EXE drugiej rundy |
| --- | --- | --- | --- | --- | --- |
| `sansaclipzip` | A | ZALICZONY / ZALICZONY | 97.943 | 30704 | `11930609806af5e85949ac3edb5fefb306b95a5cc27141def1dce9c87a28c513` |
| `xduoox3` | B | ZALICZONY / ZALICZONY | 125.246 | 30704 | `7424e5f8b1486a8797fb79e1012d964b2858354a7aa2de436166c3a9ac124d7d` |
| `xduoox3ii` | B | ZALICZONY / ZALICZONY | 117.699 | 30704 | `19c25da84aedb2e4864e1a456969813b35ab2b461470112e4b41e43e915315fc` |
| `xduoox20` | B | ZALICZONY / ZALICZONY | 89.177 | 30704 | `0246f89f171b1bc4b3780913e3fe44e9f3105e71949323db64c5da1e260bdc64` |
| `shanlingq1` | B | ZALICZONY / ZALICZONY | 96.583 | 30906 | `590f87362d2705e0f4f5526ab92d9f84a6f13f7c953d863e894602d0ff2ab657` |
| `ipod6g` | A | ZALICZONY / ZALICZONY | 136.054 | 30704 | `14db8b8466ca2676787ae2437e6a05a49881b0e9ca3caacb0434be1369e0fad4` |
| `fiiom3k` | C | ZALICZONY / ZALICZONY | 139.583 | 30906 | `edad8c82ba396177bf68c5ced9c474aa5d4571d12d0c0ec1c4c8d2b65f19f135` |
| `erosqnative` | C | ZALICZONY / ZALICZONY | 130.819 | 134954 | `6d96a37b715a8a66a24b64ea4b3c7581381f64e6fbaf60b77dc93b76a1086350` |
| `aigoerosq` | C | ZALICZONY / ZALICZONY | 88.877 | 30704 | `ae2ebc0fcafbbcc60106b190dcdf959f0ab5bf48f27cb368c20e86f340e42ada` |
| `iriverh300` | A | ZALICZONY / ZALICZONY | 135.927 | 30704 | `305bb95b5f2d87f338bb44cac8b7447c7d2658ec663571e060edb538c71e310d` |

W chwili weryfikacji słowniki sum źródeł przed i po kompilacji wszystkich 10 celów
były równe sobie oraz zgodne z ówczesnym zamrożonym drzewem roboczym. SHA-256 ich kanonicznego JSON (posortowane
klucze, separatory `(',', ':')`, UTF-8) wynosi
`df914b7021f3f3b21c06ed02fab3e7473a39d99358dab59743d04c308daf3ca5`. Raporty zachowują 30 pojedynczych
sum źródeł, rozmiary EXE, importy, porównania ABI, sumy 283 plików danych silnika
na cel, katalogów PL/EN, czasy pierwszej kompilacji/refresh oraz sumy PCM/logów.
Niezależna kontrola po smoke potwierdziła końcowe sumy źródeł, EXE, PCM i logów
oraz wszystkich 58 przeniesionych artefaktów z trzech manifestów historii.

Smoke używał natywnego Pythona Windows, `SDL_VIDEODRIVER=windows`, renderowania
programowego, dźwięku zapisywanego na dysk i ukrywania wyłącznie okna PID testu,
nie pozornego obrazu dummy. Nie wysyłano klawiszy. Przedziały CEST:
A 22:30:09-22:30:18, C 22:31:57-22:32:06, B 22:32:15-22:32:27; dokładne początki
UTC są w raportach. Każdy surowy log zawiera `TTS utterance: Pliki`, język polski,
tempo 175 i interpunkcję 0. Każdy PCM ma co najmniej 30 228 próbek o wartości
bezwzględnej większej niż 1. Procesy celowo kończono; zapisany kod `0x00000001`
nie potwierdza poprawnego zamknięcia. To przechwycona synteza, nie test jakości
odsłuchu ani fizycznych głośników.

### Ostrzeżenia i ograniczenia

- Sześć początkowych błędów wyłącznie zmiany źródeł pozostaje w `prior_build_failure`.
  Pierwszy refresh i sześć zaliczonych smoke stały się historyczne po dalszych
  poprawkach; niezmienna historia zachowuje je. Druga runda nie ma zmiany
  źródeł, błędów kompilacji/ABI ani błędu syntezy przy starcie.
- Logi drugiej rundy zachowują ostrzeżenie MinGW o granicach tablicy dla
  `__readgsqword`/`GetFiberData` w `intrin-impl.h:838`. X3 II, X20 i Eros hosted
  zachowują po osiem ostrzeżeń szerokości wskaźników/liczb w
  `firmware/drivers/lcd-24bit.c`. Konwersje przez `long` pozostają ryzykiem
  renderowania Windows x64; start bez pełnych zasobów tła nie sprawdza wszystkich
  dotkniętych ścieżek ani nie naprawia problemu.
- Początkowe logi zawierają też ostrzeżenie konwersji liczby na wskaźnik w
  `lib/skin_parser/skin_debug.c:45` i komunikat configure o założeniu little-endian.
  H300 początkowo zgłasza czas pliku 0.0072 sekundy w przyszłości i rozbieżność
  zegara; żaden log drugiej rundy refresh nie zawiera rozbieżności zegara.
- Wszystkie cele zgłaszają ostrzeżenie SYSFONT; poza X3 również brak opcjonalnych
  BMP ikon/tła. Wpisy `CRITICAL` SDL disk zapowiadają celowy zapis, nie błąd
  syntezy. Minimalne środowiska nie są pełnymi paczkami interfejsu.
- Eros native zapisuje `verify_device_dataTTS: Pliki` bez końca linii, przez co
  podsumowanie `speech`, wymagające początku linii, jest puste mimo surowego
  dowodu wypowiedzi/parametrów. Liczba niezerowych próbek obejmuje wiele
  resztkowych `-1`; zakres amplitudy to -731..728, a 30 228 próbek ma wartość
  bezwzględną ponad 1. Większy licznik nie oznacza więcej treści ani lepszej jakości.
- Nie testowano tu angielskiej wersji w działaniu, pełnego czytnika/nawigacji
  klawiaturą, miksowania, nagrywania, wtyczek/kodeków, NVDA, poprawnego zamknięcia,
  wielokrotnych startów pod obciążeniem ani fizycznych odtwarzaczy. Katalogi EN
  nie potwierdzają działania wersji EN; szersze wyniki Clip+ nie przenoszą się.
  **Nie potwierdzono zgodności sprzętu, zmieszczenia się w jego zasobach, pełnej
  dostępności ani rozstrzygnięcia kwestii licencji/dystrybucji.**

### Zarchiwizowane starsze EXE X3/Q1

Po zaliczeniu zamienników stare EXE E002 przeniesiono z
`Workspace/tts-target-tests/20261004T175730583982Z/<cel>/rockboxui.exe` do
`snapshots/Workspace/tts-target-tests/20261004T175730583982Z/<cel>/rockboxui.exe`.
Sprawdzono pochodzenie, zawartość/rozmiar PE, zakres ścieżek, wyłączny dostęp
oraz działające procesy. Poniższe SHA-256 pozostały niezmienione:

- `xduoox3`: `e37687b0259f0d2cc6248f69ab1b178c96e8e2c1125c1fdb9fa13893f2595e2a`
- `shanlingq1`: `f4360a2840e46e87146c34c8fa918ed30f11360d0ca8c4d25ce687a9ac03944f`

Historyczny raport i 23 logi pozostały niezmienione w Workspace. Pola `directory`
opisują dawne miejsca kompilacji, nie obecne ścieżki EXE; należy użyć tego
mapowania, a nie ponawiać smoke wycofanego raportu. Bieżące diagnostyczne EXE,
izolowane dane i logi pozostają w Workspace, nie w `installfiles`. EXE starszych
odświeżeń są w snapshotach wskazanych w raportach. Nie utworzono duplikatu
EXE/wydania dla użytkownika i niczego nie usunięto z trash.

## Wybór celów i koszt kompilacji

Wyświetlenie listy niczego nie zmienia i działa w PowerShellu pod Windows
bez WSL ani SDK:

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
python -B tools/tests/test_tts_targets.py --list-targets
python -B tools/tests/test_tts_targets.py --help
```

Poniższe polecenia to **przykłady przyszłych kompilacji**, a nie zakończone
testy. Kompilację należy uruchamiać pod WSL z głównego katalogu repozytorium.
Aby przygotować wszystkie 11 głównych celów Windows do testu uruchomienia,
należy podać pełną listę bez opcji `--build-only`:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/tests/test_tts_targets.py --platform windows \
  --targets sansaclipplus sansaclipzip xduoox3 xduoox3ii xduoox20 shanlingq1 \
    ipod6g fiiom3k aigoerosq erosqnative iriverh300 \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 4 --timeout 1800
```

Opcjonalny test samej kompilacji jednego celu, bez danych do uruchomienia:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/tests/test_tts_targets.py --platform windows --targets sansaclipzip \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --build-only --jobs 4 --timeout 1800
```

- Domyślny wybór nadal wynosi `xduoox3 shanlingq1`; skrypt nie rozszerza go
  automatycznie do dwunastu nowych kompilacji. `--targets` wybiera jedną lub
  więcej niepowtarzających się nazw.
- `--build-only` pomija słowniki, katalogi komunikatów głosowych i przygotowanie
  symulowanego dysku. Zwykła kompilacja przygotowuje odizolowane dane dopiero
  po sprawdzeniu zlinkowanego rdzenia. Każda taka kopia jest zapowiadana
  i weryfikowana sumami kontrolnymi na potrzeby późniejszych testów uruchomienia.
  Te przydatne kopie diagnostyczne pozostają w `Workspace/tts-target-tests`.
- Raport build-only nie nadaje się bezpośrednio do testu uruchomienia. Dla celów
  wymagających uruchomienia należy pominąć `--build-only`. Chroniony tryb refresh
  może przygotować brakujące dane dopiero po przebudowie i weryfikacji rdzenia,
  przy zgodnym pochodzeniu silnika; nie jest osobnym trybem kopiowania danych.
  Niezapisane w raporcie, częściowe środowisko uruchomieniowe zostaje odrzucone.
- Skrypt wykonuje `make bin`, nie pełną kompilację kodeków, wtyczek i paczki.
  Cele są przetwarzane kolejno; `--jobs` steruje równoległością make wewnątrz
  każdego celu. Na słabszym komputerze warto zacząć od 2-4 zadań i używać
  istniejącego sprawdzonego SDK, zamiast instalować dwanaście zestawów narzędzi
  dla urządzeń. Kompilacje skrośne Windows wymagają sprawdzonego SDK
  SDL 2.32.10 MinGW i narzędzi komputera; Linux wymaga swojego SDK deweloperskiego SDL.
- Istniejące zapisy Windows dla X3/Q1 podają 285.172 s i 456.857 s na początkową
  kompilację rdzenia, bez przygotowania danych i późniejszego odświeżenia ABI.
  To historyczne obserwacje, a nie prognozy dla wszystkich celów lub obecnego
  obciążenia komputera. Przed zwiększeniem limitu czasu należy sprawdzić dziennik
  celu; dozwolony zakres wynosi 30-1800 sekund.
- Dziesięć pierwszych kompilacji trwało po 710.746-1067.643 s; końcowe przyrostowe
  make drugiej rundy trwały 88.877-139.583 s, bez kontroli wstępnej i danych. To obserwacje
  przy równoległym obciążeniu, nie gwarancja wydajności. Należy użyć sprawdzonego
  limitu 1800 s i analizować błędy.
- Każda nowa kompilacja tworzy katalog dowodów ze znacznikiem czasu; nie jest
  przyrostowym wykorzystaniem poprzedniego przebiegu. Należy wybierać potrzebne
  cele i nie zmieniać wspólnych źródeł w trakcie pracy. Sumy kontrolne przed
  i po kompilacji wykrywają część zmian wykonywanych równolegle.

Dla przygotowanego raportu Windows należy uruchomić test bezpośrednio w Windows.
W odpowiedzi na pytanie wpisz znacznik czasu raportu nowej kompilacji,
pozostającego w centralnym `Workspace`, a nie raportu archiwalnego. Jawny wybór
sterownika obrazu odróżnia ten przebieg od testu bez rzeczywistego obrazu
z użyciem sterownika pozornego:

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
$runId = Read-Host 'Znacznik czasu nowego raportu w centralnym Workspace'
python -B tools/tests/test_tts_targets.py --smoke-report "D:\work\Workspace\rockbox\tts-target-tests\$runId\report.json" --video-driver windows
```

Tryby raportowe używają celów zapisanych w raporcie, a nie filtrowania przez
`--targets`. Test przechwytuje dźwięk po uruchomieniu i kończy proces; nie jest
pełnym testem odbiorczym aplikacji. `--refresh-report` przyrostowo przebudowuje
zakończoną grupę i sprawdza ABI integracji w źródłach oraz zlinkowanym mechanizmie
ładowania. Dla źródeł nowego etapu oba muszą odpowiadać `0xe006`; historyczne
raporty zachowują własne ABI i nie walidują tej generacji. Przed użyciem przejrzyj
bieżący walidator i odświeżaj tylko świeży raport, nigdy zamknięte dowody.
Źródła muszą pozostać niezmienione przez cały czas
odświeżenia i następującego po nim natywnego testu uruchomienia. Odświeżenie
należy wykonać pod WSL, a następnie przeprowadzić nowy natywny test uruchomienia:

```sh
cd /mnt/d/Rockbox/rockbox
read -r -p 'Znacznik czasu nowego raportu w centralnym Workspace: ' run_id
python3 -B tools/tests/test_tts_targets.py \
  --refresh-report "/mnt/d/work/Workspace/rockbox/tts-target-tests/$run_id/report.json" \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 4 --timeout 1800
```

Kolejne odświeżenie zachowuje poprzedni raport bajt w bajt w
`<grupa>/refresh-history/<runda>/report.json`. Plik `manifest.json` mapuje dawne
ścieżki na zarchiwizowane dowody ze sprawdzonymi sumami. Historyczne raporty nie
są przepisywane tak, jakby opisywały nowy EXE. Stare EXE trafiają przez przeniesienie
do `snapshots`, a stare logi uruchomienia i poprzedniego refresh do historii.
Przed regeneracją archiwizowane jest także pięć przygotowanych plików katalogów
PL/EN oraz pierwotne logi ich generowania. Nowe logi kompilacji, symboli, PE,
mechanizmu ładowania i generowania katalogów trafiają do
`<cel>/refresh-rounds/<runda>/`. Historie oraz izolowane kopie danych silnika
pozostają przydatnymi materiałami regresyjnymi.

Cała grupa jest sprawdzana przed przenoszeniem artefaktów. Blokada raportu
wyklucza równoczesny refresh i smoke. Błędy aktywnej rundy, niedokończone rundy
i uruchomienia, zmienione sumy, działające EXE oraz niebezpieczne ścieżki są
odrzucane, a nie zerowane. Wyjątek dla początkowego błędu wyłącznie zmiany źródeł
zachowuje pierwotną porażkę. Błąd w trakcie rundy zatrzymuje dalszą pracę i wymaga
analizy; nie wolno usuwać blokad ani pól błędów/historii, aby wymusić ponowienie.
Udany refresh wymaga nowego smoke; smoke odrzuca źródła zmienione od kompilacji.
Fingerprint obejmuje czytnik, nagrywanie, warstwę integracyjną/silnik i trzy pliki
systemu/nagłówka/jądra SDL. Jest to ograniczona lista źródeł, nie pełny manifest
wszystkich zależności kompilacji.

### Kontrole katalogów i tempa

Każde odświeżenie regeneruje katalogi tekstu i mowy PL/EN oraz `english.list`,
używając cech przebudowanego celu. Harness sprawdza nagłówki celu, rozmiary
danych, liczbę wpisów i wszystkie 38 identyfikatorów TTS, w tym niepusty tekst
wyświetlany i mówiony `LANG_TTS_RECORDER_UNAVAILABLE`. Sumy i ścieżki istniejących
katalogów muszą przejść kontrolę wstępną. Niepełna lub nieudana regeneracja
pozostaje zachowana i blokuje automatyczne ponowienie. Sama obecność katalogów
nie jest testem działania nagrywania.

Konfiguracja testowa zapisuje kanoniczne WPM, nie procent ze znakiem:
`tts rate: 175` z `tts rate scale: percent` odpowiada 0%; istniejąca wartość 450
pozostaje tempem 450 WPM. Test uruchomienia sprawdza skonfigurowany parametr WPM
oraz zapisuje sumę konfiguracji i oczekiwany procent ze znakiem. To kontrola
spójności danych testowych, nie dowód poprawnego wyświetlania skali. Sam start
z neutralnym tempem nie dowodzi działania Sonic przy wysokim tempie ani
identyczności PCM z pominięciem Sonic.

Bieżący fingerprint 41 plików obejmuje funkcje obsługi tempa, `wavegen.cpp`,
pliki startowe SDL, makefile eSpeak oraz źródła/nagłówki i pliki pochodzenia Sonic.
Nowe kompilacje i odświeżenia wymagają siedmiu zlinkowanych symboli Sonic oprócz
ośmiu symboli mowy. Historyczne raporty zachowują własne listy źródeł i sumy;
nie potwierdzają objęcia późniejszych źródeł Sonic.

## Ograniczenia dystrybucji

Nagłówki silnika eSpeak określają GPL-3.0-or-later, a wiele nagłówków rdzenia
Rockboxa określa GPL-2.0-or-later. Nie ustala to jednak licencji każdego
zlinkowanego pliku. Pochodzące z dietlibc `firmware/libc/strtol.c` i `strtoul.c`
wskazują GPL w wersji 2 bez zgody na późniejszą wersję. Kompilacje natywne
wybierają te źródła. Istniejące mapy linkowania Windows wskazują zamiast nich
funkcje biblioteki CRT komputera, więc ten konkretny problem portów natywnych
nie dowodzi obecności tych plików w rdzeniu Windows.
Nie należy zmieniać zbiorczo licencji Rockboxa ani zakładać, że publikacja samych
źródeł automatycznie rozwiązuje niezgodne linkowanie. Przed dystrybucją
zintegrowanego programu nadal potrzebny jest pełny wykaz źródeł i licencji
każdego artefaktu. Należy zachować oryginalne informacje i teksty licencji
oraz wyjaśnić niepewne uprawnienia przed dystrybucją. Ten dokument nie przyznaje
nowych uprawnień licencyjnych ani nie zatwierdza wydania.
