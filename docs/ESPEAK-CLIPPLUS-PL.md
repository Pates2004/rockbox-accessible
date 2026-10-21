# Eksperymentalny firmware eSpeak dla Sansa Clip+

## Wydanie: r29-alpha7-20261011

Pliki native w `D:\Rockbox\rockbox\installfiles\clipplus`:

- `rockbox-clipplus-espeak-r29-alpha7-20261011.zip`.
- `rockbox-clipplus-espeak-r29-alpha7-20261011-source.tar.gz` i `SHA256SUMS`.

Wydanie drugiej Sansy: Clip Zip `r29-alpha8-20261011`. Odpowiadające wersje symulatorów
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

## Poprzednia aktualizacja przycisku i dostępności: r29-alpha4-20261009

Menu tekstu otwiera teraz przytrzymanie środkowego Select/Enter, jak w muzyce;
Góra służy do nawigacji. Poprawka wspólnego miksera dotyczy wyścigu przy
wznawianiu mowy po wygaszeniu ciszy. Rozszerzono mowę w narzędziowych wtyczkach;
zakres i ograniczenia opisuje ESPEAK-PLUGINS-PL.md. To wydanie eksperymentalne,
wymagające prób na sprzęcie; nie potwierdza naprawy chrupania na urządzeniu.
Wydanie drugiej Sansy: alpha5. Stare identyfikatory i wyniki poniżej
opisują poprzednie etapy; aktualne pliki wskazują manifest i SHA256SUMS.

## Poprzednia aktualizacja zakładek: r29-alpha3-20261009

Tamto wydanie dodało trwałe zakładki i mówiące menu tekstu pod długim Play.
Instrukcja: `ESPEAK-BOOKMARKS-PL.md`. Odpowiadająca paczka Clip Zip to alpha4.
Numery, rozmiary i wyniki alpha2 w dalszych sekcjach opisują poprzedni etap;
aktualne pliki i sumy sprawdź w dołączonym manifeście i `SHA256SUMS`.
Nowy firmware nadal wymaga próby na sprzęcie; trzaski przy szybkich zmianach
ustawień i testy fizycznego rejestratora pozostają otwarte.

## Poprzedni etap: rejestrator

Firmware **wyłącznie dla Sansa Clip+**, nie Clip, Clip v2, Clip Zip, symulator
Windows ani bootloader. Dostarczony fork eSpeak 1.44.05 r29 działa wewnątrz
Rockboksa. Nie korzysta z zewnętrznej usługi mowy, eSpeak NG ani standardowych
nagrań `.voice` ani `.talk`.

Identyfikator wydania: **`r29-alpha2-20261009`**, w parze z Clip Zip
**`r29-alpha3-20261009`**. Dokładną walidację archiwów oprzyj na `manifest.json`
i `SHA256SUMS` wydania. Manifest opisuje kontrole archiwów, nie fizyczną
walidację rejestratora; próby rejestratora na sprzęcie pozostają do wykonania.

**Eksperymentalny, nietestowany na sprzęcie, bez potwierdzenia stabilności.**
Walidacja paczki nie potwierdza startu, mowy, odtwarzania, nagrywania, USB,
baterii ani dostępności. Nie deklarujemy testów sprzętowych ani z czytnikiem
ekranu. Zachowaj działający firmware i sposób odzyskiwania. Kompilacja używa
ARM GCC 13 zamiast zalecanego GCC 9.5.0; ostrzeżenie configure jest istotne.

## Historyczne pliki etapu rejestratora

Historyczne nazwy plików etapu rejestratora; poprzednie wydania są
archiwizowane w centralnym `snapshots`, a planowana paczka ma nazwy podane
na początku tej instrukcji:

- `rockbox-clipplus-espeak-r29-alpha2-20261009.zip`
- `rockbox-clipplus-espeak-r29-alpha2-20261009-source.tar.gz`
- `SHA256SUMS`

Przechowuj razem firmware, odpowiadające źródła i sumy kontrolne. Rozmiary
nowego obrazu i liczby modułów muszą pochodzić z nowego manifestu/walidacji,
nie z alpha1.

## Instalacja bez flashowania

1. Potwierdź model Clip+ i **już zainstalowany, działający bootloader Rockboksa**.
   Paczka nie instaluje ani nie aktualizuje bootloadera. Jeśli Rockbox jeszcze
   nie startuje, przerwij i osobno przeczytaj oficjalną instrukcję instalacji
   dla Clip+. Nie flashuj żadnego pliku z tej paczki.
