# HiBy R1: instalacja, aktualizacja, usunięcie i stan dostępności

Sprawdzono: 2026-10-14. [English version](HIBY-R1-INSTALL.md).

Uzupełnienie naszego portu z 2026-10-11: wspólny rdzeń ma edytor gestów
i eksplorację standardowych list oraz czytnika; weryfikacja hosta nie jest
testem fizycznego R1. Bluetooth wymaga osobnej akceptacji sprzętowej.
Natywny R1 domyślnie ładuje przez USB i odmawia zapisywalnego eksportu
karty przy niezweryfikowanym automonterze. Patrz `ACCESSIBILITY-TOUCH-PL.md`,
`ESPEAK-BLUETOOTH-PL.md` oraz `ESPEAK-HIBY-USB-PL.md`.
Nie traktuj poniższej procedury wymiany plików karty jako gotowej aktualizacji
przez działający Rockbox ani instrukcji instalacji naszego Windows EXE.

To procedura zweryfikowana w źródłach, z jawnymi warunkami wstępnymi, **nie
instalacja przetestowana na Twoim odtwarzaczu**. Wariant i zainstalowaną wersję
firmware trzeba ustalić dla konkretnego egzemplarza. Przed zapisem
w urządzeniu wykonaj punkt 2. Na potrzeby tej instrukcji nie flashowano,
pobrano i sprawdzono zmodyfikowany firmware, ale nie przeprowadzano testów
sprzętowych. Nie uruchamiano patchera ani nie zmieniano pobranego obrazu.

## Aktualne paczki i start bez wybierania systemu

Nasza natywna paczka testowa jest w `installfiles/hibyr1`, a pobrany firmware
Bahusoida w `installfiles/fw-rockbox`. Krótka instrukcja: `ESPEAK-HIBYR1-PL.md`.
Paczki mają różne role: pierwsza daje pełną `.rockbox` na kartę; druga daje
jednorazowo instalowany `r1.upt`. Nie kopiuj na kartę programu Windows.
Firmware instaluje zmodyfikowany HiBy OS **1.8b2**. Nie potwierdzono bezpiecznego
przejścia z każdej innej wersji; pobranie obrazu nie jest testem aktualizacji.

W dostarczonej `.rockbox` domyślny wybór loadera to Rockbox: cztery bajty
`00 00 00 00` w `rb_bl_mode.txt`, nie tekst „0”. Sprawdzony loader odczytuje
ten wybór i sam uruchamia Rockboxa po około jednej sekundzie bezczynności.
Nie trzeba potwierdzać systemu przy każdym starcie. Bez tego pliku pierwszy
start ma dziesięciosekundowe odliczanie i też domyślnie wybiera Rockboxa.
Nie obiecujemy zerowego opóźnienia ani niewidocznego selektora.

Aby wybrać HiBy Player z zapisanego Rockboxa, podczas selektora krótko naciśnij
**Głośność −**, a potem **Next**, aby zatwierdzić. Nie trzymaj Next podczas
włączania: to inny, produkcyjny tryb urządzenia. Wybór HiBy Player zapisuje się
na kolejne uruchomienia; wybierz ponownie Rockboxa, żeby przywrócić jego autostart.
Ta mapa wynika ze sprawdzonego loadera, ale nie została sprawdzona na sprzęcie.

Jeśli nie możesz przechwycić krótkiego selektora, przy wyłączonym odtwarzaczu
można zmienić wybór na karcie z Windows. Dla tego konkretnego loadera poniższe
polecenie PowerShell ustawia HiBy Player. **Zastąp `E:` rzeczywistą literą karty**;
nie wykonuj go na nieustalonym dysku ani podczas pracy odtwarzacza:

```powershell
[IO.File]::WriteAllBytes('E:\.rockbox\rb_bl_mode.txt', [byte[]](2,0,0,0))
```

Przywrócenie domyślnego Rockboxa to to samo polecenie z `[byte[]](0,0,0,0)`.
To wyłącznie wybór aplikacji, nie odzyskiwanie ani przywrócenie oryginalnego
firmware. Pozostałe dane `.rockbox` nie są przez to polecenie zmieniane.

## 1. Jakiego oprogramowania dotyczy instrukcja

