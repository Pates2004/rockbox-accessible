# HiBy R1: wykonalność usług sieciowych, strumieniowania z NAS i emulacji

Aktualizacja badania: **2026-10-19**. [English](HIBY-R1-NETWORK-EMULATION.md).
To analiza wykonalności, a nie ogłoszenie nowych działających funkcji.
W ramach badania nie łączono się z NAS/kontami, nie odtwarzano dźwięku z sieci,
nie uruchamiano emulatorów ani prób na fizycznym R1. Dowody dotyczące obrazu
producenta, emulatorów i gałęzi nadal pochodzą z **2026-10-15**; nowy przegląd
obejmuje kod sieciowy oraz oficjalne wymagania radia/podcastów/bibliotek.

## 1. Co jest dostępne teraz

HiBy podaje X1600E, 64 MB RAM, Linux 4.4.94 oraz Wi-Fi 2,4 GHz, a we własnym
oprogramowaniu DLNA, AirPlay, import przez Wi-Fi i radio internetowe. Nie stają się one
automatycznie funkcjami Rockboxa. Import przez Wi-Fi to również coś innego
niż odtwarzanie zdalnego pliku bez wcześniejszego pobrania całości.
[Specyfikacja HiBy](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/spec/),
[instrukcja producenta](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/).

W zbadanym kodzie R1 odtwarzanie otwiera ścieżkę systemu plików, ustala rozmiar
i przewija plik. Playlisty formatują ścieżki plikowe; wpisanie adresu HTTP albo
SMB do `.m3u8` nie dodaje brakującej obsługi transportu. W tym kodzie R1 nie ma
zaimplementowanej obsługi NAS przez adres, użytkownika i hasło. To ustalenie
dotyczy tego buildu, nie wszystkich urządzeń ani zewnętrznych forków Rockboxa.
[Buforowanie dźwięku](../apps/buffering.c), [playlisty](../apps/playlist.c),
[system plików aplikacji Linux](../firmware/target/hosted/filesystem-unix.c).

**Fakt z obecnych źródeł:** wątek łączności zapisuje żądane ustawienia Wi-Fi/BT
i samolotu, zgłasza odczytany stan radia oraz obsługuje anulowanie. Backend
Linux obsługuje rfkill/interfejsy WLAN i ponowne dołączenie SDIO R1. Nie daje
to wyboru SSID, zarządzania połączeniem/DHCP/DNS ani źródła dźwięku HTTP.
Interfejs UP nie potwierdza Internetu; symulator zgłasza niedostępne radia,
zamiast sterować Wi-Fi komputera.
[Łączność](../apps/hiby_connectivity.c),
[sterowanie WLAN w Linux](../firmware/target/hosted/hiby/power-control-hiby.c).

Zachowany zmodyfikowany obraz producenta 1.8b2 zawiera `cywdhd.ko`, firmware
WLAN, `wpa_supplicant`, `wpa_cli`, skrypty DHCP, biblioteki curl/OpenSSL oraz
układ okna logowania z nazwą SMB. **Tylko dowód statyczny:** nazwy i zasoby
interfejsu nie potwierdzają użytecznego API NAS producenta, wersji SMB, obsługi
TLS ani zgodności z Twoim NAS. Zbadany obraz nie jest pomiarem zainstalowanego
u Ciebie firmware. Skrypty stosują różne ścieżki konfiguracji, a część zatrzymuje
wszystkie procesy supplicanta/DHCP; nie można przejmować ich bez analizy.
Nie uruchamiano usług producenta. [Kontekst kontroli firmware](HIBY-R1-FIRMWARE-PL.md).

## 2. Proponowana obsługa NAS i kolejne usługi sieciowe

**Propozycja NAS:** po wspólnym zarządzaniu Wi-Fi dodać jeden transport NAS
tylko do odczytu. Kolejność usług zaczynającą się od radia opisano dalej.
Profil NAS potrzebuje protokołu, adresu, portu,
udziału/katalogu bazowego, użytkownika i hasła; SMB może dodatkowo wymagać
domeny. Sam IP nie określa usługi. Przykładowe `https://nas.example/music/`
ilustruje adres bazowy HTTPS, a nie sprawdzony serwer. Dane logowania Wi-Fi
oraz NAS są oddzielne.

