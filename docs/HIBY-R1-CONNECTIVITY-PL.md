# Łączność HiBy R1

## Sterownik uśpiony przez bootloader

W dostarczonym zmodyfikowanym firmware 1.8b2 bootloader odłącza funkcję Wi-Fi
od sterownika SDIO przed uruchomieniem Rockboxa. Może też uśpić kontroler
Bluetooth. Brak interfejsu WLAN po takim starcie nie oznacza, że usunięto Wi-Fi
z kompilacji. Poprzedni backend nie odróżniał tego stanu, a Bluetooth próbował
odpytywać niedostępny kontroler BlueZ, nawet gdy radio było już zablokowane.

Nowa obsługa rozpoznaje **Sterownik Wi-Fi uśpiony** wyłącznie po potwierdzeniu
znanej konfiguracji urządzenia i sterownika. Odczyt oraz wyłączanie nie budzą
tego sterownika. Dopiero jawne żądanie włączenia może ponownie przypiąć jego
znaną funkcję WLAN, po sprawdzeniu tożsamości; nie przeładowuje całego modułu
Wi-Fi/Bluetooth i nie uruchamia łączenia z zapamiętaną siecią. Nieznana rewizja
lub niespójne dane wymagają diagnostyki, zamiast zgadywania numeru urządzenia.
Nie trzeba z tego powodu ponownie flashować firmware.

Odczytany raport startu R1 identyfikuje obie funkcje SDIO jako `02d0:a9a6`:
pierwsza jest przypięta do `bcmsdh_sdmmc`, druga odłączona. Odczyt dowiązania
modułu był niedostępny; samo to nie dowodzi wbudowania sterownika w jądro ani
braku dowiązania. Wyłącznie dla tego urządzenia backend może rozpoznać uśpienie
bez dowiązania modułu, ale najpierw niezależnie potwierdza rzeczywisty brak
samego dowiązania. Uszkodzone dowiązania, błędy dostępu, niezgodne identyfikatory
i nieoczekiwane sterowniki nadal nie przechodzą kontroli. Inne identyfikatory
urządzeń nadal wymagają pierwotnego sprawdzenia tożsamości modułu.

Potwierdzona, kompletna blokada wpisów typu Bluetooth pozwala zgłosić wyłączenie
bez działającego kontrolera BlueZ. Brak wpisu lub błąd odczytu nie jest dowodem
wyłączenia. Włączanie nadal wymaga rzeczywistego wznowienia i ponownego odczytu
stanu kontrolera; wybrane w menu Włącz nie jest samo w sobie takim dowodem.
Zachowano powrót na przewodowe wyjście i obsługę błędów oraz anulowania.

Operacje sterowania mają ograniczony czas i śledzą własny proces pomocniczy.
Nie zakończony proces nie może zostać uznany za rozstrzygniętą zmianę stanu ani
pozwolić na przedwczesne włączenie Bluetooth. Dotyczy to też niepełnego trybu
samolotowego. Powyższy stan startowy potwierdzono raportem z fizycznego R1.
Ponowne przypięcie WLAN, parowanie i odtwarzanie Bluetooth oraz rzeczywiste
zachowanie zasilania nadal wymagają testu sprzętowego; próby kontrolowane
i symulator go nie zastępują.

Uśpienie sterownika, administracyjne opuszczenie interfejsu lub rfkill nie są
pomiarem elektrycznego odcięcia radia ani zużycia baterii. Poniższe opisy
wyłączenia dotyczą sprawdzonego stanu administracyjnego, nie gwarancji zerowej
emisji RF. Symulator nie wykonuje tych operacji na komputerze.

To wydanie poprawia oba wątki łączności tak, aby respektowały minimalny stos
biblioteki systemowej: 128 KiB na dostarczonym środowisku R1. Poprzednie żądanie
64 KiB mogło zatrzymać tworzenie wątku jeszcze przed obsługą radia. Łączność
pozostaje przeglądalna także po błędzie inicjalizacji, pokazując nieznany stan lub
błąd i pozwalając jawnie ponowić operację, zamiast zamykać całe menu.

