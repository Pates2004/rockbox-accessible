# Eksperymentalny firmware eSpeak dla Sansa Clip Zip

## Wydanie: r29-alpha8-20261011

Pliki native w `D:\Rockbox\rockbox\installfiles\clipzip`:

- `rockbox-clipzip-espeak-r29-alpha8-20261011.zip`.
- `rockbox-clipzip-espeak-r29-alpha8-20261011-source.tar.gz` i `SHA256SUMS`.

Wydanie drugiej Sansy: Clip+ `r29-alpha7-20261011`. Odpowiadające wersje symulatorów
opisuje `ESPEAK-WINDOWS-PL.md`. Manifest paczki i odpowiadające źródła zawierają
identyfikację tego buildu; raporty poprzednich wydań go nie walidują.
Zapis zakładek zachowuje zastane pliki tymczasowe i próbuje wolnych nazw;
komunikat odróżnia zapis lokalny od błędu aktualizacji ostatnich zakładek.
Szczegóły i ograniczenia opisuje `ESPEAK-BOOKMARKS-PL.md`.
Nie deklarujemy prób sprzętowych. Stare identyfikatory, pomiary i wyniki poniżej
pozostają historyczne.
Rozmiary, hashe i inwentarze nowej paczki muszą pochodzić z jej własnej walidacji.

Skrócone ścieżki `Workspace/...`, `Forme/...`, `snapshots/...` i `trash/...`
odnoszą się odpowiednio do `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` i `D:\work\Trash\rockbox` (w WSL pod `/mnt/d/work`).
Aktualne `installfiles/...` znajduje się w `D:\Rockbox\rockbox\installfiles`.
Źródła pozostają w `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` w WSL), a
silnik i dane w `D:\Rockbox\espeak-1.44.05-source`.
Ścieżki takie jak `simdisk` i `.rockbox` pozostają względne wobec programu/urządzenia.

## Poprzednia aktualizacja przycisku i dostępności: r29-alpha5-20261009

Menu tekstu otwiera teraz przytrzymanie środkowego Select/Enter, jak w muzyce;
Góra służy do nawigacji. Poprawka wspólnego miksera dotyczy wyścigu przy
wznawianiu mowy po wygaszeniu ciszy. Rozszerzono mowę w narzędziowych wtyczkach;
zakres i ograniczenia opisuje ESPEAK-PLUGINS-PL.md. To wydanie eksperymentalne,
wymagające prób na sprzęcie; nie potwierdza naprawy chrupania na urządzeniu.
Wydanie drugiej Sansy: alpha4. Stare identyfikatory i wyniki poniżej
opisują poprzednie etapy; aktualne pliki wskazują manifest i SHA256SUMS.

## Poprzednia aktualizacja zakładek: r29-alpha4-20261009

Tamto wydanie dodało trwałe zakładki i mówiące menu tekstu pod długim Play.
Instrukcja: `ESPEAK-BOOKMARKS-PL.md`. Odpowiadająca paczka Clip+ to alpha3.
Numery, rozmiary i wyniki alpha3 w dalszych sekcjach opisują poprzedni etap;
aktualne pliki i sumy sprawdź w dołączonym manifeście i `SHA256SUMS`.
Nowy firmware nadal wymaga próby na sprzęcie; trzaski przy szybkich zmianach
ustawień i testy fizycznego rejestratora pozostają otwarte.

## Poprzedni etap: rejestrator

Firmware **wyłącznie dla Sansa Clip Zip**, nie Clip, Clip v2, Clip+, symulator
Windows ani bootloader. Dostarczony fork eSpeak 1.44.05 r29 działa wewnątrz
Rockboksa; nie używa eSpeak NG, zewnętrznej usługi mowy ani nagranych plików
`.voice`/`.talk`. Identyfikator tego wydania to
**`r29-alpha3-20261009`**, w parze z Clip+ **`r29-alpha2-20261009`**.
Dokładną walidację archiwów oprzyj na `manifest.json` i `SHA256SUMS` wydania.
Manifest opisuje kontrole archiwów, nie fizyczną walidację rejestratora;
próby rejestratora na sprzęcie pozostają do wykonania.

**Wersja eksperymentalna, bez certyfikacji stabilności; testy sprzętowe alpha3
są nadal do wykonania.** Dla historycznego etapu alpha2 użytkownik fizycznie
uruchomił odtwarzacz i potwierdził mowę oraz odczyt TXT razem z muzyką.
Rejestrator otwierał się bez mowy; sporadyczne trzaski przy szybkich zmianach
ustawień pozostają nierozwiązane. To raport użytkownika, nie test wykonany
przez asystenta ani pełna walidacja sprzętowa. Zastępuje stary status alpha2
„start nieprzetestowany ponownie”, ale nie waliduje alpha3, natywnej mowy
rejestratora/przechwytywania, USB, baterii ani dostępności z czytnikiem ekranu.
Kontrola archiwów nie dowodzi ich działania. Zachowaj sprawdzoną instalację
i procedurę odzyskiwania. Kompilacja native używa ARM GCC 13 zamiast zalecanego
przez Rockboksa GCC 9.5.0; ostrzeżenie configure oznacza rzeczywiste ograniczenie
zgodności, nie potwierdzenie działania na sprzęcie.

## Historyczna panika alpha1 i nadal obowiązujący limit obrazu

Przyczynę paniki alpha1 potwierdzono analizą oficjalnego pliku binarnego
bootloadera z 2019 r., `9de8993af6-190809`: zgłoszony adres PC `0x3080f01c`
odpowiada dokładnie temu loaderowi. Jego BSS zaczyna się pod `0x30100000`,
co pozostawia **1 MiB** na surowy obraz ładowany od `0x30000000`. Stos loadera
`ata/sd` zajmuje `0x301114d0..0x30111ed0`. Surowy obraz alpha1 o rozmiarze
**1 243 156 bajtów** przekroczył tę granicę i nadpisał BSS oraz stos loadera,
wywołując panikę przed startem nowego firmware. Założenie o buforze 2 MiB
nie dotyczy tego bootloadera; zmiana stosu aplikacji nie usuwa tej przyczyny.