| Oprogramowanie | Zweryfikowany stan |
| --- | --- |
| Oryginalny HiBy OS | System Linux producenta i jego aplikacja odtwarzacza. |
| Oficjalny Rockbox `hibyr1` | Istniejący port działający pod Linuksem, oznaczony jako niestabilny. To nie nasz build TTS; nie zawiera integracji Bluetooth Bahusoida. |
| Rockbox Audiobook Mod Bahusoida | Istniejące wydanie społecznościowe R1 z inną mapą przycisków, gestami dotykowymi i kodem Bluetooth. Nie zawiera naszej integracji eSpeak. |
| Nasz R1 ze wspólnym TTS | Osobny prototyp Windows oraz adaptacja hosted HiBy są opisane w `ESPEAK-HIBYR1-PL.md`. Nie jest to potwierdzony build sprzętowy z gestami TalkBack ani Bluetooth; nie wgrywaj programu Windows na odtwarzacz. |

Sprawdzony fork to [bahusoid/rockbox](https://github.com/bahusoid/rockbox).
Domyślna gałąź `Mod25.12.07` wskazuje
`059809d123a5b2d4ff1d65b571e99cf56b35dd51` (2026-10-01).
Najnowsze opublikowane wydanie R1 to [26.09.17 / `x1600_hiby_v2`](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2),
commit `94c69704e9cf8bae77240a98a8eb7bd5c576f426` (2026-09-17).
HEAD gałęzi i wydanie są różnymi rewizjami. Z przypiętego wydania bierzemy
wyłącznie zmodyfikowany firmware z loaderem. Aplikację na kartę dostarcza nasza
osobna paczka eSpeak, nie paczka aplikacji Bahusoida.

Oficjalny upstream sprawdzono przy
`7d090f24b990ef54e3f9dc7eb2edba4865605471`.
Jego [rejestr portów](https://github.com/Rockbox/rockbox/blob/7d090f24b990ef54e3f9dc7eb2edba4865605471/tools/builds.pm)
oznacza R1 jako niestabilny. Obsługa zwykłego portu nie potwierdza naszego TTS.

## 2. Przed instalacją: informacje i warunek odzyskiwania

1. Sprawdź dokładny model i firmware w ekranie **Informacje / About** oryginalnego
   odtwarzacza. Zapisz pełną wersję i numer kompilacji, wariant modelu oraz
   ewentualny istniejący mod. Nie używaj obrazów R3, R3 Pro II, R2 ani R1 MIDI
   na R1, zakładając ich zgodność.
2. Potwierdź zgodność tej konkretnej wersji początkowej z wybranym modem/wydaniem,
   również przy zmianie wersji systemu. Obraz dostarczany przez fork opisano
   jako **1.8b2**. Jego dostępność nie dowodzi bezpieczeństwa aktualizacji ani
   obniżenia wersji z dowolnego firmware. Nie ustalono uniwersalnej tabeli
   zgodności. Jeśli ten punkt jest nierozstrzygnięty, zatrzymaj się przed flashowaniem.
3. Uzyskaj odpowiednią **niezmodyfikowaną oficjalną aktualizację R1** do powrotu
   z [pomocy HiBy](https://store.hiby.com/apps/help-center). Zapisz łańcuch
   odnośników producenta, wersję, rozmiar i SHA-256. Potwierdź, że to zwykła
   aktualizacja z karty, nie obraz fabryczny/burn. Samodzielnie obliczony hash
   opisuje posiadany plik; bez zaufanego wzorca nie potwierdza autentyczności.
   Jeśli HiBy nie podaje sumy, uzyskaj potwierdzenie zamiast wymyślać wzorzec.
4. Zanim polegasz na aktualizacji wymuszonej, ustal jej sposób dla tego egzemplarza
   i firmware. Instrukcja producenta jest wewnętrznie sprzeczna — patrz punkt 7.
   Potwierdź dostęp do zwykłego aktualizatora, sprawny czytnik karty oraz pomoc
   na wypadek nieudanego odzyskiwania. Sam plik do pobrania nie jest sprawdzonym
   planem ratunkowym.
5. Zabezpiecz muzykę, ustawienia, zakładki i inne nieodtwarzalne dane karty oraz
   urządzenia. Kopia karty nie jest kopią wewnętrznego firmware. W tym projekcie
   kopie do odzyskiwania i poprzednie wydania należą do centralnego `Snapshots`,
   z datą, pochodzeniem i hashami. Takie kopie mają konkretny cel ratunkowy.
6. Przygotuj naładowany odtwarzacz, sprawną kartę, czytnik i pewne zasilanie.
   Przestrzegaj wymagań zasilania konkretnego firmware; nie podajemy uniwersalnego
   minimalnego procentu baterii. Nie formatuj jedynej kopii danych. Sprawdź
   odczyt karty i wolne miejsce. Obsługa systemu plików przez HiBy OS nie dowodzi,
   że każdy format zadziała w aktualizatorze ratunkowym.
7. Zapewnij pomoc, jeśli nie możesz samodzielnie obsłużyć fabrycznego aktualizatora
   lub menu startowego. Nie potwierdzono ich udźwiękowienia. Windows/NVDA może
   pomóc przygotować kartę, ale nie udostępnia ekranów firmware odtwarzacza.

[Polityka gwarancyjna HiBy](https://store.hiby.com/pages/warranty) wskazuje,
że nieautoryzowane modyfikacje oprogramowania kończą gwarancję producenta.
Powrót do stock nie dowodzi przywrócenia gwarancji ani niewykrywalności modyfikacji.

## 3. Pliki, integralność i rzeczywiste ścieżki instalacji

Autor publikuje następujące pliki na stronie przypiętego wydania:

**Do tego projektu wybierz nasz**
`installfiles/hibyr1/rockbox-hibyr1-espeak-r34-alpha12-20261019-hardware-test.zip`
**oraz firmware** `installfiles/fw-rockbox/hibyr1_1.8b2_bahusoid_rb_26.09.17.zip`.
Poniższa tabela opisuje materiały autora loadera. Jego paczka aplikacji i głos
z nagraniami nie zastępują naszej paczki eSpeak i nie należy ich na nią nakładać.

| Plik | Rola | SHA-256 podany przez API wydań GitHuba |
| --- | --- | --- |
| `rockbox_hibyr1_bahusoid_26.09.17.zip` | Pełna paczka Rockboxa na kartę | `db4473d351c3a0065ff03cbd529b0198be50c788ce6a0a8e0bd937527710f1c9` |
| `hibyr1_1.8b2_bahusoid_rb_26.09.17.zip` | Zmodyfikowana aktualizacja systemu wewnętrznego, opisana jako firmware 1.8b2 z loaderem | `770fd83626b7899a254628670856408f07415061589820ac2991d685aa9443d9` |
| `voice_en_hibyr1_bahusoid_26.09.17.zip` | Opcjonalny, pasujący angielski głos menu z nagraniami | `7fd5f1f8b901ebc0a662190b12f49f3613c110fe02db6e2cc0e2cf41c2460dd7` |

Zmodyfikowany firmware pobrano i jego 38540535 bajtów zweryfikowano z podaną
sumą. Pozostałe dwa archiwa w tabeli mają tylko sumy z metadanych i nie są
naszą paczką TTS. Firmware ZIP zawiera wyłącznie `r1.upt`, 42113024 bajty,
SHA-256 `19231b97e19c429da101b1fa2ed670a79a74408ba45e29de446f9fd249410dc6`.
Sprawdzono CRC ZIP, łańcuchy sum fragmentów i kompletne MD5 kernela/rootfs,
skrypty startowe oraz zgodność hasha osadzonego loadera z plikiem wydania.
Nie jest to sprzętowy test obrazu ani dowód bezpiecznego downgrade.
Porównaj pobrane bajty przed użyciem; przy rozbieżności zatrzymaj się.
Komponenty producenta w zmodyfikowanym UPT nie otrzymują automatycznie licencji
GPL Rockboxa. Nie potwierdzono prawa do ich redystrybucji. Hash go nie zapewnia.

Opis wydania określa taki układ karty, bez dodatkowego nadrzędnego folderu ZIP:

```text
katalog główny karty/
    .rockbox/
        rockbox.r1
        ...pasujące kodeki, pluginy, biblioteki i zasoby...
    r1.upt             (zweryfikowana zmodyfikowana aktualizacja, tylko do pierwszej instalacji)
```

Włącz pokazywanie ukrytych plików, sprawdzając `.rockbox`. Nie twórz
`.rockbox/.rockbox`, nie kopiuj samych ZIP zamiast zawartości i nie mieszaj
pluginów/kodeków innego urządzenia z tym buildem. Osobny plik `bootloader.r1`
służy do przygotowania zmodyfikowanego UPT, nie zastępuje `r1.upt`.

[Konfiguracja R1](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/firmware/export/config/hibyr1.h)
i [loader hosted](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/bootloader/hibyos_linux.c)
potwierdzają następujące ścieżki:

| Lokalizacja | Znaczenie |
| --- | --- |
| Karta `/.rockbox/rockbox.r1` | Aplikacja Rockboxa; R1 widzi ją jako `/data/mnt/sd_0/.rockbox/rockbox.r1`. |
| R1 `/tmp/rockbox.r1` | Kopia uruchamiana przez loader; nie miejsce instalacji dla użytkownika. |
| R1 `/usr/bin/bootloader.rb` | Loader dodawany przez patcher do wewnętrznego rootfs. |
| R1 `/usr/bin/hiby_player.sh` | Zmieniony skrypt startowy wywołujący loader. |
| R1 `/usr/bin/hiby_player_orig.sh` | Oryginalny skrypt startowy zachowany przez patcher Bahusoida do uruchamiania fabrycznej aplikacji. |

Sprawdzona ścieżka to `/data/mnt/sd_0`, nie `/usr/data/mnt/sd_0` występujące
w README innego forka. Na komputerze używaj rzeczywistego dysku karty,
nie linuksowej ścieżki. Nie edytuj ręcznie plików wewnętrznego systemu.

[Patcher](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/tools/r1_patcher/r1_patcher.sh)
przebudowuje system plików rootfs i obsługę hotplug, zachowując zawartość
wejściowego kernela. Wynikowy UPT zawiera dane aktualizacji kernela i rootfs.
Pierwsza instalacja zapisuje więc pamięć wewnętrzną; nie ogranicza się do karty.
Patcher usuwa swój katalog roboczy i nie został uruchomiony. Przygotowanie
własnego UPT wymaga osobnego przeglądu oraz odizolowanego środowiska pracy.

## 4. Pierwsza instalacja, po spełnieniu wszystkich warunków

1. Sprawdź pochodzenie, informacje licencyjne i hashe obu archiwów wydania oraz
   zgodność wybranego firmware. Oficjalną paczkę do powrotu zachowaj osobno.
   Na karcie instalacyjnej umieść tylko zamierzony plik aktualizacji UPT.
2. Rozpakuj naszą pełną paczkę
   `rockbox-hibyr1-espeak-r34-alpha12-20261019-hardware-test.zip` z `installfiles/hibyr1`
   do katalogu głównego karty. Osobno rozpakuj zweryfikowany firmware
   `hibyr1_1.8b2_bahusoid_rb_26.09.17.zip` z `installfiles/fw-rockbox`, aby jego
   aktualizacja była w katalogu głównym jako `r1.upt`. Sprawdź powyższą strukturę. Jeśli
   rzeczywista zawartość jest inna, zatrzymaj się i wyjaśnij różnicę, zamiast
   zgadywać nazwę lub właściwy plik do flashowania.
3. Bezpiecznie wysuń kartę/nośnik USB i włóż kartę do wyłączonego R1.
4. Preferuj zwykłą, widoczną aktualizację z systemu fabrycznego: uruchom HiBy OS,
   wybierz **System → Firmware update → TF/SD-card update**, sprawdź proponowany
   obraz i potwierdź tylko zamierzoną aktualizację. Ścieżkę przez menu opisuje
   [HiBy](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/);
   dokładne etykiety po tłumaczeniu mogą się różnić. Użycie jej z wybranym modem
   nadal wymaga potwierdzenia zgodności. Przy działającym menu nie potrzeba
   wymuszonych kombinacji startowych; jeśli menu jest niedostępne, patrz punkt 7.
5. Poczekaj na zakończenie aktualizacji i restartu. Nie odłączaj zasilania,
   nie wyjmuj karty i nie naciskaj wielokrotnie przycisków podczas zapisu.
   Przy błędzie zachowaj dokładny komunikat; nie próbuj kolejnych przypadkowych
   obrazów ani poleceń ratunkowych.
6. Sprawdź wybraną aplikację w selektorze startowym Rockboxa. Loader Bahusoida
   używa Volume +/− do nawigacji, a Next lub Power do zatwierdzania.
   Play nie jest przyciskiem powrotu z głównego selektora; funkcja powrotu
   dotyczy jego zagnieżdżonych ekranów. Pamięta poprzedni wybór i może uruchomić go po krótkim czasie;
   nie zakładaj długiego okna na reakcję. Początkowy wybór to Rockbox.
   Nie sprawdzono obsługi tego selektora bez wzroku.
7. Uruchom Rockboxa z bezpieczną głośnością i słuchawkami przewodowymi. Sprawdź
   wersję, przeglądanie karty, krótki plik audio, pauzę, oba kierunki nawigacji,
   głośność, blokowanie/odblokowanie i zwykłe wyłączenie. Przy kolejnym starcie
   wybierz **HIBY PLAYER** i sprawdź fabryczną aplikację oraz menu aktualizacji.
8. Po udanej aktualizacji przenieś instalacyjny UPT z karty do datowanego archiwum
   ratunkowego. Zachowaj jedno rozpoznawalne aktualne wydanie z manifestem;
   pozostawiony UPT nie powinien przypadkiem wywołać późniejszej wymuszonej aktualizacji.

Opcjonalny angielski głos zawiera gotowe nagrania dla tego konkretnego forka.
Nie syntetyzuje dowolnych nazw/książek, nie dostarcza naszego polskiego TTS
i nie potwierdza pełnego pokrycia mową. W tym forku nie wyłączaj mowy menu tylko
po to, żeby uzyskać sygnał wyłączenia opisany w wydaniu. Nie wymieniono w nim
polskiego głosu. Nasz prototyp ma odrębną syntezę eSpeak: ustawienie używania
plików głosowych nie steruje nią.

## 5. Uruchamianie HiBy OS i aktualizowanie Rockboxa

Wybór **HIBY PLAYER** uruchamia zachowaną aplikację fabryczną w zmodyfikowanym
systemie. **Nie** usuwa loadera ani nie odtwarza niezmienionego firmware.
Jeśli selektor znika szybko, użyj jego nawigacji fizycznej od razu podczas
startu; nie wymyślaj specjalnej kombinacji dualboot.

Zwykła aktualizacja samego Rockboxa:

1. Przeczytaj wymagania wydania dotyczące loadera/firmware. Zatrzymaj się,
   jeśli potrzebna zmiana systemu wykracza poza tę instrukcję. Nigdy nie używaj
   w zastępstwie paczki Sansy.
2. Wyłącz urządzenie prawidłowo. Zarchiwizuj całą poprzednią `.rockbox`, wraz
   z ustawieniami, zakładkami i własnymi mapami, oznaczając wersję/datę i hashe.
   Preferuj przeniesienie zamiast bezcelowych duplikatów wydań. Zachowaj muzykę
   oraz pozostałe dane użytkownika.
3. Umieść na karcie pełną, pasującą nową `.rockbox`. Świeży katalog zapobiega
   pozostawieniu starych pluginów/kodeków po nałożeniu paczki. Odtwarzaj tylko
   ustawienia jawnie zgodne z nową wersją; zachowaj kopię do odzyskiwania.
4. Bezpiecznie wysuń nośnik, uruchom Rockboxa, sprawdź wersję i ponów test
   odtwarzania przewodowego, sterowania, zainstalowanej mowy oraz wyboru HiBy Player.

Według wydania zwykła aktualizacja Rockboxa wymienia pliki karty bez ponownego
flashowania UPT. Warunkiem są niezmienione wymagania loadera/systemu. Aktualizacja
HiBy OS jest osobnym zapisem wewnętrznego firmware i może zastąpić zmieniony
skrypt/loader. Przed stock OTA lub aktualizacją lokalną ponownie sprawdź zgodność.
Nie podmieniaj samego `rockbox.r1` między niepowiązanymi buildami: muszą pasować
kodeki, pluginy, biblioteki, zasoby i format głosu. Nasz TTS ma ponadto odrębne
ABI pluginów; nie importuj stockowych modułów do przyszłego buildu TTS.

## 6. Pełne usunięcie i powrót do oryginalnego odtwarzacza

1. Zabezpiecz dane i zapisz zainstalowany mod/wersję. Wybierz **HIBY PLAYER**
   i wejdź do jego zwykłego menu aktualizacji firmware.
2. Ponownie sprawdź dokładny model, pochodzenie, hash i zasady zmiany wersji
   oficjalnego UPT do powrotu. Użyj niezmodyfikowanej paczki aktualizacji z karty,
   nie obrazu Bahusoida ani obrazu fabrycznego/burn. Jeśli odpowiednia paczka
   lub zasady zmiany wersji pozostają nieznane, zatrzymaj się tutaj.
3. W katalogu głównym karty umieść tylko zamierzony oficjalny UPT. Zastosuj go
   zwykłym fabrycznym aktualizatorem TF/SD-card, sprawdź potwierdzenie i pozwól
   zakończyć zapis oraz restart bez przerywania. Jeśli fabryczna aplikacja
   nie startuje, stosuj wyłącznie procedurę odzyskiwania potwierdzoną dla
   Twojego egzemplarza — patrz punkt 7.
4. Potwierdź zwykły start stock bez selektora Rockboxa, oczekiwaną wersję
   firmware, działanie karty/audio/przycisków i jeszcze jeden zwykły restart.
   To kryteria odbioru; nie przeprowadziliśmy ich na R1.
5. Dopiero po udanym powrocie do stock zarchiwizuj poprzednią `.rockbox`
   i usuń ją wraz z pozostałymi instalacyjnymi UPT z aktywnej karty. Zachowaj
   muzykę oraz potrzebne dane. Przywracaj ustawienia stock tylko przy zgodności.

Ponowne wgranie odpowiedniej oficjalnej aktualizacji systemu jest ścieżką
powrotu wynikającą ze źródeł. Samo usunięcie `.rockbox`, wybranie HiBy Player
lub reset ustawień nie odinstalowują wewnętrznej modyfikacji. Nie oznacza to
odtworzenia fabrycznego obrazu bajt w bajt, usunięcia wszystkich śladów,
gwarantowanego unbrick ani automatycznego przywrócenia gwarancji.

## 7. Odzyskiwanie: potwierdzone fakty i granice działania

| Sytuacja | Następny bezpieczny krok |
| --- | --- |
| Rockbox nie działa, ale selektor startowy działa | Wybierz HiBy Player; sprawdź układ karty i przywróć z komputera kompletną, znaną i pasującą `.rockbox`. |
| HiBy Player działa | Użyj udokumentowanego zwykłego aktualizatora ze zweryfikowanym obrazem do powrotu. |
| Nie można wejść do zwykłego aktualizatora | Przed próbą potwierdź z HiBy lub autorem sekwencję aktualizacji wymuszonej dla dokładnej wersji/modelu. |
| Aktualizacja wisi, potrzebny jest USB boot albo brak znanego obrazu ratunkowego | Zachowaj dokładny objaw/wersję i skontaktuj się z pomocą; nie używaj niepowiązanych plików ratunkowych ani narzędzi produkcyjnych. |

Istnieje rzeczywista sprzeczność dokumentacji: [wydanie](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2)
podaje **Power + Volume Up**; [instrukcja HiBy](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/)
również przypisuje Volume Up przy starcie do wymuszonej aktualizacji w punkcie 2,
ale w punkcie 9 podaje **Play/Pause + Power**. To przypisane źródłom opisy,
nie dwie zamienne instrukcje do próbowania. Bez egzemplarza/firmware
i potwierdzenia nie rozstrzygniemy ich zastosowania. Instrukcja opisuje
przytrzymanie Power przez co najmniej dziesięć sekund jako reset sprzętowy;
to nie odtwarzanie firmware i nie sposób celowego przerywania aktualizacji.

Aktualny upstream zawiera [kod odzyskiwania USB X1600](https://github.com/Rockbox/rockbox/blob/7d090f24b990ef54e3f9dc7eb2edba4865605471/utils/jztool/src/x1600.c),
lecz jego loader paczki wymaga obrazu pierwszego etapu, `bootloader2.ucl`
i `bootloader-info.txt`. Nie potwierdzono, że hosted `bootloader.r1` Bahusoida
jest taką paczką. Sam przyrostek `.r1` nie dowodzi zgodności. Ogólne README
jztool opisuje głównie odtwarzacze X1000 i nie stanowi pełnej procedury ratowania R1.
Nie zalecamy tutaj poleceń jztool, Zadig, NAND ani fabrycznego flashowania.
Odzyskiwanie sprzętowe i dostępność jego ekranów pozostają niesprawdzone.

## 8. Przyciski i istniejący edytor mapowań

[Układ producenta](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/)
obejmuje Power, Volume +, Volume −, Play/Pause i Next po prawej stronie;
**nie ma fizycznego Previous**. Lokalny/upstream kod deklaruje `BUTTON_PREV`
dla współdzielonej mapy, co nie tworzy rzeczywistego przycisku. Bahusoid ma
osobną mapę R1. Nie przenoś jej symbolicznych nazw do upstreamowej mapy R3 Pro II.

Nasza paczka ma inną mapę niż aplikacja Bahusoida. Obowiązujące przypisania,
kombinacje i zasady bezpiecznego użycia Power opisuje `HIBY-R1-CONTROLS-PL.md`.
Skrót dla świeżych ustawień naszej paczki:

| Fizyczny przycisk | Listy/menu | Ekran odtwarzania (WPS) |
| --- | --- | --- |
| Volume + / − | Krótkie: poprzednia / następna pozycja; przytrzymanie reguluje głośność. | Krótkie i przytrzymane regulują głośność. |
| Play/Pause | Wstecz; przytrzymanie otwiera główne menu | Poprzedni utwór; przytrzymanie przewija wstecz. |
| Next | Aktywacja; przytrzymanie otwiera menu kontekstowe | Następny utwór; przytrzymanie przewija naprzód. |
| Power | Aktywacja / OK | Odtwarzanie/pauza; przytrzymanie nie otwiera menu i może zażądać wyłączenia. |
| Power + Next | Nie używaj zamiast zwykłego Next. | Menu kontekstowe odtwarzania; użyj krótko. |
| Power + Volume + | Blokowanie/odblokowanie | Blokowanie/odblokowanie; przy zablokowaniu Volume reguluje głośność bez przytrzymania. |

To weryfikacja kodu/dokumentacji i testów hosta, nie ergonomii na sprzęcie.
Historyczna [mapa forka](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/docs/mods/hibyr1-keymap.md)
dotyczy jego aplikacji, nie naszej paczki. Nasz czytnik tekstu ma osobną mapę
opisaną w instrukcji sterowania. Unikaj przypadkowego długiego trzymania Power.

Istniejący [plugin keyremap](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/apps/plugins/keyremap.c)
obsługuje już edycję, test, import/eksport, zapis oraz funkcje odczytu list.
W forku otwórz **Plugins → Applications → keyremap**, zaimportuj tekstową mapę
przygotowaną dla dokładnie tego targetu i sprawdź **Temp Core Remap** przed
**Set Core Remap**. Druga opcja zapisuje aktywną mapę rdzenia;
**Remove Core Remap** przywraca wbudowaną mapę. Funkcje mowy list nie dowodzą
dostępności każdej ścieżki edycji i błędów.

Jeśli zapisana mapa uniemożliwi nawigację, w miarę możliwości wyłącz urządzenie
prawidłowo i przez czytnik karty przenieś `/.rockbox/keyremap.kmf` do datowanej
kopii, a następnie uruchom ponownie. Zachowaj zawartość do diagnostyki.
Nie zmieniaj wewnętrznego firmware, żeby cofnąć mapę z karty. Ta ścieżka
wynika z kodu, ale nie została przetestowana na R1. Mapowanie fizyczne nie
obejmuje automatycznie menu startowego/ratunkowego, pluginów czytających surowe
przyciski ani wszystkich gestów. Nasza paczka ma odrębne udźwiękowione edytory
w **System → Ustawienia przycisków fizycznych** oraz
**Dostępność → Ustawienia przeglądania dotykowego → Przypisania gestów**.
Ich działanie, próbę z wycofaniem i odzyskiwanie opisują
`ACCESSIBILITY-BUTTONS-PL.md` oraz `ACCESSIBILITY-TOUCH-PL.md`.
Nie mieszaj ich plików ustawień z `keyremap.kmf`. Nie potwierdzono ich jeszcze
na fizycznym R1.

## 9. Dostępne gesty naszej paczki i granice testów

[Sterowanie dotykowe forka](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/docs/mods/touch-controls.md)
obejmuje dotknięcia, przewijanie i gesty od krawędzi. Nie potwierdza eksploracji
bez aktywowania, udźwiękowionego fokusu ani globalnego dwukrotnego stuknięcia
znanych z TalkBack. R1 działa pod Linuksem, nie Androidem; instalacja TalkBack
nie jest ścieżką tej implementacji.

Nasza paczka rozszerza wspólny rdzeń o eksplorację i konfigurowalne gesty.
Domyślne przypisania są następujące; szczegóły i ograniczenia opisuje
`ACCESSIBILITY-TOUCH-PL.md`:

| Gest | Domyślna akcja semantyczna |
| --- | --- |
| Przesunięcie w lewo | W górę |
| Przesunięcie w prawo | W dół |
| Przesunięcie w dół | W prawo |
| Przesunięcie w górę | W lewo |
| Dwukrotne stuknięcie | Aktywacja bieżącego fokusu |
| Jeden ciągły ruch w lewo, potem w prawo | Wstecz |
| Jeden ciągły ruch w prawo, potem w lewo | Ekran główny |

Eksploracja standardowych list i czytnika tekstu odczytuje wskazaną pozycję
bez aktywowania. Edytor obejmuje „Nieprzypisany” oraz próbę z potwierdzeniem
lub cofnięciem po dwudziestu sekundach. Są to funkcje implementacji sprawdzane
na hoście, nie potwierdzenie fizycznego dotyku, progów gestów ani globalnej
dostępności wszystkich wtyczek. Nie zakładamy wielodotyku ani gotowej klawiatury
typu TalkBack. Zachowaj dostęp do fizycznych przycisków i opisanej procedury
przywrócenia sterowania.

## 10. RAM, wspólny TTS i Bluetooth: konkretna kolejność prac

HiBy [podaje 64 MB RAM](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/spec/).
[Pomiar fizycznego R1 opublikowany przez dewelopera](https://github.com/ZanHZANG/hiby-r1-native-development/blob/e8b37d471d5caae5cc0548664f3576682c8c21d6/BUILD.md#memory)
zawiera `MemTotal=56936 kB` (55,60 MiB), `MemAvailable=37020 kB` (36,15 MiB),
`MemFree=14232 kB` (13,90 MiB) i brak swap. To cudzy pomiar jednego
niedostatecznie opisanego obciążenia, nie nasz wynik ani gwarantowane miejsce
dla TTS. Pamięć dostępna uwzględnia już pamięć możliwą do odzyskania;
nie dodawaj jej ponownie do wolnej. Konfiguracyjne `memory=16` Rockboxa
oznacza wspólną arenę rdzenia 15 MiB, nie limit procesu Linux 16 MiB
ani 64 MiB wolnych na syntezę.

Wspólne `tts`, `talk`, kolejka/mikser mowy, nawigacja tekstu i zakładki są teraz
podstawą prototypu R1; szczegóły etapu zawiera `ESPEAK-HIBYR1-PL.md`.
`tools/configure` dopuszcza zintegrowaną syntezę dla aplikacji hosted R1,
a `lib/espeak/espeak.make` obsługuje `APP_TYPE=hibyos`. Dodano atomowe blokady
hosted zamiast polegania na pustych linuksowych operacjach wyłączania przerwań.
To nie kończy walidacji MIPS Linux: ABI, runtime, alokator, ścieżki plików,
stos i mieszany PCM na kablu wymagają odpowiednich testów. Symulator R1 SDL
sprawdza logikę interfejsu, nie właściwy program hosted, RAM, radio, fizyczne
przyciski ani instalację. Nie scalono całego forka z roboczym drzewem Sansy.

[Opis Bluetooth Bahusoida](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/docs/mods/bluetooth-hiby-x1600.md)
i [implementacja](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/apps/hiby_bluetooth.c)
wykorzystują `bluetoothctl`, routing BlueALSA i usługi producenta, na podstawie
[patchy bidhaty](https://github.com/bidhata/hiby-r1-rockbox-bt).
Zawierają parowanie, stan i przyciski słuchawek, ale jawnie ostrzegają o crashu
Rockboxa po wyłączeniu słuchawek podczas grania i niestabilnej zmianie kodeka
w trakcie odtwarzania. Sprawdzona aktualna gałąź zachowuje te ostrzeżenia.
Listy urządzeń/kodeków w badanym kodzie nie mają funkcji odczytu pozycji.
Nie obiecujemy stabilnego BT, konkretnego kodeka, dostępnego parowania ani TTS przez BT.

Kolejność rozwoju: potwierdzić egzemplarz/firmware/odzyskiwanie; przypiąć
pojedyncze zmiany backendu; zweryfikować wspólny TTS na kablu oraz zaimplementowaną
mapę fizyczną, gesty i edytory na urządzeniu; następnie diagnozować BT na prawdziwym
sprzęcie. Próby BT zacząć od SBC, rzeczywistego wspólnego routingu muzyki i mowy,
udźwiękowionego wyszukiwania/błędów, utraty zasilania słuchawek, ponownego
łączenia, blokady, restartu i przejścia kabel/radio. Przed zwiększeniem areny
lub deklaracją czasu pracy zmierzyć szczyt RSS/PSS, dostępny RAM i baterię
przy rzeczywistym obciążeniu.

**Nadal wymaga prawdziwego R1:** pełny cykl instalacja/usunięcie/odzyskiwanie,
oba wybory startowe, każde sterowanie fizyczne/gest i przejście blokady,
synteza oraz anulowanie/pauza/wznowienie podczas grania muzyki, pokrycie mową
PL/EN, obsługa błędów, presja pamięci, utrata/odtworzenie BT i testy baterii.
To warunki odbioru, nie ukończone próby. Dokładny model/firmware i dostęp
do egzemplarza testowego pozostają pytaniami do użytkownika przed instrukcjami
zależnymi od konkretnego sprzętu.