Gdy brak znakowego urządzenia rfkill, ograniczona obsługa sysfs odczytuje i
zmienia tylko wpisy WLAN. Nie zapisuje Bluetooth ani sprzętowego stanu blokady.
Katalog danego radia pozostaje otwarty między sprawdzeniem typu a dostępem do
atrybutów, aby ponowne użycie numeru rfkill nie skierowało zapisu do innego radia.

Potwierdzone wyłączenie interfejsu bez odczytu stanu radia jest oznajmiane jako
„Interfejs Wi-Fi wyłączony; stan radia niepotwierdzony”, nie jako potwierdzone
wyłączenie nadajnika. Błąd sterowania ma odrębny komunikat. Zgłoszenie przy starcie
dotyczy wczesnej migawki; bieżący stan sprawdza się w Łączności. Samo rfkill,
sysfs lub opuszczenie interfejsu nie dowodzi elektrycznego odcięcia układu ani
konkretnej oszczędności baterii.

Ustawienia → Łączność grupują Wi-Fi, Bluetooth i tryb samolotowy. Usunięto
dotychczasową pozycję Bluetooth z ustawień ogólnych i stan Wi-Fi przy uruchomieniu
z ustawień systemu. Diagnostyka startowego WLAN pozostaje w System → Debug.
To eksperymentalny interfejs do dostarczonego firmware HiBy Linux, nie nowy
sterownik radia. Symulator Windows nigdy nie steruje radiami komputera.

## Preferencje i odczytany stan

Na czystym profilu oba radia i tryb samolotowy są wyłączone. Plik
`/.rockbox/connectivity.cfg` zapisuje żądane stany i tryb samolotowy osobno od
wspólnej struktury ustawień Rockboxa. Start wymusza żądany stan; polityka
Bluetooth jest stosowana dopiero po inicjalizacji audio. Wczesne wyłączenie WLAN
pozostaje przed wczytaniem preferencji. Początkowe zero w pamięci podręcznej nie
jest dowodem wyłączenia radia przez firmware producenta.

Włączenie trybu samolotowego zleca wyłączenie obu radii i blokuje włączanie,
skanowanie oraz łączenie Bluetooth. Wyłączenie trybu przywraca wcześniejsze
żądane stany Wi-Fi i Bluetooth. Preferencje obu radii są zachowane w czasie
trybu samolotowego, a nie nadpisywane jego tymczasowym wyłączeniem. Błąd operacji,
anulowanie, niepełny odczyt lub błąd zapisu nie są przedstawiane jako pełny
sukces. Po błędzie ponownie sprawdź stan albo ponów operację; nie zakładaj, że
nieudana operacja pozostawiła wszystkie elementy bez zmian.

Operacje mają ograniczony czas i jawny odczyt stanu, bez ciągłego odpytywania
w bezczynności. Anulowanie zleca sprzątanie; następna zmiana zasilania czeka na
zakończenie poprzedniej albo zgłasza zajętość lub przekroczenie czasu.
Spóźnione włączenie nie może ominąć blokady trybu samolotowego. Polecenia
producenta mogą już zmienić trwałe sparowanie, zanim zostaną anulowane.

## Wi-Fi

Początkowo podmenu steruje tylko administracyjnym włączeniem WLAN. Włączenie
odblokowuje wyłącznie wpisy WLAN rfkill i podnosi interfejsy WLAN; wyłączenie
blokuje te wpisy i opuszcza interfejsy, po czym ponownie odczytuje stan.
Nie blokuje Bluetooth ani nie usuwa wspólnego sterownika. Brak wpisów rfkill,
błąd odczytu i blokada sprzętowa nie są uznawane za potwierdzony sukces.

Nie jest to konfiguracja sieci, sprawdzanie hasła, łączenie z punktem dostępowym
ani klient NAS, radia, podcastów lub YouTube. To oddzielne prace. Usługi
producenta również mogą wpływać na interfejsy. W zbadanym firmware callback
rfkill WLAN zapisuje flagę programową; potwierdzona blokada nie dowodzi odcięcia
zasilania układu, całkowitego braku emisji ani konkretnej oszczędności baterii.

## Bluetooth

