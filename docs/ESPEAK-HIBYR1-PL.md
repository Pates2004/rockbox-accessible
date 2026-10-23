# Zintegrowany eSpeak na HiBy R1 — wydanie rozwojowe

Aktualizacja źródeł 2026-10-21: publiczna gałąź rozwojowa zawiera pięć trybów
ogłaszania pozycji i prace nad Bluetooth, z ABI wtyczek `0xe006`. Publikacja
źródeł nie oznacza nowego zaakceptowanego wydania native/Windows. Poniższe
opisy alpha12 i wcześniejszych paczek są historyczne; sprawdzaj manifest i ABI
rzeczywiście wgranej paczki, nigdy nie mieszaj jej modułów z nowym buildem.
Kompilowanie zacznij od [instrukcji budowania](BUILD-ACCESSIBLE-PL.md).

Wydanie testowe `r34-alpha12-20261019` ujednolica procenty wysokości, modulacji
i głośności, zawiera nowy polski słownik oraz poprawki obsługi braku pamięci
w eSpeaku/Sonic i ograniczenia ponawiania poleceń Bluetooth. Nie zmienia
zapisanych wartości parametrów ani podstawowego sterowania. Plan radia
internetowego, podcastów i bibliotek opisuje osobny
[przegląd sieci](HIBY-R1-NETWORK-EMULATION-PL.md); nie są to jeszcze działające
usługi tego wydania.

Zachowuje wcześniejsze poprawki rozmiarów stosów Łączności/Bluetooth
i uruchamiania wątku dźwięku:
biblioteka systemowa R1 odrzucała stos 64 KiB, wymagając co najmniej 128 KiB.
Backend respektuje teraz minimum platformy. Czysta paczka R1 ustawia też
rzeczywiste −25 dB (`volume: -250` w konfiguracji natywnej), nie −2,5 dB.
Aktualizacja nie wymaga ponownego flashowania firmware ani formatowania karty.
Testy biblioteki i kompilacji nie zastępują odsłuchu na fizycznym urządzeniu.

Wydanie zachowuje rozszerzony edytor: trzykrotne stuknięcie
(domyślnie nieprzypisane), dwukrotne stuknięcie z przytrzymaniem (menu kontekstowe),
czas przytrzymania dotyku i opcjonalne bezpieczne powtarzanie gestów.
Nieprzypisane trzykrotne stuknięcie nie uruchamia akcji dwukliku. Można też
przypisać datę, podsumowanie odtwarzania i urządzenia, przełączanie przeglądania
dotykowego oraz bezpośrednie otwieranie wybranych ekranów. Zobacz
[ustawienia dotyku](ACCESSIBILITY-TOUCH-PL.md) i [przycisków](ACCESSIBILITY-BUTTONS-PL.md).
Dotychczasowe sterowanie radiami pozostaje w
Ustawienia → Łączność, przywraca wcześniejsze preferencje po trybie samolotowym
i dodaje osobno przypisywane przełączanie eSpeaka/plików głosowych z syntetycznym
komunikatem. Zobacz [łączność](HIBY-R1-CONNECTIVITY-PL.md) i
[przełączanie usług](ACCESSIBILITY-SHORTCUT-PL.md). Test zachowuje polski interfejs
i włączoną mowę; angielski, wyłączona mowa i domyślny potrójny Power są dopiero
na przyszłe wydanie publiczne. Progi i użyteczność dotyku wymagają prób na sprzęcie.

Ten target korzysta ze wspólnego eSpeaka 1.44.05 r34, kolejki mowy, czytnika
tekstu i integracji zakładek tekstowych oraz dźwiękowych. Nie piszemy czytnika
od nowa ani nie zastępujemy syntezy programem systemowym. Wydanie R1 jest
aplikacją linuksową, a nie firmware działającym bez systemu operacyjnego.

Wspólny czytnik udostępnia Znajdź, Znajdź następne,
Znajdź poprzednie oraz wpisywanie linii, strony i procentu w Opcjach tekstu.
Menu otwiera przytrzymanie Next; dalej obowiązuje dotychczasowe sterowanie menu
i pisaniem. Osobne zapisywane opcje wyszukiwania mają domyślne wartości
Ignoruj wielkość liter oraz Zatrzymaj i ogłoś. Wszystkie opcje wielkości liter
i zawijania opisują [ustawienia Talkbox](ESPEAK-ROCKBOX-PL.md), a szczegóły
działania — [czytanie i zakładki](ESPEAK-BOOKMARKS-PL.md).