| Rozwiązanie | Potrzebne prace i kompromis | Ocena dla R1 |
| --- | --- | --- |
| Serwer plików HTTPS | Uwierzytelniony GET; manifest albo API listowania do przeglądania; zakresy bajtów do przewijania | Najlepszy pierwszy prototyp strumieniowania, jeśli NAS ma odpowiednią usługę; dowolna strona WWW nie wystarczy |
| WebDAV przez HTTPS | Ograniczony pamięciowo parser `PROPFIND`, potem GET/zakresy; przestrzenie nazw, kodowanie i błędy poszczególnych wpisów | Praktyczny kandydat do przeglądania przez adres/użytkownika/hasło; trzeba sprawdzić obsługę przez NAS |
| SMB2/SMB3 | Osobny klient listowania udziałów, uwierzytelniania i odczytu od wskazanego offsetu; podpisywanie/szyfrowanie i ponowne połączenia | Wykonalny kierunek badania z małym klientem użytkowym, np. libsmb2; nie zmierzono wielkości portu, ABI ani osiągów |
| Montowanie CIFS albo FUSE | Obsługa w jądrze, uprawnienia, narzędzie i cykl życia poświadczeń, ograniczanie blokującego I/O | Może udostępnić zwykłe ścieżki, lecz sama libfuse w obrazie tego nie dowodzi; obsługa CIFS w jądrze niezweryfikowana |
| Pobranie na microSD, potem odtwarzanie | Pobranie całości, kontrola miejsca/błędów, następnie obecne odtwarzanie lokalne | Prostsza pierwsza funkcja transferu; wyraźnie **nie jest strumieniowaniem** |