Obowiązujący pułap zgodności dla **Clip Zip alpha3 i Clip+ alpha2** to
**surowy obraz ≤ 1 MiB (1 048 576 bajtów)**.
Kompilacja/pakowanie i weryfikacja archiwum muszą odrzucać większy obraz.
Limit dotyczy `rockbox.bin` i zawartości `rockbox.sansa` bez 8-bajtowego nagłówka,
nie rozmiaru skompresowanego ZIP-a ani całkowitej pamięci RAM. Po kompilacji
odczytaj dokładny rozmiar nowego obrazu z pola `firmware.payload_bytes` pliku
`.rockbox/espeak-clipzip/manifest.json`. Rozmiar alpha1 powyżej to historyczna
diagnoza, nie pomiar alpha3; nowe rozmiary i liczby modułów wymagają nowego
manifestu/walidacji.

Oba modele w tej parze używają kompilacji ARM/Thumb i optymalizacji rozmiaru
eSpeak `-Os`; symulator zachowuje `-O2`. Skrypt ustawia `--thumb` dla obu
modeli i przebudowuje wszystkie dołączone moduły dla ABI `0xe003`.
Flashowanie ani wymiana bootloadera nie są wymagane. Analiza binarna ustaliła
przyczynę awarii alpha1; późniejszy raport użytkownika potwierdził start alpha2
na jego odtwarzaczu. Żadne z nich nie jest sprzętowym testem rejestratora alpha3.

Ten sam limit obrazu 1 MiB obowiązuje parę Clip Zip alpha8 / Clip+ alpha7.
Jej rzeczywiste rozmiary i wyniki trzeba ustalić po nowej kompilacji.

## Najpierw rozpoznaj właściwy model

Sprawdzone definicje źródłowe celowo używają dwóch różnych identyfikatorów:

| Właściwość | Wartość Clip Zip i źródło |
| --- | --- |
| Cel configure | `sansaclipzip`, `tools/configure` |
| ID konfiguracji/katalogów | `target_id=68`; katalogi językowe i `rockbox-info.txt` |
| Numer modelu firmware | `MODEL_NUMBER=79`, `firmware/export/config/sansaclipzip.h` |
| Kontener firmware | `rockbox.sansa`, znacznik `clzp`, suma kontrolna z wartością początkową 79 (`tools/scramble.c`) |
| ID wtyczek/kodeków | `TARGET_ID=68`, z konfiguracji; nagłówki i loader w `apps/plugin.h`, `apps/plugin.c`, `lib/rbcodec/codecs/codecs.h` |
| Skonfigurowana pamięć RAM | `memory=8` w `tools/configure`: 8 MiB, nie 8 MiB wolne dla mowy |
| Procesor native | AS3525v2 / ARM926EJ-S |
| Przyciski | `SANSA_CLIP_PAD`; nagłówek przycisków Clip Zip i `apps/keymaps/keymap-clip.c` |

Nie zmieniaj 68 na 79 w katalogach ani nagłówkach modułów. Sumę firmware
oblicza się z początkowym 79. To rozróżnienie upstream, nie literówka pakowania.
Wartość RAM pochodzi z konfiguracji kompilacji, nie z pomiaru sprzętu ani testu,
że mowa i odtwarzanie mieszczą się w każdym scenariuszu. Kod rdzenia, stosy,
mowa i bufory dźwięku dzielą tę pamięć. Clip+ używa `cli+`/66: **jego firmware
ani moduły nie są zamienne z Clip Zip**, mimo identycznej nazwy `rockbox.sansa`
i wspólnej mapy przycisków.

## Historyczne pliki etapu rejestratora

Historyczne nazwy plików etapu rejestratora; poprzednie wydania są
archiwizowane w centralnym `snapshots`, a planowana paczka ma nazwy podane
na początku tej instrukcji:

- `rockbox-clipzip-espeak-r29-alpha3-20261009.zip`
- `rockbox-clipzip-espeak-r29-alpha3-20261009-source.tar.gz`
- `SHA256SUMS`

Używaj ZIP-a firmware tylko wraz z odpowiadającymi mu źródłami i sumami kontrolnymi.
Archiwum źródeł służy odtworzeniu kompilacji i spełnieniu obowiązków licencyjnych,
nie instalacji na odtwarzaczu. Oczekiwany katalog dokumentacji w ZIP-ie to
`.rockbox/espeak-clipzip/`: `CZYTAJ.md` (polski), `README.md` (angielski),
`manifest.json`, licencje, lista autorów i informacje o pochodzeniu. To kopie
tej instrukcji i `docs/ESPEAK-CLIPZIP.md` dołączane do paczki, nie kolejne wydania
firmware. Pliki symulatora Windows mają osobny katalog
`installfiles/simwindows-clipzip/`.

## Instalacja bez flashowania

**Próba alpha8, po walidacji paczki:** najpierw wykonaj i sprawdź kopię
obecnego `.rockbox` oraz danych użytkownika. Zastąp **całą zawartość `.rockbox`**
zawartością zweryfikowanego ZIP-a alpha8, bez scalania ze starą instalacją
i z czystą konfiguracją. Zachowaj
muzykę, książki, nagrania i inne pliki użytkownika; dane ze starego `.rockbox`
pozostaw w kopii odzyskiwania. **Nie flashuj ani nie zmieniaj bootloadera.**
Następnie wykonaj etapowe próby poniżej; ich wynik sprzętowy pozostaje nieznany.

