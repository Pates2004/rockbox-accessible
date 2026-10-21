# Bluetooth HiBy i wspólny tor dźwięku mowy

## Zasady współbieżności dla autorów zmian

Każde przyjęte żądanie zachowuje własny identyfikator, generację ręcznej decyzji
i epokę uprawnień aż do zakończenia. Automat sprawdza wcześniej zapamiętany stan
przed skasowaniem anulowania. Końcowy obraz kontrolera i skrzynki usługi są
publikowane wspólnie, przy kolejności blokad kontroler, potem usługa; odbiorca
korzysta ze spójnego odczytu. Ustawienia zapisuje ten sam worker w kolejności
zatwierdzonych operacji, już poza tymi blokadami. Błąd wyjścia dźwięku pozostaje
widoczny, lecz nie odbiera pozwolenia na używanie radia o potwierdzonym zasilaniu.

Interfejs `audio_pause_guarded`, dostępny tylko dla natywnego R1 z TTS, otrzymuje
generację odtwarzania zapamiętaną przy zaobserwowaniu utraty połączenia.
Nie wolno odczytywać jej dopiero tuż przed późniejszym wywołaniem. Ręczne start,
stop, pauza i wznowienie zmieniają generację. Nadawcą musi być zarejestrowany
wątek aplikacji, nie odbiorczy wątek audio, obcy pthread, ISR ani inny rdzeń.
Nadawca nie może trzymać zasobu potrzebnego do zakończenia synchronicznej kolejki.
Żądanie na stosie pozostaje ważne do odpowiedzi albo odrzucenia komunikatu.
Inne targety nie otrzymują nowego zdarzenia, licznika ani interfejsu.

Callback `begin` nie może oddawać wykonania, uruchamiać mowy, audio ani kolejek
czy zajmować blokad kontrolera lub łączności. Wynik fałszywy nie zostawia blokady;
prawdziwy utrzymuje krótką blokadę usługi wyłącznie przez skalarną zmianę stanu
odtwarzania. `end` zwalnia ją przed IAP, wyciszaniem i operacjami PCM.
Nowsza decyzja użytkownika, cofnięte pozwolenie albo polecenie odtwarzania
odrzucają nieaktualne żądanie wstrzymania.

Kontrola wyjścia PCM jest obrazem stanu pod jego własną blokadą, nie wspólną
transakcją z blokadą usługi i zmianą odtwarzania. Bezpośrednia zmiana wyjścia
między odczytem a zatwierdzeniem nie jest wykluczona. Nie gwarantuje to braku
choćby jednej próbki na kablu ani fizycznego przełączenia. Podobnie uruchomiony
proces monitora nie potwierdza gotowej subskrypcji ani dostarczenia zdarzeń.

## Wyjście dźwięku i ponowne łączenie

Udane ręczne **Połącz** przełącza cały miks Rockboxa, czyli muzykę i Talkbox,
na wybrane słuchawki Bluetooth, nawet gdy jack pozostaje wpięty. Jest jedno
wybrane wyjście PCM, nie osobne wyjścia muzyki i mowy. Samo połączenie BlueZ
nie potwierdza gotowości właściwego wyjścia BlueALSA ani przełączenia Rockboxa.
Nieudane przełączenie zachowuje poprzednie wyjście.

Automatyczne odzyskiwanie PCM zapamiętuje generację wyboru wraz z wyjściem
i sprawdza ją pod blokadami stanu i przełączania przed otwarciem wyjścia.
Nieaktualna próba nie nadpisze nowszego przyjętego wyboru użytkownika, również
przy powrocie na kabel po nieudanym odzyskiwaniu Bluetooth. To zabezpiecza
wybór wyjścia; nie jest funkcją automatycznego łączenia słuchawek.