Jeden wybór włącz/wyłącz zastępuje osobne polecenia włączenia i wyłączenia.
Niżej są sparowane urządzenia, parowanie nowego, rozłączenie i stan. Skanowanie
i łączenie wymagają jawnie włączonego Bluetooth; samo odświeżenie nigdy go
nie włącza. Odczyt zasilania musi być kompletny, nie oparty na starej fladze.

Chwilowa blokada podczas startu, anulowania lub sprzątania jest zgłaszana jako
ograniczenie łączności, a nie dowód włączenia trybu samolotowego. Polecenie
wyłączenia trybu samolotowego dotyczy tylko rzeczywiście włączonego trybu.

Muzyka i mowa dzielą mikser Rockboxa i trasę PCM. Dokument
[Bluetooth i audio](ESPEAK-BLUETOOTH-PL.md) opisuje anulowanie, PIN, trasowanie,
wymagania narzędzi producenta i ograniczenia. Uporządkowanie menu nie dodaje
obietnicy mikrofonu, przycisków słuchawek, wyboru kodeka ani multipoint.

## Stan po starcie i oczekiwanie na Bluetooth

Wyłączone programowo to odczytany stan administracyjny, nie błąd instalacji.
Dostarczony launcher zwykle usypia Bluetooth, a czysty profil żąda wyłączenia.
Wcześniejsze Wyłączone administracyjnie oznaczało ten sam stan, nie trwały
zakaz korzystania z Bluetooth.

Udane, pasywne odświeżenie Łączności nie mówi już Gotowe zamiast pierwszej
pozycji Wi-Fi. Rzeczywiste błędy i niedostępność nadal są zgłaszane. Podczas
zmiany zasilania Bluetooth można przeglądać udźwiękowione menu, gdy ograniczony
czasowo wątek wykonuje operację. Ponowna aktywacja zgłasza zajętość zamiast
rozpoczynać drugą zmianę. Anulowanie żąda sprzątnięcia, bez pomijania blokad
i rozstrzygnięcia poprzedniej operacji. Nawigacja może przerwać komunikat stanu,
ale nie jest odrzucana przez niemą, modalną pętlę oczekiwania.

Zbadana gałąź Broadcom skryptu wznowienia producenta ma jawne oczekiwania
łącznie około dziesięciu sekund, poza startem kontrolera i usług. Zgłoszono
też skuteczne włączenie na R1 po co najmniej kilku sekundach; nie jest to
kontrolowany pomiar ani potwierdzenie parowania i dźwięku. Ta zmiana pomija
skazany na niepowodzenie wstępny rozkaz zasilania tylko po potwierdzeniu uśpienia.
Pomija zbędne ponowne odświeżenie po udanej zmianie z dostępnym, znanym stanem
zasilania, chyba że aktywne połączenie wymaga sprawdzenia toru audio. Zachowuje
oczekiwania bezpieczeństwa producenta. Czas i ciągłość mowy wymagają ponownego
sprawdzenia na odtwarzaczu.

## Granice weryfikacji

Osobny pasywny zestaw diagnostyczny jest w
`installfiles/diagnostics/hibyr1-connectivity`; źródła i instrukcje znajdują się
w `tools/diagnostics/hiby_r1_connectivity`. Domyślny tryb Check tylko odczytuje
jawnie wskazaną kartę. Enable i Restore wymagają potwierdzenia; nie nakładaj
zestawu na starszy logger audio alpha8. Zestaw rozpoznaje wyłącznie programy
alpha8/alpha9 i zgodną bibliotekę ALSA, a nie dowolny nowy build. Zbiera krótki
raport sprzętu i usług przy starcie, nie hasła, profil użytkownika ani dowód
działającego Bluetooth. Stosuj dopasowaną instrukcję i przywróć oryginalny program
przed aktualizacją aplikacji.

Testy hosta z atrapami sprawdzają politykę, przywracanie, błędy i zasoby;
Windows może sprawdzić nawigację oraz mówione komunikaty niedostępności.
Żadne z nich nie potwierdza fizycznego Wi-Fi/Bluetooth R1, pełnego startu usług
producenta, zasilania radia, dźwięku słuchawek ani zużycia energii. Do czasu prób
na odtwarzaczu tryb samolotowy jest administracyjną polityką najlepszej próby,
a nie certyfikatem ciszy radiowej ani gwarancją do zastosowań lotniczych.