1. Potwierdź, że fizyczny odtwarzacz to **Sansa Clip Zip** i już uruchamia się
   przez zainstalowany, działający **bootloader Rockboksa dla Clip Zip**.
   Paczka nie instaluje ani nie zmienia bootloadera. Jeśli ten warunek nie jest
   spełniony, przerwij i osobno przeczytaj oficjalną instrukcję instalacji
   Rockboksa dla Clip Zip. Nie flashuj `rockbox.sansa` ani nie używaj plików
   bootloadera/kombinacji przycisków z Clip+ lub innego modelu. Ta instrukcja
   nie zawiera procedury instalacji bootloadera.
2. Naładuj odtwarzacz, przeczytaj instrukcję na komputerze i ustal sprawdzoną
   drogę odzyskiwania przed próbami. Zacznij od niskiej głośności, początkowo
   wyjmując słuchawki z uszu. Podłącz USB w znanym działającym trybie dostępu
   do plików; rozpoznaj **pamięć wewnętrzną**, nie kartę microSD.
3. W osobnym bezpiecznym miejscu wykonaj kopię wszystkich plików urządzenia,
   całego obecnego `.rockbox`, ustawień, nagrań i plików firmware/odzyskiwania.
   W razie potrzeby pokaż ukryte pliki i sprawdź kompletność oraz odczyt kopii.
   To celowa kopia do odzyskiwania: zachowaj ją po próbach. **Zachowaj również
   istniejące kopie na urządzeniu**; nie kasuj, nie nadpisuj ani nie formatuj
   ich dla uzyskania czystych ustawień. Pozostaw muzykę, książki i nagrania.
   Gdy brakuje miejsca, przerwij i rozwiąż ten problem bez usuwania danych
   użytkownika, których roli i kopii nie sprawdzono.
4. Przed wypakowaniem sprawdź oba archiwa według `SHA256SUMS`. W Linux/WSL
   uruchom `sha256sum -c SHA256SUMS` w katalogu wydania; w Windows porównaj
   wynik `Get-FileHash -Algorithm SHA256` każdego archiwum z odpowiednim
   wpisem. Hashe wykrywają uszkodzenia, nie potwierdzają tożsamości wydawcy
   ani autentyczności.
5. Dopiero po wykonaniu kopii przenieś aktywny stary `.rockbox` poza katalog
   główny odtwarzacza do osobnego, opisanego miejsca odzyskiwania, nie nadpisując
   istniejących kopii. **Nie scalaj instalacji.** Zintegrowany eSpeak używa ABI
   wtyczek `0xe003`; standardowe i symulatorowe wtyczki/nakładki są niezgodne.
   Wszystkie dołączone wtyczki, nakładki i kodeki muszą być przebudowane dla tego
   firmware Clip Zip. Nie kopiuj modułów Clip+, nawet z innego wydania eSpeak.
6. Wypakuj cały `.rockbox` z ZIP-a do **katalogu głównego pamięci wewnętrznej**.
   Wymagane ścieżki obejmują `/.rockbox/rockbox.sansa`,
   `/.rockbox/espeak-data/phondata`, `/.rockbox/langs/polski.vstrings` i
   `/.rockbox/espeak-clipzip/manifest.json`. Nie twórz `.rockbox/.rockbox`, nie
   instaluj tej paczki na microSD ani nie kopiuj symulatora Windows na odtwarzacz.
   Bezpiecznie wysuń urządzenie i uruchom przez dotychczasowy działający bootloader.
7. Zacznij od czystych polskich ustawień paczki: mowa menu, naturalny odczyt nazw
   plików/katalogów, eSpeak włączony, język mowy zgodny z systemowym, 175 słów/min
   (0% przy skali procentowej), ściszanie muzyki do 25%, głośność odtwarzania
   -25 dB. Poprzednie ustawienia, stan wznowienia i pliki użytkownika nie są
   importowane. Nie przywracaj starego `config.cfg`, `.voice`, `.talk`, `.rock`,
   `.ovl` ani `.codec` do tej instalacji testowej. Zachowaj je w kopii odzyskiwania.
   Wymagane są katalogi wyświetlania i mowy PL/EN; angielski wybierz w ustawieniu
   języka Rockboksa przy testowaniu tej wersji. Interfejs obsługują przyciski.
8. Jeśli mowa zawodzi, odtwarzacz się zawiesza lub dźwięk przerywa, zakończ próby
   i przywróć poprzednią instalację. Nie polegaj na eksperymencie jako jedynym
   dostępnym odtwarzaczu. Odczyt tej instrukcji przez NVDA na komputerze nie
   dowodzi sprawdzonej dostępności odtwarzacza.

## Powrót do poprzedniej wersji bez flashowania

Połącz USB przez znaną działającą procedurę odzyskiwania. Jeśli ten firmware
nie udostępnia pamięci, użyj udokumentowanej drogi dla posiadanego firmware
i bootloadera Clip Zip; paczka jej nie dostarcza, a ta instrukcja nie zaleca
żadnej niesprawdzonej kombinacji przycisków przy włączaniu.

Przenieś eksperymentalny `.rockbox` poza urządzenie, zachowując potrzebne nowe
pliki. Przywróć **całą zweryfikowaną poprzednią kopię `.rockbox`** do katalogu
głównego pamięci wewnętrznej, bezpiecznie wysuń i uruchom ponownie. Nie mieszaj
modułów, nie flashuj obrazu, nie wymieniaj bootloadera ani nie usuwaj kopii
z urządzenia. Skrypt na komputerze nie korzysta z odtwarzacza ani nie porządkuje
jego danych; zasady archiwizacji na komputerze nie są poleceniem sprzątania
urządzenia.

## Przyciski odtwarzacza i czytnik tekstu

To mapowanie odczytane ze źródeł, nie raport z testów przycisków na sprzęcie.
`firmware/target/arm/as3525/sansa-clipzip/button-target.h` definiuje przyciski;
`apps/keymaps/keymap-clip.c` określa działania zależne od kontekstu:

- Na zwykłych listach Góra/Dół zmienia pozycję, puszczenie Select lub Prawo
  zatwierdza, Lewo lub krótkie Power anuluje; puszczenie Home otwiera menu.