2. Podłącz USB w trybie udostępniającym pamięć. Rozpoznaj **pamięć wewnętrzną**,
   nie microSD. W osobnym bezpiecznym miejscu wykonaj kopię wszystkich plików
   urządzenia, całego obecnego `.rockbox`, ustawień, nagrań i plików firmware
   używanych do odzyskiwania. W razie potrzeby włącz widoczność ukrytych plików.
   Sprawdź odczyt kopii. Przeczytaj instrukcję na komputerze przed odłączeniem;
   naładuj odtwarzacz i na początku zdejmij słuchawki z uszu.
3. Sprawdź ZIP i archiwum źródeł według `SHA256SUMS`. Hashe wykrywają uszkodzenia;
   nie są podpisem cyfrowym ani potwierdzeniem tożsamości wydawcy.
4. Po wykonaniu kopii przenieś stary `.rockbox` poza katalog główny urządzenia.
   **Nie scalaj instalacji.** eSpeak używa ABI wtyczek `0xe003`; standardowe
   moduły i nakładki oraz moduły symulatora są niezgodne. Każdy dołączony moduł
   musi być przebudowany dla tego firmware.
5. Wypakuj cały `.rockbox` z ZIP-a do **katalogu głównego PAMIĘCI WEWNĘTRZNEJ**.
   Wymagane są m.in. `/.rockbox/rockbox.sansa`, `/.rockbox/espeak-data/phondata`,
   `/.rockbox/langs/polski.vstrings`. Nie twórz `.rockbox/.rockbox`, nie instaluj
   na microSD i nie kopiuj archiwum źródeł na odtwarzacz. Bezpiecznie wysuń
   urządzenie i uruchom je przez istniejący bootloader.
6. Paczka ma czyste polskie ustawienia: mowa menu i naturalny odczyt nazw plików/katalogów,
   eSpeak włączony, język systemowy, 175 słów/min (wyświetlane 0%), ściszanie
   muzyki do 25%, głośność odtwarzania -25 dB. Nie importuje ustawień użytkownika
   ani stanu wznowienia czy plików. Nie przywracaj starego `config.cfg`, `.voice`, `.talk`, `.rock`,
   `.ovl` ani `.codec`. Katalogi wyświetlania i mowy PL/EN są dołączone; angielski
   wybierz w ustawieniu języka Rockboksa. Obsługa pozostaje oparta na przyciskach.
7. Gdy mowa nie działa, urządzenie zawiesza się lub odtwarzanie jest wadliwe,
   zakończ próby i przywróć kopię. Nie polegaj na tej wersji jako jedynym
   dostępnym odtwarzaczu. Tekst instrukcji można odczytać przez NVDA na komputerze;
   nie dowodzi to sprawdzonej dostępności urządzenia.

## Powrót do poprzedniej wersji bez flashowania

Połącz USB według znanej działającej procedury odzyskiwania. Jeśli ta wersja
nie udostępnia USB, użyj udokumentowanej drogi oryginalnego firmware/bootloadera;
paczka jej nie dostarcza. Przenieś eksperymentalny `.rockbox` poza urządzenie,
przywróć **całą sprawdzoną kopię `.rockbox`** do katalogu głównego pamięci
wewnętrznej, bezpiecznie wysuń i uruchom ponownie. Nie flashuj `rockbox.sansa`,
nie wymieniaj bootloadera i nie mieszaj wersji modułów. Skrypt pakujący nigdy
nie odczytuje urządzenia ani nie porządkuje jego danych czy kopii zapasowych.

## Mowa rejestratora: źródła a stan prób sprzętowych

Dla historycznej alpha2 Clip Zip użytkownik potwierdził fizyczny start,
mowę i odczyt TXT razem z muzyką, ale rejestrator otwierał się bez mowy.
Bramka TTS rejestratora ograniczona do symulatora i blokada miksera podczas
nagrywania były potwierdzonymi ograniczeniami źródeł naszej integracji.
Ten raport nie waliduje Clip+ ani żadnego nowego wydania. Sporadyczne trzaski
przy szybkich zmianach ustawień pozostają nierozwiązane; przyczyna ani
naprawa nie są potwierdzone.

