Pasywna diagnostyka łączności HiBy R1

To osobny zestaw, niezależny od diagnostyki audio przypiętej do alpha8. Nie jest
aktualizacją firmware ani wydaniem aplikacji. Zachowaj dopasowanie istniejącego
zestawu audio do jego oryginalnej aplikacji.

Używaj po podłączeniu i zidentyfikowaniu karty. Przed wyjęciem karty całkowicie
wyłącz R1. Zestaw trzymaj na zapisywalnym dysku komputera, poza kartą. Raporty
pozostają obok skryptu w Reports. Nie używaj starej litery dysku bez sprawdzenia
nowo podłączonej karty. Kopia zapasowa karty nie jest potrzebna.

Windows PowerShell 5.1, klawiatura i NVDA

Start.cmd otwiera zwykłe menu tekstowe: wpisz numer i Enter. Sam Enter wybiera
Sprawdź; 0 kończy. Nie ma obsługi myszy, globalnego wstrzykiwania klawiszy,
przełączania fokusu ani sterowania radiami komputera. Domyślny język to polski;
Start.cmd -Language en włącza angielski. Polecenia bezpośrednio w PowerShell:

  .\Connectivity-diagnostics.ps1 -CardRoot F:\
  .\Connectivity-diagnostics.ps1 -Mode Enable -CardRoot F:\
  .\Connectivity-diagnostics.ps1 -Mode Collect -CardRoot F:\
  .\Connectivity-diagnostics.ps1 -Mode Restore -CardRoot F:\

Zastąp F:\ katalogiem głównym zidentyfikowanej karty wymiennej. Ścieżki UNC,
podfoldery, dysk systemowy, dowiązania i junction są odrzucane. Dyski USB typu
Fixed również celowo są odrzucane; nie obchodź tego dowiązaniem. Włączenie
i przywrócenie wymagają dokładnego TAK (YES po angielsku). Inna odpowiedź
anuluje.
Skrypt PowerShell ma kodowanie UTF-8 ze znacznikiem BOM, aby Windows PowerShell
5.1 poprawnie czytał polskie znaki. Zachowaj BOM przy edycji lub przenoszeniu.
Menu, potwierdzenia, błędy i ostrzeżenia raportu odpowiadają -Language pl lub en.

Check — Sprawdź, domyślnie: tylko odczyt karty, mały raport we własnym Reports,
hashe programu i bibliotek oraz wykryte konflikty z diagnostyką audio. Nie
czyta ustawień, wznowień, haseł, zakładek ani list sparowanych urządzeń.

Aktywna diagnostyka audio nie uniemożliwia Check, lecz blokuje Enable. Najpierw
wykonaj Restore istniejącym, DOPASOWANYM zestawem AUDIO alpha8. Nie nakładaj
launcherów i nie przepinaj zestawu audio na alpha9. Ponownie podłącz kartę
i wykonaj Check.

Enable — Włącz: obsługuje wyłącznie oryginalne aplikacje o hashach:
alpha8: 7d82d50b88e0bfc3f0fe7bc6882843d047128d5504fc10bbdc72664119058390
alpha9: a536942c7cc6caa68c6dae24c2128e9d623562e2e26e7df10fdb51539684e122
ALSA:   e7dd65afbb4209ffda6edea998cd0f4116fe166eb859939553ac6840f964f8ed

Hash alpha9 wyliczono strumieniowo z obecnej paczki natywnej o SHA256
5ff3a5767695e7750ee74792ecd802da9c80399ca2d50478816967e36a1fcda3.
Inne wersje wymagają przyszłego, sprawdzonego zestawu. Nie ma nadpisywania
hashów dla żadnej karty. Ściśle wydzielony mechanizm testowy zmienia wyłącznie
politykę katalogu głównego dysku, tylko w centralnym radio-diagnostics/tests
z pasującym skryptem, kartą i znacznikiem. Testy używają opublikowanych bajtów
aplikacji i bibliotek, a nie innych dopuszczonych hashów.

Oryginał zostaje PRZENIESIONY na TEJ SAMEJ karcie z .rockbox/rockbox.r1 do
.rockbox/rockbox.r1.connectivity-original. Nie jest kopiowany na komputer ani
do kopii zapasowej. Zweryfikowany launcher zastępuje rockbox.r1 po przygotowaniu
pliku tymczasowego. Stan diagnostyki zapisuje pełny hash oryginału i wszystkich
sąsiadujących bibliotek .so. Profile, głośność, autostart, rb_bt_on.txt,
firmware i ustawienia radiowe pozostają bez zmian. Nieoczekiwane pliki
diagnostyczne powodują odmowę, nigdy nadpisanie.