- Na ekranie odtwarzania puszczenie Góra/Play przełącza odtwarzanie/pauzę,
  Lewo/Prawo zmienia utwór (przytrzymanie przewija), Vol+/Vol- zmienia głośność,
  a krótkie Power zatrzymuje odtwarzanie.
- Przy dostępnym eSpeak otwarcie pliku UTF-8 `.txt` w przeglądarce uruchamia
  zintegrowany czytnik, nie osobną wtyczkę książek. Oryginalna przeglądarka tekstu
  pozostaje dostępna przez Otwórz za pomocą.
- W czytniku puszczenie Select lub Home wstrzymuje/wznawia czytanie;
  Lewo/Prawo przechodzi wstecz/dalej o wybraną jednostkę. Góra/Dół lub Vol+/Vol-
  zmienia jednostkę: znak, słowo, wiersz logiczny, akapit lub strona.
  **Przyciski głośności wybierają tu jednostkę, nie głośność.** Krótkie Power
  zamyka czytnik; Lewo przemieszcza po tekście zamiast wychodzić.
  Nie przytrzymuj Power w celu zamknięcia czytnika.

Czytnik implementuje kursor powiązany z odtwarzaniem i buforowaną pauzę/wznowienie;
sprawdź rzeczywiste działanie w etapowej próbie poniżej. Nawigacja/zmiana jednostki
wstrzymuje ciągłe czytanie i wypowiada wybór; Select wznawia od tej pozycji.
Strony liczą wiersze logiczne (domyślnie 20, zakres 1-100), nie zawinięcia ekranu.
Znaki oznaczają punkty kodowe Unicode, nie klastry grafemów. Trwałe zakładki
dokumentu i odczyt PDF/EPUB/DOCX nie są zaimplementowane. Nieprawidłowy UTF-8
powinien wywołać komunikat błędu zamiast być traktowany jako obsługiwany dokument.

## Etapowa ponowna próba na urządzeniu

To proponowana lista kontrolna, **nie ukończona walidacja sprzętowa**. Używaj
niskiej głośności i krótkich, nieistotnych plików testowych; zachowaj powstałe
nagrania do sprawdzenia. Zakończ każdy etap przed następnym. Jeśli mowa zawodzi,
odtwarzacz się zawiesza lub dźwięk przerywa, zakończ próby i użyj procedury
odzyskiwania, zamiast przechodzić do nagrywania.

1. **Start i mowa:** uruchom urządzenie, przejdź przez menu i krótką listę plików
   oraz katalogów. Sprawdź fokus/wybór, wypowiadane etykiety, nazwy i literowanie
   tam, gdzie je wybrano, komunikaty błędów oraz opóźnienie pierwszej wypowiedzi.
   Osobno sprawdź interfejs i mowę po polsku oraz po angielsku; sama zmiana
   ustawienia nie dowodzi słyszalnego skutku. Zapisz brakujące/błędne komunikaty.
2. **Odtwarzanie z mową:** odtwórz krótki sprawdzony MP3. Sprawdź pauzę/wznowienie,
   głośność i zmianę utworów, następnie wywołaj mowę menu podczas odtwarzania.
   Muzyka powinna być ściszana w czasie mowy i wracać do poprzedniego poziomu,
   bez przerw, zacinania ani utrzymującego się ściszenia. Zapisz opóźnienia
   rozpoczęcia mowy i powrotu głośności.
3. **Czytnik:** otwórz krótki `.txt` UTF-8 z polskimi/angielskimi słowami i pustymi
   wierszami. Sprawdź wszystkie pięć jednostek nawigacji w obu kierunkach,
   pauzę/wznowienie i wyjście. Słuchaj, czy tekst nie jest pomijany/powtarzany,
   i porównaj wypowiadaną pozycję z czytaniem po wznowieniu. Sprawdź pusty plik
   oraz plik testowy z błędnym UTF-8; po błędach nawigacja i wyjście muszą nadal
   reagować. Ważną lekturę zostaw na późniejsze, sprawdzone wydanie; trwałe
   zakładki nie są dostępne.
4. **Nagrywanie, dopiero po udanych wcześniejszych etapach:** wykonaj poniższą
   ręczną próbę rejestratora. Natywny nagłówek deklaruje nagrywanie mikrofonu/FM;
   **nie** dowodzi to działającego przechwytywania ani jednoczesnej mowy
   rejestratora. Przerwij po komunikacie o niedostępnym nagrywaniu lub innym
   błędzie. Nagrywanie FM wymaga osobnego późniejszego testu fizycznego.

Dla każdego etapu zapisz dokładną wersję firmware, język/ustawienia, działanie
i plik, wynik, opóźnienie startu/mowy, czas pauzy/wznowienia oraz błędy dźwięku.
Odzyskiwanie przez USB, bateria, długie sesje i największe obciążenie RAM/CPU
pozostają osobnymi kontrolami sprzętowymi; cztery krótkie etapy nie stanowią
certyfikacji stabilności ani dostępności.

### Mowa rejestratora: źródła a stan prób sprzętowych

Historyczna cisza alpha2 była potwierdzonym ograniczeniem integracji: TTS
rejestratora działał wyłącznie w symulatorze, a mikser blokował wyjście podczas
nagrywania. Źródła rejestratora zawierają teraz mowę zależną od możliwości
natywnego PCM: pierwszy wiersz, nawigację, poziomy, nazwę pliku, czas/rozmiar
i zmiany stanu, a także zatrzymanie mowy i DMA odtwarzania przed inicjalizacją,
zamknięciem i zmianą opcji/zegarów nagrywania. PCM mowy śledzi bieżącą
częstotliwość miksera i aktualizuje DSP, unikając starej częstotliwości
końcówki po Stop, która mogła przyspieszyć pierwsze słowa rejestratora.
Backend AS3525v2 przełącza wyjście DMA
z pętli odsłuchu wejścia na czas mowy. Nagrywanie pozostaje aktywne; mowa
czasowo zastępuje bieżący odsłuch w słuchawkach. Odsłuch wraca po końcówce
mowy i około trzech pustych ramkach miksera (kilka milisekund, bez pomiaru
sprzętowego). Przechwytywanie nie jest pauzowane dla mowy. Cyfrowe domieszanie
TTS do nagrania mikrofonu nie jest zamierzone, ale nadal wymaga kontroli WAV.