Źródła rejestratora zawierają teraz mowę zależną od możliwości natywnego PCM:
pierwszy wiersz, nawigację, poziomy, nazwę pliku, czas/rozmiar i zmiany stanu,
a także zatrzymanie mowy i DMA odtwarzania przed inicjalizacją, zamknięciem
i zmianą opcji/zegarów nagrywania. PCM mowy śledzi bieżącą częstotliwość miksera
i aktualizuje DSP, unikając starej częstotliwości końcówki po Stop, która mogła
przyspieszyć pierwsze słowa rejestratora. Backend AS3525v2 przełącza wyjście
DMA z pętli odsłuchu wejścia
na czas mowy. Nagrywanie pozostaje aktywne; mowa czasowo zastępuje bieżący
odsłuch w słuchawkach. Odsłuch wraca po końcówce mowy i około trzech pustych
ramkach miksera (kilka milisekund, bez pomiaru sprzętowego). Przechwytywanie
nie jest pauzowane dla mowy. Cyfrowe domieszanie TTS do nagrania mikrofonu
nie jest zamierzone, ale nadal wymaga poniższej kontroli WAV.

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
**Clip+ alpha2** i **Clip Zip alpha3** nadal wymagają prób fizycznych.
Nagrywanie w SDL pozostaje niedostępne.

## Etapowa pierwsza próba na urządzeniu

To proponowana lista prób ręcznych, **nie raport z testów fizycznego urządzenia**.
Używaj niskiej głośności i nieistotnych plików testowych. Przechodź dalej dopiero
po zakończeniu poprzedniego etapu. Gdy mowa zawodzi, urządzenie się zawiesza lub
dźwięk się przerywa, przerwij i użyj kopii oraz opisanej procedury przywracania,
zamiast przechodzić do nagrywania.

1. Uruchom urządzenie, przejdź przez kilka menu i krótką listę katalogów/plików.
   Sprawdź mowę menu oraz wypowiadane/literowane nazwy; zanotuj opóźnienie do
   pierwszej wypowiedzi.
2. Odtwórz krótki, sprawdzony MP3. Wywołaj komunikat menu i sprawdź, czy muzyka
   ścisza się podczas mowy, a potem wraca, bez zacinania i przerw w dźwięku.
3. Otwórz krótki tekst UTF-8 we wbudowanym czytniku. Sprawdź nawigację oraz
   pauzę/wznowienie: pozycję odczytu i ciągłość wypowiedzi po wznowieniu.
4. Dopiero po poprawnym przejściu wcześniejszych etapów wykonaj poniższy test
   rejestratora. Trwałe zakładki tekstu i pełna wtyczka czytnika książek
   pozostają na później; to wydanie ich nie dodaje.

Dla każdego etapu zapisz wersję firmware, czynność/plik, wynik, opóźnienie startu
lub rozpoczęcia mowy, opóźnienie pauzy/wznowienia, zacinanie/przerwy i inne objawy.
Odróżniaj obserwacje na urządzeniu od udanej kompilacji lub testów na komputerze.

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

## Zawartość i walidacja

Jedyny finalny ZIP trafia do `installfiles/clipplus`. Zawiera standardowe pliki
`make zip`, dokładne dostarczone `espeak-data`, wszystkie świeżo wygenerowane
`apps/lang/*.vstrings`, czyste ustawienia i `.rockbox/espeak-clipplus/` z
instrukcjami PL/EN, licencjami, autorami, pochodzeniem oraz `manifest.json`.
Standardowe nagrania `.voice` i `.talk`, w tym `langs/InvalidVoice_english.talk`,
są pomijane w bazowym archiwum `make zip` przy tworzeniu paczki firmware
korzystającej wyłącznie z TTS. Manifest zapisuje pominięte pliki; walidator
finalnego ZIP-a nadal odrzuca każdy plik `.voice` lub `.talk`, nawet wpisany
do manifestu. Katalogi mowy to tekst do syntezy na żywo, nie nagrania.
Oryginalne zasoby MBROLA nie oznaczają obsługi MBROLA.

Manifest zapisuje wersję, narzędzia, hash inwentarza źródeł, hash ELF, nagłówek
Clip+ `cli+`/66 i jego sumę, hash zawartości obrazu, ABI, inwentarze danych/mowy
oraz hashe każdego pozostałego pliku ZIP-a. Hash ZIP-a w `SHA256SUMS` obejmuje
także manifest. Walidacja sprawdza architekturę ELF ARM i zdefiniowane
`rb_espeak_synth_tracked`, `rb_espeak_synth_character`, `espeak_Synth`,
`tts_speak`, `reclist_speak` i `audio_set_pcm_output`, porównuje obraz
z `rockbox.bin` i niezależną
rekonstrukcją ELF, sprawdza nagłówki wszystkich wtyczek/nakładek/kodeków,
katalogi PL/EN, wymagane zasoby i hashe wpisów. To **kontrola struktury, nie
uruchomienie na odtwarzaczu**.