Projekt nie zmierzył baterii ani dostępnego RAM-u na fizycznym R1.
Nowy etap dodaje blokadę i odczyt Wi-Fi przy starcie, ograniczone czasowo
wyłączenie całego urządzenia, opisy domyślnych przycisków z przewodnikiem oraz
ciemne/jasne kolory interfejsu. Zobacz `HIBY-R1-POWER-PL.md`,
`HIBY-R1-CONTROLS-PL.md` i `INTERFACE-APPEARANCE-PL.md` — opisują też granice
testów sprzętowych i skórek. Poprawiono również bezczynne odświeżanie
klawiatury oraz konkretne usterki zasobów Bluetooth i framebufferu.

Wydanie `r34-alpha5-20261015` dodaje przypisywanie odczytu czasu oraz wybór
komunikatów blokowania i odblokowania. `ACCESSIBILITY-SCREEN-PL.md` opisuje
opcje i istniejący wspólny czas automatycznej blokady/podświetlenia.
To eksperymentalna paczka do testów
na odtwarzaczu, a nie potwierdzenie działania wszystkich funkcji na sprzęcie.
Nie znamy wersji zainstalowanej na Twoim egzemplarzu: nie gwarantujemy dowolnego
przejścia między firmware ani działania usług Bluetooth i USB.
Udana kompilacja MIPS lub symulator Windows nie oznaczają testu sprzętowego.
Pula rdzenia pozostaje na poziomie 15 MiB; nominalne 64 MB urządzenia nie
oznacza 64 MB do dyspozycji Rockboxa. Silnik korzysta z dotychczasowej puli
1,5 MiB i adaptera Unicode/plików, bez wymagania locale UTF-8 ani libstdc++.

Sterowanie przyciskami i klawisze Windows opisuje `HIBY-R1-CONTROLS-PL.md`,
a granice instalacji i usuwania — `HIBY-R1-INSTALL-PL.md`. Wydanie Windows
trafia do `D:\Rockbox\rockbox\installfiles\simwindows-hibyr1`; **nie** jest
plikiem do wgrywania na odtwarzacz. Wydania Sans pozostają osobno.

## Aktualizacja po błędzie Cannot open ctl

Pierwszy test sprzętowy alpha1 zakończył się paniką `Cannot open ctl` przy
otwieraniu miksera, przed mową. Dołączona ALSA 1.0.26 nie przyjmuje pola `hint`
w konfiguracji sprzętowego miksera używanej przez nowszy system HiBy. Alpha2
otwiera mikser karty 0 przez własną, minimalną konfigurację w pamięci, bez
zmian w systemie producenta ani wyłączania regulacji głośności. W razie dalszego
błędu komunikat podaje urządzenie, kod i opis ALSA. To poprawka do ponownego
testu, nie potwierdzenie działania całego urządzenia.

Jeżeli loader już uruchamia Rockboxa, **nie flashuj ponownie firmware**:
wyłącz urządzenie i rozpakuj całą nową paczkę `.rockbox` do katalogu głównego
karty, zastępując pasujące pliki programu. Zachowaj wcześniej swoje ustawienia
i zakładki; paczka ma czyste domyślne ustawienia, nie zawiera Twojego profilu.
Do tej poprawki nie kopiuj `r1.upt` na kartę i nie wykonuj downgrade do 1.6.

Jeżeli chcesz sprawdzać **na czystych ustawieniach**, samo nadpisanie plików nie
wystarcza: mogą pozostać `config.cfg.new` i prywatne ustawienia dostępności.
Przy wyłączonym Rockboksie zachowaj cały dotychczasowy folder `.rockbox`, np.
zmieniając jego nazwę na nieużywaną `.rockbox-backup`, a następnie rozpakuj nową
paczkę tak, aby powstał nowy `.rockbox`. Nie łącz folderów i nie przywracaj starego
profilu do próby na czysto. Zachowaj kopię zakładek i własnych plików; niczego
nie usuwaj ani nie zmieniaj na zamontowanej karcie, gdy Rockbox z niej korzysta.

## Pierwsza instalacja i autostart

1. Tylko dla zwykłego **HiBy R1**, nie R1 MIDI ani R3. Zabezpiecz kartę i uzyskaj
   właściwy oryginalny firmware do powrotu przed pierwszym flashowaniem.
2. Rozpakuj naszą paczkę `rockbox-hibyr1-espeak-r34-alpha12-20261019-hardware-test.zip`
   do katalogu głównego karty: bezpośrednio ma powstać `.rockbox/rockbox.r1`.
3. Osobno rozpakuj `installfiles/fw-rockbox/hibyr1_1.8b2_bahusoid_rb_26.09.17.zip`.
   Umieść jego `r1.upt` w katalogu głównym tej samej karty. To zmodyfikowany
   system **1.8b2**, a nie aktualizacja naszej syntezy ani zachowanie obecnej wersji.