Backend tej pary używa wąskiej możliwości **`HAVE_PCM_RECORDING_VOICE`**,
ograniczonej do natywnych celów AS3525v2 z nagrywaniem, takich jak Clip+ i Clip Zip.
Nie włącza ogólnej obsługi jednoczesnego odtwarzania muzyki i przechwytywania.
Ścieżka źródłowa i testy hosta nie potwierdzają działania rejestratora na sprzęcie.
Zakres regresji hosta obejmuje bramki możliwości, mowę wierszy/stanów,
kolejność przejść i przypadki wykonania C dla częstotliwości od 16 do 96 kHz,
z kontrolami AddressSanitizer i UndefinedBehaviorSanitizer. Testy hosta nie
walidują sprzętowego taktowania DMA ani nagrywania mikrofonu; rzeczywiste wyniki
kontroli artefaktów sprawdź w manifeście i dowodach walidacji wydania.
Mowa rejestratora, powrót odsłuchu i zapis wejścia na
**Clip Zip alpha3** i **Clip+ alpha2** nadal wymagają prób fizycznych.
Nagrywanie w SDL pozostaje niedostępne. Trzaski przy szybkich zmianach ustawień
nie mają potwierdzonej przyczyny ani naprawy; nie ustalono wyczerpania RAM
ani usterki ciągłego odtwarzania. Trwałe zakładki i pełna wtyczka czytnika
książek pozostają na później.

### Ręczny test rejestratora na odtwarzaczu

Klawisze pochodzą z `apps/keymaps/keymap-clip.c` (`CONTEXT_RECSCREEN`
i dziedziczonego kontekstu standardowego), nie z testu sprzętu. Góra/Play
i Dół/Menu wybierają wiersze; Prawo lub Vol+ zwiększa wybrany poziom,
Lewo lub Vol- zmniejsza. **Lewo nie oznacza tu Wstecz; przyciski głośności
regulują wybrany poziom.** Select rozpoczyna ze stanu zatrzymania, potem
pauzuje/wznawia. Zwolnienie Home rozpoczyna nowy plik podczas nagrywania.
Krótkie Power zatrzymuje nagranie; krótkie Power po zatrzymaniu wychodzi.
Przytrzymanie Dół/Menu otwiera ustawienia **tylko po zatrzymaniu**.
Nie przytrzymuj Power.

1. Użyj słuchawek, niskiej głośności i krótkiej, nieistotnej próbki.
   W ustawieniach nagrywania wybierz mikrofon, WAV, wyłącz wyzwalacz i ustaw
   czas nagrywania wstępnego na zero. Wejdź do rejestratora; sprawdź mowę
   pierwszego wiersza Głośność bez naciskania klawisza. Przejdź góra/dół przez
   wzmocnienie, nazwę pliku, czas i rozmiar; sprawdź etykiety/wartości.
   Dodatkowe wiersze AGC/kanałów zależą od ustawień.
2. Na Głośności i wzmocnieniu mikrofonu zmień jeden mały krok i cofnij go
   przez Prawo/Lewo lub Vol+/Vol-. Potwierdź wypowiadaną wartość i słyszalny
   skutek zmiany poziomu bez przesterowania; te regulacje mają różne cele.
3. Naciśnij Select, aby rozpocząć. Sprawdź komunikat nagrywania i nazwę pliku;
   wypowiadaj rozpoznawalną próbkę wejściową, wybierając czas/rozmiar
   i wywołując TTS. Sprawdź przyrost czasu/rozmiaru, aktywne przechwytywanie
   podczas TTS i powrót odsłuchu po każdej wypowiedzi; zapisz opóźniony
   lub brakujący powrót.
4. Select pauzuje, kolejny Select wznawia. Sprawdź oba komunikaty, zachowanie
   czasu/rozmiaru i wznowione wejście; zapisz opóźnienia, przerwy i brakującą mowę.
5. Podczas nagrywania naciśnij i zwolnij Home; sprawdź nową nazwę. Zatrzymaj
   krótkim Power; sprawdź komunikat i zakończenie zapisu obu plików WAV.
6. Po zatrzymaniu przytrzymaj Dół/Menu, aby otworzyć ustawienia; wróć krótkim
   Power. Ponownie sprawdź mowę/pierwszy wiersz i poprawność poziomów.
7. Wyjdź krótkim Power po zatrzymaniu. Odtwórz każdy testowy WAV i zachowaj go
   do oceny: powinien zawierać wejście mikrofonu bez cyfrowo domieszanego TTS
   ani niewyjaśnionych przerw wejścia. Odsuń słuchawki od mikrofonu; odbiór
   akustyczny nadal jest możliwy i nie obiecujemy odporności na sprzężenie.
8. Odtwórz ponownie sprawdzony MP3, wywołaj mowę menu i odczyt TXT.
   Sprawdź odtwarzanie, głośność, powrót po ściszeniu muzyki i przywrócenie
   toru wyjścia/odsłuchu. Zapisz dokładną wersję, język, czynności i błędy;
   wykonaj próbę po polsku i angielsku.

## Kompilacja i weryfikacja wydania

Poniższe polecenia używają `tools/build_espeak_clipplus.py`
z wyborem modelu. **Zawsze podawaj `--target=sansaclipzip`: domyślny pozostaje
Clip+.** Używaj ustalonego drzewa źródeł; nie zmieniaj źródeł, skryptów,
testów ani instrukcji w trakcie kompilacji i pakowania.