Dwa ostatnie wymagane symbole ELF pozwalają odrzucić natywny build bez TTS
rejestratora lub backendu kierowania wyjścia PCM; same symbole silnika nie wystarczą.

Oba modele w tej parze używają zwartej kompilacji ARM/Thumb i natywnego eSpeak
z `-Os` (symulator zachowuje `-O2`), z przebudową wszystkich dołączonych
wtyczek, nakładek i kodeków dla ABI `0xe003`. Skrypt budujący i walidator
wymuszają **limit surowego obrazu 1 MiB (1 048 576 bajtów) dla obu modeli**:
`rockbox.bin` i zawartości `rockbox.sansa` bez 8-bajtowego nagłówka,
niezależnie od wielkości ZIP-a. Nowy zmierzony rozmiar, tryb ARM/Thumb
i inwentarze modułów zapisz w nowym manifeście/walidacji; stare pomiary
nie potwierdzają tego wydania.

Linker native używa `--gc-sections` i może poprawnie usunąć nieużywany wrapper
`rb_espeak_synth`. Walidacja wymaga faktycznie wywoływanych przez rdzeń wejść
tracked/character, nie tego nieużywanego wrappera.
Dekodery obrazów `.ovl` używają API IMGDEC 1 oraz osobnego pola ABI wtyczek;
musi ono nadal wynosić `0xe003`. Zwykłe nakładki wtyczek mają normalny nagłówek
wtyczki. Walidator sprawdza oba formaty, nie dopuszczając standardowego starego ABI.

Osobny `*-source.tar.gz` dostarcza odpowiadające źródła, nie drugą kopię firmware.
Zawiera rzeczywiste pliki robocze Rockboksa (śledzone i nieignorowane nieśledzone,
w tym integrację native), dostarczone źródła/dane eSpeak, skrypty i manifest
plików. Pomija `.git`, dane uwierzytelniania Git, audyty wewnętrzne, narzędzia
kompilatora, buildy, instalacje i snapshoty. Lokalne zmiany identyfikuje inwentarz,
nie sam commit. Kopie źródeł i danych mają osobne cele: odtworzenie kompilacji
i uruchomienie. Na komputerze nie pozostaje drugi finalny ZIP ani rozpakowane
finalne wydanie.

Dołączono wykaz licencji/GPLv2 Rockboksa, GPLv3 eSpeak, Apache-2.0 Sonic oraz
pochodzenie; źródła zachowują informacje licencyjne poszczególnych plików.
Nie jest to certyfikacja pełnego przeglądu licencji zależności. Przed publikacją
sprawdź obowiązki związane z redystrybucją.

### Pochodzenie libc native i ograniczony przegląd

Nowe implementacje `firmware/libc/strtol.c`, `firmware/libc/strtoul.c` i test
`tools/tests/test_libc_strto.c` napisano niezależnie na potrzeby integracji,
według semantyki konwersji liczb. Nie skopiowano ich z zewnętrznej libc ani
nie zmieniono jedynie etykiety licencji dietlibc. Sprawdzono poprzednie API
i zachowanie; nie jest to prawnie certyfikowana procedura clean-room.
Te **nowe implementacje i ich test są udostępnione jako GPL-2.0-or-later**,
co umożliwia wybór GPLv3 dla połączenia. Grant nie zmienia licencji zastąpionego
kodu ani wkładów innych autorów. Ten zapis trafia do firmware i źródeł, bez
wewnętrznego audytu. Nowy skrypt pakujący Clip+, jego testy i te instrukcje
również udostępniono jako GPL-2.0-or-later; inne granty pozostają bez zmian.

Linkowanie native używa Ubuntu newlib `libm.a` i GCC `libgcc.a`, nie pełnego
środowiska libc/libstdc++ hosta. Dla sprawdzonych dołączonych modułów matematycznych
paczka dostarcza zbiór notices newlib oraz dodatkowe pełne notices Arm Ltd
BSD-3-Clause dla `math_err.c` (2018) i `math_config.h` (2017-2018).
Te ostatnie są w `newlib-Arm-BSD-3-Clause.txt`, odtworzone ze zweryfikowanego
oficjalnego archiwum źródeł newlib 4.4.0.20231231; zapisano tam URL oraz hashe
archiwum i plików źródłowych. Zbiór notices Ubuntu newlib nie zawiera tych tekstów
Arm. Kanoniczny plik projektu to `docs/NEWLIB-ARM-NOTICES.txt`, poza generowanym
katalogiem notices runtime, aby nie powodować kolizji podczas pakowania źródeł.
Same notices BSD tych modułów matematycznych nie wymagają dołączania całego
drzewa źródeł newlib ani narzędzi kompilatora.