4. Po sprawdzeniu zgodności aktualizacji uruchom w fabrycznym systemie
   **System → Firmware update → TF/SD-card update**. Nie wyłączaj urządzenia
   ani nie wyjmuj karty w trakcie zapisu. Ekran aktualizacji nie jest udźwiękowiony
   przez nasz eSpeak; może być potrzebna pomoc przy pierwszej instalacji.
5. Po restarcie nie trzeba wybierać systemu. Paczka ma świeży, binarny wybór
   Rockboxa w `.rockbox/rb_bl_mode.txt`; sprawdzony loader odlicza około jednej
   sekundy i uruchamia aplikację. To czas selektora, nie cały czas startu do mowy.
   Ekran wyboru może krótko mignąć. Nie modyfikujemy obrazu UPT, żeby go ukryć.
6. Po udanym zapisie usuń `r1.upt` z karty, zachowując oryginalny pobrany ZIP
   na komputerze. Późniejsze aktualizacje naszej `.rockbox` zwykle nie wymagają
   ponownego flashowania UPT. Nie nakładaj pluginów innego buildu.

Powrót do HiBy Player, odzyskiwanie i dokładne sumy: `HIBY-R1-INSTALL-PL.md`.
Paczka sprzętowa jest w `installfiles/hibyr1`; Windows EXE zostaje na komputerze.

## Symulator Windows i źródła

Wydanie Windows zawiera także `SOURCE-hibyr1-windows-espeak-r34-alpha15-20261019.tar.gz`
z odpowiadającymi mu poprawkami Rockboxa, źródłami i danymi dostarczonego eSpeaka
oraz narzędziami budowania. Przy dalszym udostępnianiu zachowaj je razem
z programem; to źródła, nie obraz dla odtwarzacza.

Opcjonalny parametr `--debugaudio` zapisuje w symulatorze dodatkowy plik
`audiodebug.raw` obok programu; bez tego parametru ślad nie powstaje.
Zawiera odtwarzaną muzykę i mowę, więc udostępniaj go świadomie. Ślad pomija
bezczynne fragmenty wyjścia i nie ma tych samych pozycji bajtowych co pełne
wyjście sterownika SDL disk. Nie jest nagraniem z fizycznego odtwarzacza.

eSpeakiem sterują „Włącz syntezę mowy” oraz „Głośność mowy”. „Używaj plików
głosowych do czytania interfejsu”, „Głośność plików głosowych” oraz tryby
czytania nazw katalogów i plików dotyczą wyłącznie nagranej mowy. Ich wyłączenie
ani ustawienie głośności na zero nie wycisza syntezy. Prototyp Windows korzysta
z tej samej wspólnej zasady co wydania Sans.

Nie mieszaj tego wydania z wtyczkami/kodekami Sans, oficjalnego Rockboxa ani
Bahusoida. ABI tych źródeł rozwojowych to `0xe006`, a identyfikator R1 — 124. Aktualizacja
wymaga całej zgodnej paczki na karcie, nie tylko pliku aplikacji.

Wspólny rdzeń implementuje teraz gesty semantyczne i eksplorację bez aktywacji
dla standardowych list oraz czytnika tekstu. Edytor gestów obejmuje opcję
„Nieprzypisany”, osobną atomowo zapisywaną konfigurację i próbę z potwierdzeniem
lub cofnięciem po dwudziestu sekundach. Przypisania, odzyskiwanie sterowania
i ograniczenia wtyczek opisuje `ACCESSIBILITY-TOUCH-PL.md`. Nieprzypisane gesty
nie wykonują przypisanej akcji. Nowy edytor przycisków, niezależny od Key Remap,
opisuje `ACCESSIBILITY-BUTTONS-PL.md`: pojedyncze, dwukrotne i trzykrotne
naciśnięcie oraz przytrzymanie z jednym wspólnym czasem. Nieprzypisane
przyciski przywracają własną funkcję, w szczególności regulację głośności;
osobna opcja zachowuje domyślne sterowanie Rockboxa. To nie jest ACTION_NONE.
Testy hosta nie potwierdzają progów ani wygody dotyku na fizycznym ekranie.

Obsługa Bluetooth HiBy pozostaje oddzielona od silnika mowy. Zgodność usług
i ALSA oraz zachowanie słuchawek wymagają testów sprzętowych. Windows jawnie
zgłasza niedostępność Bluetooth zamiast pozorować udane połączenie. Mowa
w SDL nie potwierdza działania Bluetooth na odtwarzaczu.