W ustawieniach Bluetooth automatyczne łączenie ma opcje: Wyłączone, Po włączeniu
Bluetooth oraz Po włączeniu Bluetooth i po utracie połączenia. Domyślna jest
ostatnia opcja; samo radio nadal jest domyślnie wyłączone. Zapamiętywane jest
wyłącznie urządzenie po udanym ręcznym połączeniu. Automat wymaga potwierdzenia
przez BlueZ, że to konkretne urządzenie nadal jest sparowane i zaufane; nie
paruje, nie nadaje zaufania, nie skanuje i nie włącza radia. Połączenie zainicjowane
przez usługę producenta nie jest automatycznie przejmowane jako inne wyjście.

Limit czasu ponawiania wynosi 30, 60, 120 lub 300 sekund, domyślnie 120. Następuje
najwyżej osiem prób, z rosnącymi odstępami i limitem 15 sekund na pojedynczą
operację automatyczną, dodatkowo ograniczonym końcem całego okna. Nieudana próba
nie rozpoczyna okna od nowa. Rozłącz, Zapomnij, anulowanie, tryb samolotowy oraz
wyłączenie radia lub odtwarzacza zatrzymują odzyskiwanie. Po ręcznym rozłączeniu
potrzebne jest świadome połączenie albo wyłączenie i ponowne włączenie Bluetooth.

Po niespodziewanej utracie połączenia lub wyjścia domyślnie następuje wstrzymanie
muzyki i powrót wspólnego dźwięku na kabel, gdzie może mówić Talkbox. Alternatywa
to kontynuowanie na wyjściu przewodowym. Ponowne połączenie nie wznawia samo
wstrzymanej muzyki. Krótki bufor może trafić na kabel przed reakcją wątku polityki;
nie jest to gwarancja, że nie wydostanie się ani jedna próbka. Sam powrót na kabel
też może się nie udać. Przełączanie i ponowne łączenie wymagają prób na fizycznym R1.

## Stan weryfikacji

Kontroler Bluetooth HiBy R1 i adapter poleceń producenta są zaimplementowane,
ale natywny Bluetooth R1 pozostaje **diagnostyczny, bez potwierdzenia na sprzęcie**.
Ta wersja nie przeszła jeszcze fizycznej akceptacji słuchawek i przełączania wyjść.
Testy hosta uruchamiają rzeczywisty adapter C z przygotowanymi
programami poleceń oraz rzeczywisty worker z kontrolowanym backendem. Nie dowodzą
działania radia, słuchawek, dźwięku ani czasu pracy baterii. Symulator Windows
jednoznacznie zgłasza niedostępność Bluetooth; nie udaje parowania ani nie używa
stosu Bluetooth komputera.

Przełączanie PCM jest osobną bramką weryfikacji. Samo połączenie BlueZ nie oznacza
sukcesu: adapter sprawdza stan połączenia, właściwe wyjście źródłowe BlueALSA i
przełączenie wspólnego PCM. Wersja R1/eSpeak wybiera osobny, izolowany sterownik
PCM; inne targety hosted zachowują dotychczasowy sterownik. Testy hosta nie są
potwierdzeniem pluginu producenta ani sprzętu. Samo `SND_PCM_NONBLOCK` nie
gwarantuje limitu czasu otwierania, konfiguracji i zamykania pluginu.

## Sterowanie i mowa

Menu w Ustawienia → Łączność → Bluetooth zawiera jeden przełącznik zasilania,
Sparowane urządzenia, Sparuj nowe urządzenie, Rozłącz, Stan, Ustawienia Bluetooth
oraz Połącz ostatnio wybrane urządzenie. Usunięcie parowania wymaga potwierdzenia;
domyślnie wybrane jest Zachowaj sparowane urządzenie. Ustawienia obejmują
ponawianie, zachowanie po utracie połączenia, opcjonalne komunikaty o zmianach
i zapamiętany adres. Są zapisywane osobno w `.rockbox/bluetooth.cfg`, bez zmiany
wspólnych ustawień udostępnianych wtyczkom. Lista sparowanych
jest odświeżana osobno; parowanie nowego urządzenia pokazuje niesparowane wyniki
skanowania. Po wybraniu urządzenia dostępne są odpowiednie operacje połączenia
i usunięcia. Skanowanie, łączenie i odświeżanie nie włączają radia automatycznie.
Czytane są nazwy, stan sparowania, wyniki operacji, anulowanie i błędy, przez ten
sam mechanizm lokalizowanej mowy co reszta Rockboxa. Wyszukiwanie ma limit czasu;
Wstecz anuluje operację. Menu odzyskuje sterowanie, podczas gdy worker kończy
anulowanie; do tego czasu nie przyjmuje drugiej operacji.