Dołączono też notices GCC 13 z **GCC Runtime Library Exception 3.1**, osobną
informację licencyjną pakietu kompilatora ARM oraz LGPL-2.1. Sama informacja
o pakiecie ARM nie licencjonuje kodu runtime GCC; ograniczony przegląd nie wykazał
dodatkowego obowiązku dołączania źródeł libgcc dla tej zwykłej kompilacji GCC
objętej dostarczonym wyjątkiem. GPLv3 jest w `eSpeak-LICENSE.txt`. Te notices
runtime są też w `rockbox/docs/native-runtime-licenses/` archiwum źródeł.
Kanoniczna kopia notice Arm pozostaje w źródłach, ponieważ dostarczony skrypt
pakujący odczytuje ją przy ponownej kompilacji; kopia generowana grupuje notices
dołączonych bibliotek. Manifest zapisuje hashe bibliotek, wersje pakietów/źródeł
i hash mapy linkowania, nie certyfikat prawny.

Ograniczony przegląd uznaje klauzulę reklamową Berkeley za uchyloną 22 lipca 1999 r.,
także dla kodu qsort z notice UC Regents. Zachowaj notice źródła i zapis uchylenia
już dołączony w `LICENSES` Rockboksa. Nie jest to nadal otwarta niezgodność.
Sprawdzony grant/wyjątek TLSF oraz ogólne notices GPL również nie wykazały nowej
przeszkody runtime wynikającej z GPLv2-only.

Dla dołączonych składników LGPL, w tym `strstr`, `strcasestr` i metadanych OMA,
zachowaj nazwy/notices, dołącz LGPL-2.1 oraz komplet odpowiadających źródeł
aplikacji/bibliotek i skryptów kompilacji. Razem zapewniają praktyczną
**ścieżkę ponownego linkowania z LGPL-2.1, punkt 6(a)**; przekazanie nie ogranicza
modyfikacji, ponownego linkowania ani inżynierii wstecznej w tym celu. Eksperyment
nie wymaga zmiany oznaczeń licencji tych źródeł. Przekazuj razem firmware ZIP,
odpowiadające źródła i `SHA256SUMS`: niezwiązany commit upstream nie zastępuje
rzeczywistych odpowiadających źródeł.

Historyczne badania pochodzenia i szerszy przegląd wszystkich zasobów przed
publiczną publikacją nie są nowo ustalonymi blokadami prywatnego eksperymentu
ani tego ograniczonego przekazania binariów/źródeł. Finalne archiwa muszą jednak
rzeczywiście zawierać odpowiadające źródła i notices, w tym uzupełnienie Arm.
Przekazanie binariów innej osobie podlega właściwym obowiązkom także bez publicznej
publikacji. Ten ograniczony przegląd nie stanowi pełnej certyfikacji prawnej ani
akceptacji sprzętu.

Grant nowego mostka, adaptera native i integracji TTS, kompilacji oraz testów
zapisano w `eSpeak-PROVENANCE.md` (źródło: `lib/espeak/README.md`); nie zastępuje
on oryginalnych notices licencyjnych zaimportowanych składników.

## Kompilacja i weryfikacja wydania

Wymagane: Linux/WSL, Python 3.9+, Git, GNU make, Bash, Perl, zip/unzip, narzędzia
C hosta i `arm-none-eabi-gcc`/`arm-none-eabi-g++` **13.x** z odpowiednimi binutils
w PATH. Instalacja narzędzi/poprawki native to osobne zadanie. Sprawdzono dokładny
zestaw Ubuntu 24.04: `gcc-arm-none-eabi`, `libnewlib-dev`,
`libnewlib-arm-none-eabi`, `gcc-13-base` oraz teksty licencji `base-files`.
Do odtworzenia narzędzi zachowaj dostęp do odpowiadających pakietów źródłowych
Ubuntu i wersji zapisanych w manifeście. Skrypt odczytuje
`/usr/share/doc/libnewlib-dev/copyright`,
`/usr/share/doc/gcc-arm-none-eabi/copyright`,
`/usr/share/doc/gcc-13-base/copyright` i
`/usr/share/common-licenses/LGPL-2.1`; brak notices zatrzymuje pakowanie, zamiast
pomijać wymagane teksty. Inne dystrybucje wymagają sprawdzenia rzeczywistych
pakietów/notices, nie podstawienia dowolnego pliku copyright. Sprawdzony
katalog `D:/Rockbox/espeak-1.44.05-source/espeak-data`; w WSL jest to
`/mnt/d/Rockbox/espeak-1.44.05-source/espeak-data`. Rewizja silnika:
`2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f`.