Natywne R1 domyślnie używa USB tylko do ładowania. Nowa blokada odmawia
zapisywalnego eksportu karty, dopóki nie potwierdzimy wyłącznej kontroli
nad automonterem producenta oraz bezpiecznego odmontowania i przywracania.
Odziedziczony kod eksportował kartę nadal zamontowaną w Linuksie; nie jest
bezpieczną alternatywą. Odmowa nie oznacza działającego transferu USB.
Szczegóły i granice testów opisuje `ESPEAK-HIBY-USB-PL.md`.
Aktualizacja plikowa przez ADB to osobna możliwa droga, nie gotowy
przetestowany aktualizator. Instrukcja instalacji nadal ma warunki wstępne.
Pierwsza instalacja wymaga firmware z loaderem; po jego zainstalowaniu nasz
plik wyboru wystarcza do autostartu. Nie trzeba ponownie zmieniać loadera
ani UPT, żeby uniknąć ręcznego wyboru OS. Nie obiecujemy zniknięcia selektora.

Nie dodajemy rejestratora do sprzętu bez obsługiwanej ścieżki nagrywania.
Instalacja wymaga zgodnego loadera i planu powrotu do oryginalnego systemu;
nasze narzędzia budowania nie flashują loadera ani aktualizacji UPT.

Menu Dostępność zaczyna się od Ustawień Talkbox. Podmenu Ustawienia eSpeak zawiera
wyłącznie parametry silnika; czytanie tekstu, przeglądanie dotykowe, pisanie
i ekran są obok niego w Ustawieniach Talkbox. Przyciski fizyczne pozostają
w Systemie. Język głosu „Zgodny
z systemem” śledzi język Rockboxa;
gdy brak odpowiadającego głosu, nadal używa angielskiego.

Ustawienia → Ustawienia ogólne → System → Dźwięki interfejsu zawiera wybór
„Dźwięki interfejsu dla”: dowolną kombinację przycisków, gestów i eksploracji,
łącznie z Brak i Wszystkie (nowe domyślne). Stare zapisane źródła zachowują
znaczenie. Świeży profil używa średniej siły; zapisanej ciszy nie nadpisuje.
Główna siła Wyłącz wycisza wszystkie źródła. Eksploracja klika przy
nowym celu lub kontakcie, nie przy drganiu współrzędnych. Wysokość dźwięku pustych
miejsc można ustawić osobno. Zgłaszanie pustych miejsc w ustawieniach
przeglądania dotykowego ma trzy tryby: tylko dźwięk (domyślnie), dźwięk i mowa,
tylko mowa. W pierwszym trybie wyłączone dźwięki oznaczają ciszę.

Ogólne Ustawienia ekranu dotykowego oraz Ustawienia przycisków fizycznych są
teraz w Systemie. Pierwsze zawierają czułość gestów, odblokowanie dowolnym
przyciskiem i przyciski przy zablokowanym dotyku. Obie opcje blokady domyślnie są
wyłączone. Ustawienia pisania dodają echo znaków/słów, wielkich liter i usuwania.
Nie ma osobnego podmenu skrótu dostępności; bezpośrednie przełączniki usług
przypisuje się przyciskom albo gestom.

Jeśli karta nadal ma diagnostyczny launcher audio alpha8, przed wymianą programu
przywróć zwykły program dopasowanym narzędziem alpha8. Nie używaj nowego manifestu
do przywracania starszego programu. Sama kompilacja tego wydania nie zmienia
karty; działający już loader nie wymaga kolejnego flashowania UPT.

## Pisanie, kurtyna i ta aktualizacja

W Dostępność → Ustawienia Talkbox są **Ustawienia pisania**, a w podmenu
**Ustawienia ekranu** — **Kurtyna ekranu**.
`ACCESSIBILITY-TYPING-PL.md` opisuje wpisywanie po oderwaniu palca, dwukliku
i nawigację strzałkami; `ACCESSIBILITY-CURTAIN-PL.md` opisuje tymczasowy czarny
ekran i odzyskiwanie obrazu. W wyborze akcji są jednoznaczne **Strzałka w górę,
w dół, w lewo, w prawo**, oddzielnie od nazw gestów. Kurtyna po restarcie jest
wyłączona.

Aktualizacja zachowuje prywatną konfigurację miksera z alpha2, dodaje kontrolę
błędów alokacji miksera i utwardzenie stanu, timeoutów oraz odzyskiwania Bluetooth.
Korzysta z nowych dostarczonych polskich danych słownika. Nie wymaga kolejnej
aktualizacji `r1.upt`. Test sprzętowy nadal jest potrzebny; Windows nie udaje
działającego fizycznego adaptera Bluetooth tego portu.

`HIBY-R1-NETWORK-EMULATION-PL.md` oddziela zbadane możliwości NAS/Wi-Fi
i emulatorów od gotowych funkcji. Paczka nie dodaje klienta NAS, emulatorów
GBA/DS/3DS/Wii ani automatycznej obsługi udźwiękawiających skryptów Pokémon.