Polityka startowa po inicjalizacji audio jawnie stosuje zapamiętany stan radia,
domyślnie wyłączony. Tryb samolotowy wyłącza oba radia; po jego wyłączeniu wracają
wcześniejsze preferencje. Zapis preferencji nie dowodzi wykonania operacji:
[opis żądanego i rzeczywistego stanu](HIBY-R1-CONNECTIVITY-PL.md).
Wyłączenie wymaga potwierdzenia stanu wyłączonego
kontrolera przez BlueZ. Parowanie korzysta z agenta obecnego w firmware.
Interaktywne wpisywanie PIN-u lub potwierdzanie kodu nie jest zaimplementowane;
takie żądanie zgłasza błąd, a nie pozorny sukces. Parowanie i zaufanie zapisane
wcześniej przez BlueZ mogą pozostać po anulowaniu lub późniejszym błędzie
połączenia/PCM. Sprawdź listę; Zapomnij usuwa zapisane urządzenie. Łączenie
drugich słuchawek może wpływać na pierwsze przez usługi producenta; płynne
przełączanie słuchawek nie jest potwierdzone.

Stan odczytuje z BlueZ zasilanie i połączenie również wtedy, gdy poprzednio
zapamiętany stan radia był wyłączony. Potwierdzone zewnętrzne wyłączenie radia
lub rozłączenie słuchawek powoduje próbę powrotu na kabel przed usunięciem
zapisu połączenia. Błąd lub anulowanie przywracania wyjścia zgłasza właściwy
komunikat i zachowuje zapis połączenia do ponownej próby. Niepełna lub nieudana
odpowiedź BlueZ zgłasza błąd; nie stanowi potwierdzenia rozłączenia. Odświeżanie
jest jawne, bez okresowego odpytywania radia w tle. Stała, kontrolowana subskrypcja
`dbus-monitor` dostarcza wskazówek o zmianach. Worker potwierdza zasilanie i stan
wybranego urządzenia przed reakcją; samo zdarzenie lub błąd monitora nie dowodzi
rozłączenia. Próby ponownego uruchomienia monitora są ograniczone. Stan informuje,
gdy monitorowanie jest niedostępne. Lekkie sprawdzanie pamięci i potoku nie
uruchamia stale skanowania ani listowania wszystkich sparowanych urządzeń.
Automatyczne komunikaty uwzględniają własne ustawienie oraz opcję informowania
o dynamicznych zmianach; jawne błędy operacji nadal są czytane.

Rozłącz, wyłączenie przełącznikiem i Zapomnij dla aktywnego urządzenia najpierw próbują przywrócić
wyjście przewodowe. Brak `bluealsa-cli` nie blokuje tych operacji BlueZ. Przy
braku samego `bluetoothctl` nadal następuje próba powrotu na kabel, ale operacja
zgłasza niedostępność i zachowuje zapis połączenia radiowego, ponieważ nie można
było potwierdzić rozłączenia.

Zaimplementowany tor: muzyka + eSpeak + pliki głosowe → dotychczasowy mikser
Rockboxa z przyciszaniem muzyki → jeden helper PCM → ALSA → słuchawki przewodowe
lub Bluetooth. Synteza nie otrzymuje osobnego wyjścia. Główna głośność Bluetooth
programowo ścisza oba kanały zmiksowanego sygnału; sam mikser analogowego DAC-a
nie może jej regulować. Na tym etapie nie obiecujemy wyboru kodeka,
mikrofonu, nagrywania Bluetooth, przycisków słuchawek, multipoint ani zgodności
głośności absolutnej.

## Izolowane PCM i zamykanie