Użyj poniższego identyfikatora wydania i nie zmieniaj źródeł w trakcie
kompilacji ani pakowania:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipplus \
  --source-frozen --version r29-alpha7-20261011 \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source --jobs 4
```

Skrypt używa `--target=sansaclipplus --type=n --integrated-espeak
--thumb --compiler-prefix=arm-none-eabi-`, automatycznego wrappera C++, świeżego
`Workspace/build-espeak-clipplus` i `make zip`. Przebudowuje wszystkie moduły.
Zmiana źródeł podczas kompilacji/pakowania zatrzymuje publikację. Stare buildy
i wydania przenosi, nigdy nie nadpisuje, do unikalnych `snapshots` po kontroli
ścieżek, zawartości/hashy i użycia przez procesy/otwarte pliki. Używany artefakt
lub brak wymaganej kontroli zatrzymuje operację. Kontrole obejmują bieżącego
użytkownika Linuksa, a pod WSL widoczne procesy Windows i wyłączny odczyt plików.
Nie wykluczają użycia przez innych użytkowników komputera.

Logi, hashe zamrożenia, dowody ELF/symboli i `validation.json` pozostają w
centralnym katalogu kompilacji. `elf-payload-validation.bin` to celowo zachowana kopia
diagnostyczna do niezależnego porównania, nie wydanie użytkownika. Zwykły ZIP
`make zip` pozostaje wejściem diagnostycznym, nie drugą instalacją. Pliki
symulatora nie są zmieniane. Nieudany staging nie jest opublikowanym wydaniem.
Końcowa kontrola tylko do odczytu w WSL (po zbudowaniu paczki):

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipplus --verify \
  /mnt/d/Rockbox/rockbox/installfiles/clipplus/rockbox-clipplus-espeak-r29-alpha7-20261011.zip
```

Windows PowerShell:

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
python -B tools/build_espeak_clipplus.py --target=sansaclipplus --verify 'D:\Rockbox\rockbox\installfiles\clipplus\rockbox-clipplus-espeak-r29-alpha7-20261011.zip'
```

Aby odtworzyć kompilację źródeł bez metadanych Git, wypakuj sąsiednie katalogi
`rockbox` i `espeak-1.44.05-source` z archiwum do
`/mnt/d/work/Workspace/rockbox/source-rebuild-clipplus-r29-alpha7-20261011`.
Oryginalne źródła silnika w `D:\Rockbox\espeak-1.44.05-source` pozostają na miejscu.
Ustaw wersję z `source-manifest.json`; poniższy przykład dotyczy planowanego wydania.
Katalog kompilacji musi być nowy; zachowaj poprzedni build w centralnym `snapshots`:

```sh
set -eu
cd /mnt/d/work/Workspace/rockbox/source-rebuild-clipplus-r29-alpha7-20261011/rockbox
source_dir="$PWD"
export VERSION=r29-alpha7-20261011
build_dir=/mnt/d/work/Workspace/rockbox/build-espeak-clipplus-source-r29-alpha7-20261011
mkdir "$build_dir"
cd "$build_dir"
bash "$source_dir/tools/configure" --target=sansaclipplus --type=n \
  --integrated-espeak --thumb --compiler-prefix=arm-none-eabi-
make -j4 zip
```

Surowy `rockbox.zip` **nie jest** kompletną instalacją eSpeak. Wymaga dokładnych
sąsiednich `espeak-data`, wygenerowanych `.vstrings`, ustawień i walidacji.
Pełne wydanie twórz skryptem z roboczego repozytorium Git; nie instaluj ręcznego
ZIP-a tak, jakby zawierał wszystkie wymagane dane.

Nie nadpisuj `CXX` przy kompilacji native: ominęłoby to wrapper Thumb i mogłoby
ponownie przekroczyć bezpieczny limit obrazu bootloadera.