Podstawa protokołów: [zakresy HTTP](https://www.rfc-editor.org/rfc/rfc9110.html#section-14),
[WebDAV PROPFIND](https://www.rfc-editor.org/rfc/rfc4918.html#section-9.1),
[przypięte API libsmb2](https://github.com/sahlberg/libsmb2/blob/4cce7691d2281dc9ecf0e5fa4d8d2f4860031df2/README).
Oceny to wnioski inżynierskie, nie wdrożona obsługa.

Prawdziwe strumieniowanie wymaga abstrakcji źródła pod odtwarzaniem i odczytem
metadanych: otwarcia, znanej/nieznanej długości, ograniczonego odczytu,
obsługiwanego przewijania, anulowania i zamknięcia. Wątek roboczy powinien
zasilać ograniczony bufor, nie blokując
mowy ani sterowania. Muszą działać także metadane na końcu pliku i przewijanie
wymagane przez kodeki. Obsługę zakresów HTTP trzeba sprawdzać na odpowiedziach;
serwer może zignorować Range. Należy walidować `206`/`Content-Range`, obsłużyć
`200`/`416` i nie łączyć fragmentów różnych wersji pliku. Radio na żywo
i adaptacyjne HLS wymagają dodatkowej pracy; nie wynikają z obsługi zdalnych
zwykłych plików.
[Odpowiedzi HTTP i walidatory](https://www.rfc-editor.org/rfc/rfc9110.html).

Dla Wi-Fi najpierw trzeba ustalić proces zarządzający radiem, połączeniem
i DHCP w konkretnym firmware, gniazdo/uprawnienia i obsługiwane zabezpieczenia.
Połączenia poleceń/zdarzeń supplicanta są kandydatem, nie zweryfikowaną
integracją R1. Oficjalna strona Doxygen ma oznaczenie 2.5; polecenia sprawdzić
w zainstalowanej wersji. Osobno śledzić połączenie, adres IP, DNS i osiągalność
usługi. Zachować profile producenta i zachowanie zasilania/BT/USB; unikać
konkurujących zarządców, zbiorczego zatrzymywania procesów i skryptów startowych
producenta. Nowe profile aplikacji należą do `.rockbox`, nie do nadpisywanej
konfiguracji producenta.
[Interfejs sterowania supplicanta](https://w1.fi/wpa_supplicant/devel/ctrl_iface_page.html).

### 2.1. Najpierw radio, potem podcasty

**Proponowane etapy; żaden nie jest tu wdrożony ani odebrany:**

| Etap | Najmniejsza użyteczna próba | Dowód wymagany przed ogłoszeniem obsługi |
| --- | --- | --- |
| Wspólna podstawa | Zarządca Wi-Fi zgodny z firmware i jeden ograniczony wątek HTTP/TLS | Ustalenie właścicieli/zabezpieczeń; syntetyczne testy limitów czasu, przekierowań, anulowania i presji pamięci |
| Radio internetowe | Jeden dozwolony bezpośredni adres MP3, potem metadane ICY | Rzeczywiste dekodowanie bez przewijania, sprawna mowa/sterowanie, utrata/ponowne połączenie i ograniczony bufor |
| Podcasty | Pobranie publicznego załącznika RSS na microSD, potem odtwarzanie lokalne; następnie Atom | Błędy kanału/nośnika, sprawdzone wznowienie pobierania i niezależne zakładki odtwarzania |
| Dostępne biblioteki | Bookshare lub DZDN wyłącznie z autoryzowanym API i obsługiwanymi formatami | Uzgodnienia z usługodawcą/logowanie, uprawniony czytelnik, legalne próbki formatów i dostępna nawigacja |

W radiu nieznanej długości i chwilowego braku danych nie wolno traktować jak
rozmiaru/EOF zwykłego pliku. Stop zamyka połączenie; ponowne połączenie wraca
do transmisji na żywo. Bufor pauzy jest skończony, nie zapewnia nieograniczonego
odsłuchu z opóźnieniem ani przewijania. Pobranie całości jest użyteczną próbą
transportu, **nie strumieniowaniem na żywo**. Ograniczyć playlisty pośrednie
i przekierowania; strona WWW stacji nie jest dźwiękiem.

Ramki metadanych ICY oddzielać przed dekodowaniem, walidować `icy-metaint`
i zachowywać stan parsera między częściowymi odczytami; jawnie sprawdzić starsze
`ICY 200 OK`. Oczyścić tytuły i nie zalewać Talkboxa; opcjonalne automatyczne
ogłoszenia wymagają zapamiętywanego przełącznika. Kod MP3/AAC/Ogg można ponownie
wykorzystać, lecz nadal trzeba zbadać założenia rozmiaru/przewijania pliku.
AAC-ADTS, MP4/M4A i Ogg Vorbis/Opus sprawdzać osobno. HLS dodaje odświeżanie
playlist, segmenty/demultipleksację, czas, nieciągłości i opcjonalną ochronę;
odłożyć go do oddzielnego późniejszego etapu.
[Oficjalny opis klienta ICY](https://www.ffmpeg.org/ffmpeg-protocols.html#http),
[rejestracja kodeków](../lib/rbcodec/metadata/metadata.c),
[podstawa HLS](https://www.rfc-editor.org/rfc/rfc8216.html),
[bieżące wskazówki HLS](https://developer.apple.com/streaming/hls-authoring-specification-for-apple-devices.html).

Dla podcastów parsować RSS `enclosure`, później Atom `link rel="enclosure"`,
z ograniczeniami głębokości/bajtów/wpisów XML, bez zewnętrznych encji/zasobów,
stosując trwałe identyfikatory odcinków zamiast tytułów. Użyć `.part` i dziennika
umożliwiającego odtworzenie stanu; sprawdzić liczbę bajtów, miejsce, wyjęcie
karty, limity dużych plików i niepełne zapisy przed atomowym udostępnieniem
gotowego pliku. Wznawiać tylko tę samą reprezentację z silnym walidatorem
i sprawdzonym `206`/`Content-Range`; pełne `200` wymaga rozpoczęcia od nowa,
nigdy dopisania. Obsłużyć `416` oraz zmianę/wygaśnięcie adresu. Pozycja
pobierania i zakładka odtwarzania są niezależne. Prywatne płatne kanały
wymagają osobnej dozwolonej obsługi poświadczeń.
[Specyfikacja RSS](https://www.rssboard.org/rss-specification),
[załączniki Atom](https://www.rfc-editor.org/rfc/rfc4287.html#section-4.2.7),
[walidatory/zakresy HTTP](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5).

### 2.2. Późniejszy dostęp do Bookshare

**Opublikowane fakty:** Bookshare dokumentuje API v2; komunikat dla deweloperów
uzależnia przyjęcie nowych partnerów od trwających usprawnień. Zgoda/klucz
aplikacji wymagają kontaktu z `partner-support@bookshare.org`. Potwierdzona
dysfunkcja utrudniająca czytanie druku i prawa do tytułów w danym kraju są
osobnymi wymaganiami, których klucz API nie zapewnia. Dokumentacja v2,
wersja 13.12.0 z 2026-10-07, udostępnia
odnośniki formatów/pobrania; pakowanie może zwrócić `202`, potem `302` albo `429`.
[Komunikat dla deweloperów](https://apidocs.bookshare.org/),
[API v2](https://apidocs.bookshare.org/reference/index.html),
[uprawnienia](https://www.bookshare.org/help-and-learning-articles/who-qualifies-for-bookshare),
[prawa międzynarodowe](https://www.bookshare.org/global).

Udokumentowano OAuth code/refresh i Bearer; password grant wymaga szczególnej
zgody dla klienta, a implicit nie jest obsługiwany. Na zbadanej stronie
autoryzacji nie znaleziono udokumentowanej obsługi device-code ani PKCE.
**Propozycja:** najpierw
uzgodnić z Bookshare dostępne logowanie R1/aplikacji towarzyszącej i zasady
sekretu klienta natywnego. Zachować informacje prawne, przypisanie użytkownika
i odciski/znaki wodne; polityka DRM opisuje też szyfrowanie. Potwierdzić
dozwoloną obsługę paczek zamiast zakładać nieograniczone pobrania bez DRM.
[Autoryzacja](https://apidocs.bookshare.org/auth/index.html),
[polityka DRM](https://www.bookshare.org/legal/digital-rights-management).

### 2.3. Późniejszy dostęp do DZDN

**Opublikowane fakty:** pomoc zapisu DZDN obejmuje mieszkańców Polski
z dysfunkcją uniemożliwiającą czytanie druku i dokumentem ją potwierdzającym,
następnie aktywację online; §22 ogólnego regulaminu opisuje dostęp zagraniczny
przez upoważnione podmioty. Ogłoszenie Playera Android z 2026-10-07 i §10
polityki prywatności potwierdzają API/token własnej aplikacji, wobec sesyjnych
cookies przeglądarki.
W tym przeglądzie nie znaleziono udokumentowanego publicznego API/SDK ani
autoryzacji dla zewnętrznego klienta. Nie dowodzi to braku API ani możliwości
współpracy.
[Pomoc zapisu](https://dzdn.pl/jak-zapisac-sie-do-biblioteki/),
[ogłoszenie Playera](https://dzdn.pl/aplikacja-mobilna-dzdn-player/),
[prywatność §10](https://dzdn.pl/polityka-prywatnosci-2/).

**Następny krok:** poprosić administratora serwisu o zatwierdzone zasady klienta,
cykl uwierzytelniania, limity, formaty, zasady offline/wygaśnięcia i dozwoloną
obsługę ochrony. §13 ogólnego regulaminu ogranicza kopiowanie, przetwarzanie
i udostępnianie osobom trzecim. Odczyt publicznego portalu/pomocy nie powiódł
się, więc regulamin właściwy dla online i DRM pozostają niezweryfikowane;
nie wnioskować o braku usługi. Zbiory DAISY/Czytak/tekst/MP3 nie potwierdzają
zgodności R1. Nie obchodzić ochrony ani nie uznawać prywatnych interfejsów
aplikacji za publiczną zgodę.
[Regulamin ogólny](https://dzdn.pl/regulamin/),
[oficjalny kontakt](https://dzdn.pl/kontakt/).

### 2.4. Dostępne formaty książek to osobne wymaganie

Bookshare odróżnia tekstowe EPUB/DAISY od generowanych MP3/DAISY Audio.
Odtwarzanie samych ścieżek nie zapewnia nawigacji po rozdziałach/stronach DAISY.
DAISY 2.02 wymaga NCC/SMIL; DAISY 3 używa pakietu/NCX/SMIL i może zawierać
DTBook. EPUB wymaga kontenera/pakietu/spine/XHTML/nawigacji i ewentualnych
media overlays. Obecny czytnik zwykłego tekstu/zakładki Talkbox to użyteczne
części, nie pełny czytnik DAISY/EPUB. **Warunek odbioru:** zachować nawigację
strukturalną, język i pozycje właściwe dla formatu; walidować ograniczone
przetwarzanie archiwów/XML oraz wskazane zasoby i jawnie zgłaszać nieobsługiwaną
ochronę.
[Formaty Bookshare](https://www.bookshare.org/help-and-learning-articles/what-format-are-bookshare-books-available-in),
[DAISY 2.02](https://daisy.org/activities/standards/daisy/daisy-2/daisy-format-2-02-specification/),
[DAISY 3](https://daisy.org/activities/standards/daisy/daisy-3/z39-86-2005-r2012-specifications-for-the-digital-talking-book/),
[EPUB 3.3](https://www.w3.org/TR/epub-33/).

## 3. Poświadczenia i dostępna obsługa

Projektowany interfejs musi zapewnić udźwiękowione po polsku i angielsku
profile serwerów, stan połączenia, przeglądanie, buforowanie, ponawianie,
anulowanie i rozłączanie przez przyciski i gesty. Pola haseł muszą pozostać
maskowane i nie mogą automatycznie odczytywać zawartości. Opcjonalne wskazówki
wymagają zapamiętywanego przełącznika; konieczne nazwy, stany i błędy pozostają.
Te zasady obejmują też listy stacji/odcinków/bibliotek i błędy połączenia.
Klawiaturę, stabilny fokus i rzeczywisty dostęp NVDA w Windows sprawdzać
oddzielnie od udźwiękowienia i symulowanego wejścia R1.

Użyć konta NAS tylko do odczytu. Nie umieszczać sekretów w adresach,
playlistach, logach, argumentach procesów ani błędach. Uwierzytelnianie Basic
wymaga bezpiecznego transportu; Base64 nie szyfruje. W HTTPS sprawdzać zaufanie
do certyfikatu i tożsamość serwera, także przy łączeniu przez IP; uwzględnić
czas urządzenia i świadome zaufanie prywatnemu CA. Nigdy po cichu nie wyłączać
weryfikacji ani nie przekazywać poświadczeń innemu hostowi po przekierowaniu.
[HTTP Basic](https://www.rfc-editor.org/rfc/rfc7617.html),
[weryfikacja certyfikatu](https://curl.se/libcurl/c/CURLOPT_SSL_VERIFYPEER.html),
[weryfikacja nazwy/IP](https://curl.se/libcurl/c/CURLOPT_SSL_VERIFYHOST.html),
[poświadczenia a przekierowania](https://curl.se/libcurl/c/CURLOPT_USERPWD.html).

Ograniczyć liczbę i schematy przekierowań, odrzucać zejście z HTTPS. Zapewnić
jawną aktualizację CA i naprawę nieustawionego zegara; sprawdzić TLS/SNI/szyfry/
entropię urządzenia zamiast polegać na nazwach bibliotek producenta. Usuwać
z diagnostyki tokeny i prywatne adresy kanałów/podpisanych pobrań. Wymogi
logowania/DRM nadal obowiązują, nawet gdy da się uzyskać adres medium.
[Polityka przekierowań](https://curl.se/libcurl/c/CURLOPT_FOLLOWLOCATION.html),
[weryfikacja czasu certyfikatu](https://docs.openssl.org/3.5/man1/openssl-verification-options/).

Domyślnie przechowywać hasło tylko w sesji. Zapis wymaga świadomego wyboru
i uczciwego opisu ochrony na wyjmowanej karcie; klucz szyfrowania obok hasła
nie chroni skutecznie przed odczytem karty. Konfiguracja, pamięć podręczna
i logi należą do własnego katalogu `.rockbox`. Nie zakładać ochrony sekretów
samymi uprawnieniami plików na FAT/exFAT. SMB nie może po cichu przechodzić
na SMB1 ani dostęp gościnny; należy negocjować i testować wymaganą politykę
podpisywania i szyfrowania. Nazwy bibliotek producenta tego nie potwierdzają.

## 4. Pamięć, energia i testy odbiorcze

Lokalne ustawienie CPU wynosi 1008 MHz. Obecny build rezerwuje arenę core
15 MiB z konfigurowanego budżetu 16 MiB i ma bufor wtyczek 2 MiB; nie jest
to dodatkowa wolna pamięć fizyczna. Linux, usługi, kodeki, mowa, bufory ekranu,
TLS i emulator współdzielą fizyczne 64 MB. Nie zwiększać areny do 64 MB
na podstawie samej specyfikacji sprzętu.
[Konfiguracja R1](../firmware/export/config/hibyr1.h),
[pamięć buildu](../tools/configure), [bufor wtyczek](../firmware/export/config/hibylinux.h),
[alokacja areny](../firmware/core_alloc.c).

**Proponowane zabezpieczenia wątku:** oddzielny wątek transferu, stałe bufory,
ograniczone nagłówki/metadane/kolejki, kontrola napełnienia i oczekiwanie bez
aktywnego odpytywania. Nie wykonywać sieciowego I/O pod blokadami UI/sterowania
radiem. Generacje anulowania muszą odrzucać spóźnione odpowiedzi; samolot/USB/
zamknięcie muszą zatrzymać i zamknąć własne transfery przed wyłączeniem radia,
bez ponownego łączenia wbrew woli użytkownika. Sprawdzić ograniczony czas DNS,
połączenia/TLS/bezczynnego odczytu. Libcurl multi jest kandydatem, lecz zwykły
DNS może blokować przy `NOSIGNAL`, a pauza zachowywać bufory biblioteki.
Zacząć od jednego transferu HTTP/1.1 bez automatycznej dekompresji; liczyć
alokacje TLS, DNS/wątków/dekodera i biblioteki, nie tylko bufor dźwięku.
[Interfejs multi](https://curl.se/libcurl/c/libcurl-multi.html),
[ograniczenie DNS](https://curl.se/libcurl/c/CURLOPT_NOSIGNAL.html),
[pamięć przy pauzie](https://curl.se/libcurl/c/curl_easy_pause.html).

Przykłady obliczone, nie pomiary przepustowości: nieskompresowane stereo
44,1 kHz/16 bit to 176 400 B/s (1,4112 Mbit/s), a 192 kHz/24 bit to
1 152 000 B/s (9,216 Mbit/s). Osiem sekund wymaga odpowiednio około 1,35
albo 8,79 MiB bez narzutów. Pliki skompresowane mają inne przepływności.
Większe bufory łagodzą przerwy, ale zajmują małą pamięć; bufor na microSD
dodaje zapisy. Wi-Fi, TLS, mowa i obciążenie CPU mogą skracać pracę baterii;
nie ma tu wyniku czasu działania, temperatury ani współpracy Wi-Fi/BT.

Odbiór musi osobno sprawdzić połączenie/DHCP/DNS, złe hasło, błąd TLS,
przeglądanie, nazwy Unicode, metadane, start/przewijanie/pauzę/wznowienie,
uśpienie NAS, zmianę pliku, utratę Wi-Fi/ponowne połączenie i anulowanie.
Porównać zdekodowany dźwięk z legalnym lokalnym wzorcem, zmierzyć szczyt
RSS/PSS i `MemAvailable`, przerwy oraz baterię przy wyłączonym ekranie,
a także sprawdzić mowę z muzyką i przejścia BT/USB na rzeczywistym R1.
Symulator Windows ani analiza statyczna tego nie potwierdzają. Model NAS,
jego firmware, polityka protokołów/logowania i dokładne firmware R1 nadal
pozostają nieznane.
Rozszerzyć odbiór o zatrzymany DNS/TLS, zły czas/CA, wycieki sekretów przez
przekierowania, podzielone/błędne ICY, szybkie anulowanie/spóźnione odpowiedzi
i przerwane pobieranie podcastu. Limity buforów dobrać dopiero po pomiarze
zapasu procesu/systemu przy dekodowaniu i Talkboxie, opóźnienia sterowania
i niedopełnień bufora. Porównać zmierzoną energię w bezczynności/pracy i baterię
przy znanym stanie radia/ekranu; poradnik nie podaje nowej prognozy CPU,
wolnego RAM, przepustowości ani czasu baterii.

## 5. Granice emulacji

Sam zegar nie porównuje różnych architektur CPU. R1 potrzebuje programu
32-bit MIPS Linux o zgodnym ABI; Windows EXE, Android APK i programy ARM
nie są zamienne. Poniższe wnioski wynikają ze źródeł i wymagań, **nie
z benchmarków na R1**.

| System | Dowód pierwotny | Ocena dla R1 |
| --- | --- | --- |
| GB/GBC | Dołączony [Rockboy](../apps/plugins/rockboy/README) obsługuje GB/GBC | Istniejąca rodzina emulatora; nie GBA i nie dowód dostępności każdej gry |
| GBA | [README gpSP](https://github.com/libretro/gpsp/blob/5819380c2ffb0900219d700a382ee68c464ebb99/README.md) i [build MIPS](https://github.com/libretro/gpsp/blob/5819380c2ffb0900219d700a382ee68c464ebb99/Makefile) mają rekompilator MIPS | Wiarygodny pierwszy eksperyment z frontendem, zgodnym ISA/ABI zmiennoprzecinkowym i sprawdzoną obsługą JIT/cache; szybkość, dźwięk, RAM i bateria nieznane |
| Nintendo DS | [CMake melonDS](https://github.com/melonDS-emu/melonDS/blob/906e9ebb27da8c6a715cd7abab4abfe8a8d29427/CMakeLists.txt) włącza JIT dla x86-64/ARM64; [build DeSmuME](https://github.com/libretro/desmume/blob/95b4d798731caa809125b6c3c11d17cc332ff6ef/desmume/src/frontend/libretro/Makefile.libretro) ma ścieżki JIT x86 i 32-bit ARM, bez backendu MIPS | Brak wykazanej praktycznej drogi z tymi silnikami na R1; eksperyment z interpreterem nie jest wykluczony, ale użyteczna szybkość pozostaje niepotwierdzona i nieobiecana |
| Nintendo 3DS | [Wymagania Azahar](https://github.com/azahar-emu/azahar/blob/68202bc4ff7edf9d7280ec0dcd6572b7cd1ae26e/README.md) określają x86-64/ARM64, 2 GB RAM i odpowiednią grafikę; [RAM starego modelu](https://github.com/azahar-emu/azahar/blob/68202bc4ff7edf9d7280ec0dcd6572b7cd1ae26e/src/core/memory.h) wynosi 128 MiB | Poza realistycznym celem dla R1; uproszczenie menu albo instalacja Lua nie usuwa wymagań CPU, pamięci i grafiki |
| Wii/GameCube | [Build Dolphin](https://github.com/dolphin-emu/dolphin/blob/8d2ad1a662472955497e5bb79d7b9ec6999e1f0d/CMakeLists.txt) zwykle celuje w x86-64/ARM64; [FAQ](https://dolphin-emu.org/docs/faq/) zaleca 2 GB RAM | Poza realistycznym celem dla R1; ogólny wariant bez JIT nie dowodzi istnienia użytecznego portu MIPS/64 MB |

DS potrzebuje też dwóch ekranów, dotyku i większej liczby przycisków;
pionowy ekran sam nie rozwiązuje kosztu emulacji ani dostępnego sterowania.
Wyników handhelda ARM nie można przenieść na CPU MIPS R1. Nie pobierano
ROM-ów ani BIOS-u.

## 6. Lua i dostępne Pokémony to różne wymagania

Lua Rockboxa to **5.1.5 z całkowitym typem `long`**, okrojonymi bibliotekami
i API Rockboxa. Przydaje się do skryptów Rockboxa; nie jest emulatorem GBA
ani API pamięci emulatora wymaganym przez skrypt dostępności. Istniejące
`rb.talk_spell` może dochodzić do naszego TTS, ale osobno uruchomiony emulator
nie dziedziczy automatycznie kolejki mowy i miksowania dźwięku Rockboxa.
[Konfiguracja Lua](../apps/plugins/lua/luaconf.h),
[interfejs Lua](../apps/plugins/lua/rocklib.c), [ścieżka mowy](../apps/talk.c).

Publiczna [rewizja Pokemon Access 3.1.0](https://github.com/nuive/pokemon-access/tree/2deb98f38a4e6674ff60af6f9419be22865f1f39)
nadal wymaga VBA-ReRecording. Potrzebuje odczytu pamięci/rejestrów, hooków
wykonania i zapisu DMA, planowania klatek i wejścia klawiatury PC; także FFI
oraz adapterów mowy, okien i audio z Windows. Identyfikacja GBA odczytuje
**32 MiB do Lua** i tworzy kolejny bufor FFI: same surowe dane osiągają 64 MiB,
jeszcze bez narzutu tabel i emulatora. Trzeba zastąpić to zgodnym strumieniowym
albo natywnym CRC, zachowując dokładną semantykę emulowanego zakresu.
Wykaz danych gier GBA obejmuje angielski/hiszpański; obsługa polskiego nie jest potwierdzona.
[Wymagania](https://github.com/nuive/pokemon-access/blob/2deb98f38a4e6674ff60af6f9419be22865f1f39/readme.md),
[hooki i CRC GBA](https://github.com/nuive/pokemon-access/blob/2deb98f38a4e6674ff60af6f9419be22865f1f39/gba.lua).

**Wniosek projektowy:** gpSP jest lepszym pierwszym kandydatem pod szybkość,
ale w zbadanym kodzie nie ma zgodnego hosta Pokemon Access. mGBA jest lepszym
kandydatem do adaptacji API; zbadany kod ma breakpointy i watchpointy zależne
od włączenia debuggera, wykraczające poza starszą stronę API. Nadal potrzebuje
małego frontendu ze skryptami, zgodnej semantyki buforów/rejestrów/callbacków,
adapterów mowy/efektów, dostępnego sterowania i regresji zapisów/resetów.
Żaden kandydat nie ma odbioru na R1. Najpierw trzeba ustalić konkretną grę,
rewizję/język ROM-u, wersję skryptu i zgodę na redystrybucję.
[Kod skryptów mGBA](https://github.com/mgba-emu/mgba/blob/143adf5aa2a60c6036810b0cd72445e13d74b0e6/src/core/scripting.c),
[opcje kompilacji skryptów](https://github.com/mgba-emu/mgba/blob/143adf5aa2a60c6036810b0cd72445e13d74b0e6/CMakeLists.txt).

## 7. Późniejsze przekazanie zmian Bahusoidowi

Odczyt GitHuba z 2026-10-15 wskazał domyślną gałąź **`Mod25.12.07`**, commit
`059809d123a5b2d4ff1d65b571e99cf56b35dd51`. Istnieje też `Mod26.01.16`;
nazwa nie określa właściwej bazy PR. Tag wydania R1 `x1600_hiby_v2` wskazuje
`94c69704e9cf8bae77240a98a8eb7bd5c576f426`.
[API gałęzi](https://api.github.com/repos/bahusoid/rockbox/branches?per_page=100),
[tag wydania](https://api.github.com/repos/bahusoid/rockbox/git/ref/tags/x1600_hiby_v2).

Przed późniejszą propozycją ponownie ustalić bazę z opiekunem, użyć czystej
gałęzi tematycznej i wybrać tylko przejrzane zmiany. Rozdzielić mowę/dostępność
core, poprawki wejścia/backendu R1, sieć oraz ewentualny samodzielny emulator
na poprawki możliwe do sprawdzenia, z dokumentacją PL/EN i dowodami regresji.
Nie proponować całego zabrudzonego drzewa ani prywatnych obrazów firmware.
Przyjęcie zależy od opiekuna. Tutaj niczego nie commitowano, nie wypychano
i nie zgłaszano.

Licencję rozpatrywać dla każdego składnika. Nasz nowy most ma
GPL-2.0-or-later; dostarczony silnik eSpeak pozostaje GPL-3.0-or-later i nie
można przemianować go na GPLv2. Osobno skontrolować połączoną dystrybucję,
importowane pliki oraz odpowiadające źródła i materiały budowania. gpSP ma
warunki GPL, mGBA MPL-2.0, a libsmb2 LGPL-2.1. Nie licencjonują one firmware
producenta, ROM-ów/BIOS-u ani Pokemon Access: w zbadanym drzewie tego ostatniego
nie znaleziono jawnej licencji.
[Pochodzenie mostu/silnika](../lib/espeak/README.md),
[nota gpSP](https://github.com/libretro/gpsp/blob/5819380c2ffb0900219d700a382ee68c464ebb99/main.h),
[licencja mGBA](https://github.com/mgba-emu/mgba/blob/143adf5aa2a60c6036810b0cd72445e13d74b0e6/LICENSE),
[licencje libsmb2](https://github.com/sahlberg/libsmb2/blob/4cce7691d2281dc9ecf0e5fa4d8d2f4860031df2/COPYING).

[Zasady forka](https://github.com/bahusoid/rockbox/blob/059809d123a5b2d4ff1d65b571e99cf56b35dd51/docs/CONTRIBUTING)
wymagają podania prawdziwego imienia i nazwiska oraz stylu Rockboxa. Oficjalny
upstream używa Gerrita, a [obecna polityka](../docs/CONTRIBUTING) zdecydowanie
odradza kod generowany przez AI i wymaga opisania pochodzenia przy zgłoszeniu.
Ujawnić faktyczny udział narzędzi i zapewnić przegląd człowieka; PR do forka
nie potwierdza przyjęcia upstream ani nie rozstrzyga autorstwa i licencji.

## 8. Co pozostaje ustalić

Przed implementacją ustalić dokładne firmware R1, model NAS, włączony
protokół/port/udział, politykę logowania/TLS i oczekiwane przeglądanie oraz
przewijanie, bez publikowania haseł. Dla dostępnej emulacji najpierw wskazać
konkretną grę/skrypt i potrzebne sterowanie. Dla radia/podcastów uzgodnić
dozwolone adresy źródeł i zachowanie pauzy/offline; biblioteki wymagają ponadto
autoryzacji usługodawcy, zatwierdzonego logowania i obsługiwanych formatów.
Sieć, synteza, zużycie pamięci,
gry i bateria wymagają prób sprzętowych; to badanie nie potwierdza żadnego
z tych wyników działania.