Wszystkie wywołania PCM ALSA wykonuje helper uruchamiany przez
`execve("/proc/self/exe", ...)`, nie interfejs, callback miksera ani potomny proces
przed `exec` z aplikacji wielowątkowej. Wczesne wejście
`--hiby-pcm-helper <wyjście> <częstotliwość> 3` wraca przed inicjalizacją Rockboxa
i TTS. Nie inicjuje areny rdzenia ani silnika mowy. Nadal mapuje ten sam program
i biblioteki; RSS helpera i całkowity dostępny RAM wymagają pomiaru na R1.

Ograniczone gniazdo Unix `SOCK_SEQPACKET` przenosi najwyżej jedną paczkę 1024
ramek stereo oczekującą potwierdzenia. Częściowy zapis ALSA zachowuje resztę danych.
Mikser pobiera następny bufor dopiero po potwierdzeniu; oznacza ono przyjęcie
przez ALSA, nie dokładny moment dźwięku w słuchawkach. Zegar audio i kursora
nadal podlega opóźnieniu buforów sprzętu i Bluetooth. Naturalny koniec odtwarzania
opróżnia końcówkę w helperze; jawne Stop przerywa nieblokujące opróżnianie i
odrzuca kolejkę. Zawieszone wywołanie pluginu nie trzyma blokady interfejsu.

Otwarcie wyjścia ma limit dwóch sekund i obsługuje anulowanie. Zmiana następuje
dopiero po potwierdzeniu konfiguracji ALSA na żądanej częstotliwości. Błąd lub
anulowanie zachowuje poprzednie wyjście. Brak postępu zapisu lub sygnału życia
przez 1,5 sekundy wycofuje helper i próbuje wrócić na kabel, bez panic. Sygnały
życia nie ukrywają zawieszonego zapisu. Helper i rodzic w bezczynności czekają
do 250 ms zamiast stale szybkiego odpytywania audio. Ani to rozwiązanie, ani
obecność Linuksa nie dowodzi pomijalnego narzutu na baterię.

Powtarzające się błędy otwierania wyjścia przewodowego mają monotoniczne,
wykładnicze opóźnienie ponawiania: od 250 ms do maksymalnie czterech sekund.
Udane otwarcie, jawne żądanie wyjścia, zmiana częstotliwości lub nowe odtwarzanie
zeruje opóźnienie; automatyczne ponawianie nie. Błąd wysłania DATA zachowuje
niewysłany fragment i obsługuje odzyskiwanie zgodnie ze wspólnym stanem PCM i
miksera, zamiast zatrzymywać tylko sterownik, gdy rdzeń nadal zgłasza odtwarzanie.
Dane już przyjęte przez ALSA nadal mogą przepaść przy awarii wyjścia; nie
obiecujemy bezstratnego przełączania Bluetooth.

Wycofanie zamyka IPC, wysyła SIGKILL i odbiera procesy bez blokowania. Obsługa
bezczynności wraca do zakończonych, kontrolowanych procesów; zamknięcie ma
ograniczone okno końcowego odbioru, zamiast zakładać sukces pojedynczego WNOHANG.
Czekanie na warunki korzysta z zegara monotonicznego, tak jak limity odzyskiwania
i sygnałów życia.
Stały budżet ośmiu procesów zapobiega mnożeniu helperów, jeśli wywołanie pluginu
lub jądra nie daje się szybko zakończyć. SIGKILL nie gwarantuje natychmiastowego
zakończenia procesu w nieprzerywalnym wejściu/wyjściu jądra. Wyczerpanie budżetu
jest błędem, nie powodem tworzenia kolejnych procesów. Odłączenie słuchawek,
zachowanie jądra i pobór energii pozostają do sprawdzenia na sprzęcie. Powrót
na kabel też może się nie udać; nie jest gwarancją sprzętową.