Wymagania: Linux/WSL, Python 3.9+, Git, GNU make, Bash, Perl, zip/unzip,
narzędzia C hosta oraz `arm-none-eabi-gcc`/`arm-none-eabi-g++` **13.x**
z odpowiadającymi binutils w PATH. To eksperymentalna ścieżka GCC 13, nie
walidacja z zalecanym przez upstream GCC 9.5.0. Dotychczasowe środowisko
pakowania to Ubuntu 24.04 z `gcc-arm-none-eabi`, `libnewlib-dev`,
`libnewlib-arm-none-eabi`, `gcc-13-base` i `base-files`. Zachowaj dostępność
wersji narzędzi/pakietów wskazanych w manifeście do odtworzenia kompilacji.

Skrypt wymaga `/usr/share/doc/libnewlib-dev/copyright`,
`/usr/share/doc/gcc-arm-none-eabi/copyright`,
`/usr/share/doc/gcc-13-base/copyright`, `/usr/share/common-licenses/LGPL-2.1`
oraz projektowego `docs/NEWLIB-ARM-NOTICES.txt`. Brak notices musi zatrzymać
pakowanie; dowolny plik copyright z innej dystrybucji nie jest zamiennikiem.
Dostarczone źródła silnika są w `D:/Rockbox/espeak-1.44.05-source`
(`/mnt/d/Rockbox/espeak-1.44.05-source` w WSL), z dokładnym podkatalogiem
`espeak-data` i rewizją `2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f`.

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipzip \
  --source-frozen --version r29-alpha8-20261011 \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source --jobs 4
```

Ścieżka Clip Zip używa `--target=sansaclipzip --type=n --integrated-espeak
--thumb --compiler-prefix=arm-none-eabi-`, automatycznego wrappera C++, świeżego katalogu
`Workspace/build-espeak-clipzip` i `make zip`. Skrypt ustawia `--thumb` w configure;
kompilacja ARM/Thumb musi zachować poprawne przejścia między kodem ARM i Thumb
oraz wymusić limit surowego obrazu 1 MiB. Musi przebudować wszystkie moduły,
użyć katalogu dokumentacji/manifestu Clip Zip i przekazać wyłącznie kompletne
wydanie native do `installfiles/clipzip`. Zmiany źródeł w trakcie pakowania muszą
przerwać publikację. Katalogi wynikowe Clip+ i symulatora Windows są oddzielne.

Poprzednie buildy/wydania Clip Zip przed zastąpieniem trafiają do unikalnych
katalogów centralnego `snapshots`, nigdy nie są nadpisywane. Najpierw muszą
powieść się kontrole ścieżek, zawartości/hashy oraz procesów/otwartych plików.
Używany artefakt lub niedostępna wymagana kontrola wstrzymuje zastąpienie.
W WSL kontrole obejmują widoczne procesy Windows i wyłączne otwarcia plików,
lecz nie wykluczają użycia przez innych użytkowników komputera. Chroni to poprzednie
wydania na komputerze, nie tworzy kopii do scalenia z czystą instalacją.

Logi, zamrożone hashe, dowody ELF/symboli i `validation.json` należą do
centralnego katalogu kompilacji. Surowe archiwum `make zip` oraz
`elf-payload-validation.bin` są celowymi wejściami/wynikami diagnostycznymi,
nie dodatkowymi finalnymi wydaniami. Niedokończony katalog pakowania nie jest
wydaniem. Po pakowaniu sprawdź rzeczywiste archiwa bez ich modyfikacji:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipzip --verify \
  /mnt/d/Rockbox/rockbox/installfiles/clipzip/rockbox-clipzip-espeak-r29-alpha8-20261011.zip
```

Windows PowerShell (kontrola tylko do odczytu):

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
python -B tools/build_espeak_clipplus.py --target=sansaclipzip --verify 'D:\Rockbox\rockbox\installfiles\clipzip\rockbox-clipzip-espeak-r29-alpha8-20261011.zip'
```

Obok ZIP-a zachowaj odpowiadające źródła i `SHA256SUMS`.
Powodzenie tej kontroli to walidacja struktury, nie test na sprzęcie ARM
ani w Windows SDL.

### Odtworzenie kompilacji źródeł bez metadanych Git

Wypakuj sąsiednie katalogi `rockbox` i `espeak-1.44.05-source` z archiwum do
`/mnt/d/work/Workspace/rockbox/source-rebuild-clipzip-r29-alpha8-20261011`.
Oryginalne źródła silnika w `D:\Rockbox\espeak-1.44.05-source` pozostają na miejscu.
Użyj wersji z `source-manifest.json`; przykład dotyczy planowanego wydania.
Katalog kompilacji musi być nowy; poprzedni build przed zastąpieniem zachowaj
w centralnym `snapshots`.

```sh
set -eu
cd /mnt/d/work/Workspace/rockbox/source-rebuild-clipzip-r29-alpha8-20261011/rockbox
source_dir="$PWD"
export VERSION=r29-alpha8-20261011
build_dir=/mnt/d/work/Workspace/rockbox/build-espeak-clipzip-source-r29-alpha8-20261011
mkdir "$build_dir"
cd "$build_dir"
bash "$source_dir/tools/configure" --target=sansaclipzip --type=n \
  --integrated-espeak --thumb --compiler-prefix=arm-none-eabi-