Uruchom R1 raz, zaczekaj na start Rockboxa i normalnie wyłącz urządzenie.
Bootloader kopiuje launcher do /tmp i przekazuje tylko LD_LIBRARY_PATH, dlatego
launcher nie wyznacza ścieżki karty z $0. Używa znanego katalogu. Weryfikuje hash
oryginału, kopiuje rzeczywisty oryginał do prywatnego, unikalnego katalogu /tmp,
sprawdza jego hash i uruchamia go. Działa to również przy karcie noexec. Ta
konieczna kopia wykonawcza pozostaje do restartu po udanym exec. Błędy startu
sprzątają wyłącznie własne pliki tymczasowe. Wyjście aplikacji nie trafia do logu.

Jednorazowa migawka powstaje PRZED aplikacją, tylko gdy nie istnieje już
r1-connectivity.log. Limit wynosi 64 KiB, pojedynczy odczyt pola maksymalnie
256 bajtów. Odczyty obejmują maksymalnie 16 rzeczywistych wpisów rfkill z polami
type/name/soft/hard/state; stałe funkcje SDIO mmc0:0001:1 i mmc0:0001:2
(vendor/device/class i cele dowiązań driver/module); obecność i flagi wlan0/1;
maksymalnie 256 nazw comm procesów filtrowanych do usług Bluetooth, hciattach
i brcm_patchram; /run/r1_wireless_type oraz metadane /dev/rfkill. Sprawdzony
rootfs nie ma stat, więc metadane są pobierane ograniczonym ls -ldn z liczbowymi
identyfikatorami (operacja stat, bez otwierania urządzenia radiowego). Nie odczytuje
strumienia urządzenia rfkill ani ioctl. Nie uruchamia poleceń sterujących radiami.
Opcjonalne bluetoothctl show wymaga stałego BusyBox z rootfs z dostępnym timeout
i kontrolera. Limit wynosi 3 sekundy z SIGKILL i najwyżej 4096 bajtów odczytu.
W sprawdzonym BusyBox 1.31.1 producenta nie ma timeout, więc zapytanie jest
pomijane i log mówi o tym wprost. Opcje dd sprawdzono rzeczywistym narzędziem
producenta na prywatnych plikach. Brak sprzętu oznacza niedostępne dane, a nie potwierdzone
wyłączenie zasilania. Nie działa żaden ciągły proces odpytywania.

Potwierdzony bootloader producenta 1.8b2 wykonuje wifi_down, odłącza funkcję
SDIO 2 i usypia Bluetooth, chyba że istnieje .rockbox/rb_bt_on.txt. Migawka przed
aplikacją pozwoli zbadać przekazany stan i tożsamość sprzętu; nie potwierdza
elektrycznego wyłączenia RF, skutecznego wznowienia ani działania fizycznych radii.

Collect — Zbierz: kopiuje WYŁĄCZNIE istniejący log diagnostyczny do 64 KiB do
nowego podfolderu Reports, sprawdza hashe i nie zmienia karty. Ta użyteczna
dodatkowa kopia logu pozostaje do analizy; nie powstaje kopia karty ani profilu.

Restore — Przywróć: sprawdza oryginał, launcher, stan i pełny zapisany zestaw
bibliotek przed zmianami. Przenosi launcher, log i stan do nowego Reports,
a oryginał z powrotem do rockbox.r1. Błędy przenoszenia wycofują zakończone
operacje. Nie kasuj ręcznie nieznanego pliku, by wymusić przywrócenie. Można
przywrócić również przerwane przygotowanie przed lub po przeniesieniu oryginału,
jeśli zachował się prawidłowy stan. Utrata zasilania lub uszkodzenie systemu
plików nadal może wymagać ręcznej analizy; zachowaj dowody i zgłoś błąd.

Sprawdzenie obejmuje rzeczywisty PowerShell 5.1 na sztucznych kartach i launcher
z odizolowanymi atrapami narzędzi, sysfs i procesów. Fizyczny R1, start jego
bootloadera, fizyczne radia oraz odczyt przez rzeczywisty NVDA nie są sprawdzone.
Testy na komputerze nie są akceptacją sprzętową.