Kolejność zamknięcia: ostatnia mowa i `voice_wait` → zatrzymanie wątku polityki
Bluetooth i monitora → anulowanie i zakończenie workerów łączności i Bluetooth
→ `hiby_pcm_shutdown` → zamknięcie kodeka/sprzętu. Nie wywołuj
zamknięcia PCM pod jego blokadą ani z callbacku. Radio nadal włącza się dopiero
na żądanie. Testy helpera nie dowodzą zgodności ABI ani bezpieczeństwa USB.

## Wymagania uruchomieniowe

Adapter uruchamia bez powłoki programy o dokładnych ścieżkach:

- `/usr/bin/bluetoothctl`: kontroler BlueZ, wyszukiwanie, parowanie i łączenie.
- `/usr/bin/bluealsa-cli`: sprawdzanie właściwego wyjścia źródłowego A2DP.
- `/usr/bin/bt_resume`: awaryjne uruchomienie usług producenta przy błędzie włączania.
- `/usr/bin/dbus-monitor`: pasywne wskazówki o zmianach BlueZ/BlueALSA, bez skanowania.
- Zgodne, działające usługi BlueZ i BlueALSA oraz plugin PCM ALSA `bluealsa`, jego
  konfiguracja i biblioteki zgodne ABI z firmware urządzenia.

Wyjście lokalne: `plughw:0,0`. Bluetooth:
`bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp`, z wyjściem
`/org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dpsrc/sink`. Adres ma dokładnie sześć
oktetów szesnastkowych. Nazwy i listy mają limity i są oczyszczane; nie trafiają
do składanych poleceń powłoki. Polecenia mają limit czasu i danych wyjściowych,
anulowanie oraz odbiór zakończonych procesów. Brak narzędzi, nieobsługiwane
polecenia, niepotwierdzone parowanie/połączenie i brak wyjścia audio są błędami.

Sprawdzone obrazy fabrycznego 1.6 i zmodyfikowanego 1.8b2 zawierają znaczniki
BlueZ 5.54, BlueALSA 4.1.1 i programy monitorujące. Odczyt plików obrazu nie
potwierdza uruchomionego firmware, uprawnień D-Bus, dostarczania zdarzeń ani
zgodności kodeków na konkretnym odtwarzaczu. Biblioteka ALSA z kompilacji nie dowodzi zgodności bibliotek
ani obecności pluginu na playerze. Manifest wcześniejszej diagnostycznej paczki
R1 opisuje pochodzenie bibliotek użytych do linkowania, ale paczka nie zawiera
plików `.so` i nie instaluje usług/pluginu Bluetooth. Nie kopiuj przypadkowego
komputerowego zestawu GLib/DBus na odtwarzacz.

Sprawdzony fork wykorzystuje też opcjonalne, własnościowe polecenie
`BT:ABSVOL:<adres_z_podkreśleniami> <0..127>` przez `/var/run/sys_server`.
Nie jest to interfejs parowania ani standardowe polecenie BlueZ. Ten adapter go
nie wymaga. Ewentualna integracja wymaga pomiarów i odsunięcia go od wątku
interfejsu i PCM.

## Bezpieczna instalacja i aktualizacje

Istniejącego trybu pamięci masowej USB działającego Rockboxa nie wolno traktować
jako bezpiecznej aktualizacji. Sprawdzony bazowy gadget udostępnia surowe urządzenie
blokowe karty, gdy Linux nadal ma zamontowany system plików. Jednoczesny dostęp
komputera i Linuksa może go uszkodzić. Naprawa i weryfikacja USB są osobną bramką
publikacji.

Loader wydania uruchamia kopię `/tmp/rockbox.r1`, ale zachowuje
`LD_LIBRARY_PATH=/data/mnt/sd_0/.rockbox`. Biblioteki, kodeki, wtyczki i otwarte
pliki mogą nadal korzystać z karty. Kopia programu w RAM-ie nie jest procedurą
odmontowania. Przyszła aktualizacja plikowa przez ADB wymaga sprawdzenia pełnej
paczki, czystego zamknięcia aplikacji, wymiany z przywróceniem po błędzie i testów
awarii. USB fabrycznego systemu po czystym zamknięciu Rockboxa jest alternatywą
wyłącznie po sprawdzeniu zachowania tego firmware. Żadnej z tych metod nie
przedstawiamy jako gotowego aktualizatora. Sprawdzony loader wyłącza Wi-Fi;
nie wykazano aktualizacji przez Wi-Fi.