make -j4 zip
```

Nie nadpisuj `CXX` przy kompilacji native: ominęłoby to wrapper Thumb i mogłoby
ponownie przekroczyć bezpieczny limit obrazu bootloadera.

Ten surowy `rockbox.zip` **nie jest kompletną instalacją eSpeak**: nadal wymaga
dokładnych sąsiednich danych `espeak-data`, wygenerowanych `.vstrings`, czystych
ustawień, notices i walidacji. Do pełnego wydania użyj drzewa roboczego Git
i skryptu pakującego z wyborem modelu; nigdy nie instaluj surowego ZIP-a z ręcznej
kompilacji tak, jakby zawierał wszystkie zasoby wykonawcze.

## Zawartość paczki i wymagana walidacja

Kompletna paczka musi łączyć natywny wynik `make zip`, dokładne dostarczone
`espeak-data`, świeżo wygenerowane `apps/lang/*.vstrings`, czyste ustawienia
i dokumentację/notices/manifest w `.rockbox/espeak-clipzip/`. Katalogi mowy są
tekstem do bieżącej syntezy, nie nagraniami dźwięku. Podczas pakowania usuń
z bazowego archiwum standardowe `.voice`/`.talk`, w tym
`langs/InvalidVoice_english.talk`; manifest zapisuje pominięcia, a końcowy
walidator musi odrzucać każde takie nagranie, nawet wymienione w manifeście.
Zachowane zasoby MBROLA z upstream nie oznaczają obsługi MBROLA.

Odbiór wydania musi obejmować sprawdzenie rzeczywistych plików, nie tylko udane
zakończenie kompilatora lub tę instrukcję:

- Architekturę natywnego ELF ARM i zdefiniowane symbole `rb_espeak_synth_tracked`,
  `rb_espeak_synth_character`, `espeak_Synth`, `tts_speak`, `reclist_speak`
  i `audio_set_pcm_output`; dwa ostatnie pozwalają odrzucić build bez TTS
  rejestratora lub backendu kierowania wyjścia PCM. Same symbole silnika nie
  wystarczą. Porównanie zawartości
  obrazu `.sansa` z `rockbox.bin` oraz niezależną rekonstrukcją ELF.
  Przy `--gc-sections` usunięcie nieużywanego wrappera `rb_espeak_synth` jest
  prawidłowe; nie jest on punktem wejścia wymaganym przez rdzeń.
- Surowy obraz nie większy niż **1 048 576 bajtów**, niezależnie od kompresji
  ZIP-a; większy obraz musi zostać odrzucony przez skrypt budujący i walidator.
  Zapisz zmierzony rozmiar i tryb ARM/Thumb w dowodach walidacji. Mniejszy obraz
  usuwa potwierdzone nakładanie na pamięć loadera, ale nie dowodzi udanego startu.
- Znacznik firmware `clzp` i sumę z wartością początkową 79, ale ID wtyczek,
  kodeków, konfiguracji, katalogów i `rockbox-info.txt` **68**.
  Sprawdź katalogi PL/EN, zgodną wersję i model docelowy. Nie ujednolicaj tych ID.
- ABI wtyczek `0xe003` i API kodeków 50. Dekoder obrazów `.ovl` używa API IMGDEC 1
  z osobnym wbudowanym polem ABI wtyczek, które musi wynosić `0xe003`; zwykłe
  nakładki mają standardowy nagłówek wtyczki. Bez modułów stock ani symulatora.
- Wymagane dane/notices, czyste ustawienia, ścieżki archiwum, inwentarz plików
  i hashe każdego wpisu. `manifest.json` zapisuje wersję, narzędzia kompilacji,
  inwentarz źródeł, hashe ELF/obrazu/mapy linkowania i pochodzenie bibliotek.
  `SHA256SUMS` obejmuje oba archiwa, a więc także sam manifest firmware.
- Odpowiadające archiwum źródeł, jego inwentarz i powiązanie z dokładnie tym
  firmware; niezwiązany commit upstream nie identyfikuje lokalnych zmian.

To kontrole **struktury, nie wykonania programu na odtwarzaczu**. Po kompilacji
osobno zapisz rzeczywiste wyniki; nie oznaczaj proponowanych prób jako zaliczonych.

## Odpowiadające źródła i licencje

Przekazuj razem ZIP, odpowiadający `*-source.tar.gz` i `SHA256SUMS`. Archiwum
źródeł musi zawierać rzeczywiste pliki drzewa roboczego Rockboksa (śledzone
i nieignorowane nieśledzone pliki integracji), dostarczone źródła/dane eSpeak,
skrypty kompilacji i `source-manifest.json`. Pomija `.git`, dane uwierzytelniania,
audyty wewnętrzne, narzędzia kompilatora, wyniki kompilacji, instalacje i snapshoty.
Kopie danych wykonawczych i odpowiadających źródeł mają różne cele: uruchomienie
i odtworzenie kompilacji. Zachowaj jeden finalny ZIP native, nie dodatkowe
rozpakowane wydanie na komputerze.

Zachowaj wykaz licencji/GPLv2 Rockboksa, dostarczony tekst GPLv3 eSpeak,
licencję Apache-2.0 Sonic, listę autorów, pochodzenie i oryginalne notices
poszczególnych plików. Poniższe obowiązki i ustalenia ograniczonego przeglądu
pochodzą z dotychczasowej dokumentacji native Clip+; **nie są nowym pełnym
przeglądem prawnym Clip Zip**:

- Nowe `firmware/libc/strtol.c`, `firmware/libc/strtoul.c` i
  `tools/tests/test_libc_strto.c` napisano niezależnie według semantyki konwersji,
  nie kopiując innej libc ani nie zmieniając jedynie etykiety dietlibc.
  Sprawdzono poprzednie API/zachowanie; nie jest to certyfikowana procedura
  clean-room. Te nowe implementacje/test są GPL-2.0-or-later, co pozwala wybrać
  GPLv3 dla połączenia bez zmiany licencji zastąpionego kodu lub prac innych
  autorów. Nowy skrypt pakujący, jego testy i te instrukcje są GPL-2.0-or-later;
  dotychczasowe granty zewnętrzne pozostają bez zmian. Grant nowego mostka,
  adaptera native i integracji TTS/kompilacji/testów znajduje się w
  `eSpeak-PROVENANCE.md`, pochodzącym z `lib/espeak/README.md`, i nie zastępuje
  notices importowanych składników.
- Linkowanie native używa newlib `libm.a` i GCC `libgcc.a`, nie pełnego runtime
  libc/libstdc++ hosta. Zachowaj `newlib-COPYRIGHT.txt` i pełne uzupełnienie
  Arm BSD-3-Clause `newlib-Arm-BSD-3-Clause.txt` dla `math_err.c` (2018) oraz
  `math_config.h` (2017-2018). Sam wykaz notices newlib z Ubuntu pomija te
  teksty Arm. Kanonicznym źródłem uzupełnienia jest
  `docs/NEWLIB-ARM-NOTICES.txt`, z oficjalnym URL newlib 4.4.0.20231231 oraz
  hashami archiwum/źródeł. Same te notices BSD nie wymagają całego drzewa
  źródeł newlib/narzędzi kompilatora.
- Zachowaj `GCC13-COPYRIGHT-and-RUNTIME-EXCEPTION.txt`, w tym **GCC Runtime
  Library Exception 3.1**, i osobny `GCC-ARM-PACKAGING-COPYRIGHT.txt`.
  Informacja o pakiecie ARM sama nie licencjonuje runtime GCC. Dotychczasowy
  ograniczony przegląd nie wykazał dodatkowego obowiązku dołączania źródeł
  libgcc dla zwykłej ścieżki kompilacji GCC objętej tym wyjątkiem.
- Dołącz `LGPL-2.1.txt`, zachowaj notices/nazwy linkowanych składników LGPL
  (w tym `strstr`, `strcasestr` i metadanych OMA) oraz dostarcz komplet
  odpowiadających źródeł aplikacji/bibliotek i skryptów kompilacji. Zapewniają
  one **ścieżkę ponownego linkowania z LGPL-2.1, punkt 6(a)**; nie ograniczaj
  modyfikacji, ponownego linkowania ani inżynierii wstecznej w tym celu.
  Nie trzeba zmieniać oznaczeń tych źródeł.
- Zachowaj notices źródeł i zapis uchylenia klauzuli reklamowej Berkeley
  (22 lipca 1999 r.) już zawarty w `LICENSES` Rockboksa, także dla qsort UC
  Regents. Dotychczasowy przegląd nie uznaje jej za nadal otwartą niezgodność;
  sprawdzone wyjątki linkowania TLSF/ogólne notices GPL również nie wykazały
  nowej przeszkody runtime wynikającej z GPLv2-only.

Notices runtime należą również do `rockbox/docs/native-runtime-licenses/`
w archiwum źródeł. Zachowaj też kanoniczne uzupełnienie Arm: dostarczony skrypt
odczytuje je, a kopia generowana grupuje notices dołączonych bibliotek.
Wersje pakietów/źródeł i hashe archiwów w manifeście dokumentują pochodzenie,
nie certyfikację prawną. Szerszy przegląd zasobów/pochodzenia to osobny zakres.
Komplet dostarczonych archiwów musi zawierać wszystkie odpowiadające źródła
i notices; obowiązki dotyczą przekazania binariów innej osobie także bez publicznej
publikacji. Przed wydaniem sprawdź obowiązki redystrybucji.

## Osobny symulator Clip Zip dla Windows

Symulator Clip Zip dla Windows należy do
`installfiles/simwindows-clipzip/`, osobno od native `installfiles/clipzip/`
i dotychczasowego symulatora Clip+ w `installfiles/simwindows/`. Uruchamiaj go
tylko na komputerze, z jego własnego zapisywalnego katalogu i własnymi czystymi
ustawieniami/danymi. Nie kopiuj jego programu, wtyczek ani symulowanego
`.rockbox` na odtwarzacz. Ani walidacja ZIP-a native, ani ta instrukcja nie
oznacza, że paczka Windows została już zbudowana lub przetestowana.

Poniższe mapowanie klawiatury pochodzi z
`uisimulator/buttonmap/sansa-clip.c`, w tym gałęzi `SANSA_CLIPZIP`
(wybieranej przez `uisimulator/buttonmap/SOURCES`), nie z domysłów na podstawie Clip+:

| Klawisz komputera | Emulowany przycisk Clip Zip |
| --- | --- |
| Lewo / 4 na klawiaturze numerycznej | Lewo |
| Prawo / 6 na klawiaturze numerycznej | Prawo |
| Góra / 8 na klawiaturze numerycznej | Góra / Play |
| Dół / 2 na klawiaturze numerycznej | Dół / Menu |
| Spacja / 5 na klawiaturze numerycznej | Select |
| Insert / mnożenie (`*`) na klawiaturze numerycznej | Home |
| Page Up / 9 na klawiaturze numerycznej | Vol+ |
| Page Down / 3 na klawiaturze numerycznej | Vol- |
| Escape / 1 na klawiaturze numerycznej | Power |

Klawisze numeryczne to nie cyfry z górnego rzędu. Udokumentowany Select to
Spacja, nie Enter; Home odtwarzacza emuluje Insert, nie klawisz Home komputera.
Działania zależą od kontekstu tak jak na urządzeniu: w czytniku Spacja przełącza
pauzę/wznowienie, Lewo/Prawo nawiguje, Góra/Dół lub Page Up/Down wybiera jednostkę,
a krótkie Escape zamyka czytnik. Przytrzymane Escape to przytrzymane Power,
nie zwykły powrót. Sprawdź rzeczywiste działanie klawiatury w dostarczonym buildzie
Windows.

Rysowany interfejs SDL nie udostępnia NVDA natywnych kontrolek Windows;
samoudźwiękowienie nie dowodzi dostępności dla NVDA. W symulatorze nagrywanie
jest niedostępne: inicjalizacja/polecenia/stan nagrywania są wyłączone, a DMA
nagrywania jest atrapą. Widoczny ekran nagrywania i mowa kontrolek nie pozwalają
przechwytywać prawdziwego mikrofonu; sprawdzaj tam odmowę/komunikaty, nie udane
nagrywanie. Możliwości mikrofonu/FM natywnego Clip Zip wymagają testów fizycznych.