## Testy

Na hoście POSIX z GCC:

```sh
python3 -B tools/tests/test_hiby_bluetooth.py
python3 -B tools/tests/test_hiby_pcm.py
```

Zestaw kompiluje rzeczywiste źródła z ostrymi ostrzeżeniami i sprawdza błędne
adresy, długie nazwy Unicode, błędy/limity poleceń i żądania PIN-u, zamknięte
potoki, anulowanie grup procesów potomnych, limity list, serializację/zamykanie
workera, jawną niedostępność w symulatorze oraz AddressSanitizer i
UndefinedBehaviorSanitizer. Dowody trafiają do centralnego Workspace, nie do
źródeł. Testy PCM uruchamiają rzeczywisty helper z kontrolowanymi błędami ALSA,
prawdziwym ALSA `null` hosta, kompilacją MIPS i ASan/UBSan. Niezmienione funkcje
PCM/miksera wyodrębnione ze źródeł sprawdzają jednoczesny kanał muzyki i mowy
oraz poziomy przyciszania przez helper. Nie jest to próba silnika eSpeak, DSP
ani słuchawek. Sprawdzane są częściowe zapisy, kolejność potwierdzeń, końcówka
i Stop, zawieszenia otwierania/konfiguracji/zapisu/opróżniania, anulowanie,
śmierć helpera, ograniczony odbiór procesów, zmiany wyjść/częstotliwości,
zamknięte standardowe deskryptory i guardy targetów/wczesnego wejścia.
Regresja rzeczywistego rdzenia wymusza błąd wysłania DATA po kontroli odbioru i
sprawdza komplet zachowanych próbek, powrót na kabel oraz następne odtworzenie
muzyki i mowy. Osobny przypadek sprawdza chwilowe zapełnienie wysyłania. Test
trwałego błędu lokalnego wyjścia liczy uruchomienia podczas odtwarzania i
sprawdza ograniczone ponawianie oraz reset przy jawnym wyborze wyjścia,
częstotliwości i odtwarzania. To rozszerza testy, nie potwierdza wstecznie
wcześniejszego przebiegu, który nie wykrył tych dwóch usterek.
Testy nie zastępują prób muzyki i mowy przewodowej/Bluetooth, głośności,
wyłączenia słuchawek, blokady, wznawiania, zamykania, ABI, restartu usług i baterii
na fizycznym playerze.

Dodatkowe regresje hosta obejmują równoległe wywołania zamykania oczekujące na
tego samego workera, zewnętrzne zmiany zasilania/połączenia BlueZ, błędy i
anulowanie przywracania wyjścia, brak programów CLI oraz niepełne odpowiedzi o
stanie. Program CLI, który zamknie potok wyjścia i nadal działa, wciąż podlega
limitowi czasu bez aktywnego odpytywania zamkniętego potoku. Pomiar czasu CPU
procesu na hoście nie stanowi pomiaru zużycia baterii R1.

## Źródła

- [Sprawdzony fork bahusoid: Bluetooth i ograniczenia](https://github.com/bahusoid/rockbox/blob/059809d123a5b2d4ff1d65b571e99cf56b35dd51/docs/mods/bluetooth-hiby-x1600.md).
- [Sprawdzone wydanie x1600_hiby_v2](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2).
- [BlueZ Device API i wymagania agenta parowania](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Device.rst).
- [Wymagania pluginu ALSA BlueALSA](https://github.com/arkq/bluez-alsa/blob/master/doc/bluealsa-plugins.7.rst).
- [ALSA: PCM i błędy odłączonego urządzenia](https://www.alsa-project.org/alsa-doc/alsa-lib/pcm.html).

Aktualna dokumentacja upstream wyjaśnia interfejsy, nie potwierdza wersji
zainstalowanych w konkretnym, niesprawdzonym firmware R1.
