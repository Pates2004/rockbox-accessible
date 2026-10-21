# HiBy R1: Wi-Fi, wyłączanie i energia

[English](HIBY-R1-POWER.md)

## Wi-Fi

Ten build jawnie żąda blokady nadajnika typu **WLAN** przez linuksowe `rfkill`
i wyłącza interfejsy `wlan0` oraz `wlan1`, jeśli istnieją. Sprawdza wynik
odczytem stanu. Robi to raz przy starcie głównej aplikacji, nie w każdej
pomocniczej instancji dźwięku; nie uruchamia okresowego skanowania.

Nie blokuje Bluetooth ani wszystkich nadajników naraz, nie usuwa wspólnego
sterownika Wi-Fi/BT i nie wyłącza wspólnego zasilania układu. Nie wykonuje
zbiorczego `killall` i nie usuwa haseł ani konfiguracji Wi-Fi producenta.
Sama obecność Linuksa lub brak klienta sieci w Rockboksie wcześniej nie
gwarantowały wyłączenia odziedziczonego Wi-Fi.

Sterowanie radiami jest w **Ustawienia → Łączność**:
[opis preferencji, stanu i trybu samolotowego](HIBY-R1-CONNECTIVITY-PL.md).
Startowa diagnostyka pozostała w **System → Debug → Stan Wi-Fi przy uruchomieniu**.
To udźwiękowiona **migawka ze startu**, nie ciągły monitoring ani pomiar prądu.
Pokazuje wynik blokady, liczbę wpisów WLAN, potwierdzone nieaktywne interfejsy
oraz kody błędów sterowania:

- **Potwierdzona:** odczytane wpisy WLAN zgłosiły blokadę nadajnika.
- **Brak wpisu radia; blokada niepotwierdzona:** nie znaleziono wpisu WLAN
  w `rfkill`. Nie jest to dowód braku sprzętu ani odcięcia jego zasilania.
- **Nie potwierdzono wyłączenia Wi-Fi:** kontrola nie powiodła się albo sterownik
  nie udostępnił potwierdzenia. Przy starcie pojawia się również komunikat.
- **Niedostępne w tej kompilacji:** symulator nie steruje radiami komputera;
  nie przedstawia zer jako pomiarów sprzętowych.

Kod `0` oznacza brak zarejestrowanego błędu danej operacji, nie osobny dowód
odcięcia energii. Przy niepotwierdzonym stanie podaj wszystkie pozycje ekranu.
Rockbox nadal się uruchamia; nie ukrywamy braku potwierdzenia. Inny program
z uprawnieniami może później zmienić blokadę; migawka tego nie wykrywa.
Nie ma tu klienta NAS. Włączenie WLAN jest możliwe w Łączności; nie oznacza
połączenia z siecią. W zbadanym sterowniku rfkill zapisuje flagę programową,
więc blokada nie potwierdza fizycznego odcięcia zasilania radia.

Blokada nadajnika nie jest pomiarem prądu ani obietnicą fizycznego odłączenia
całego układu. [Dokumentacja rfkill Linuksa](https://www.kernel.org/doc/html/latest/driver-api/rfkill.html).

## Wyłączenie urządzenia

Polecenie wyłączenia przechodzi przez normalne zamknięcie Rockboksa: zapis
ustawień i stanu, zatrzymanie odtwarzania oraz zakończenie własnych usług.
Na R1 nie powinno jedynie kończyć aplikacji ani gasić ekranu.

Backend synchronizuje system plików i uruchamia `/sbin/poweroff` bez powłoki.
Producentowski `init` dostaje do 30 sekund na zamknięcie usług i odmontowanie
systemów plików. Jeśli urządzenie nadal działa, backend ponownie synchronizuje
dane i żąda wyłączenia jądra przez `RB_POWER_OFF`. Oczekiwanie jest ograniczone;
nie używa starej nieskończonej pętli budzącej CPU co milisekundę. Proces potomny
jest śledzony i sprzątany w granicach dostępnych operacji systemowych.
Równoczesne żądanie z głównego wątku i zabezpieczenia czasu wyłączenia nie
uruchamia drugiej procedury: wyłączanie jest serializowane.
R1 pozostawia też zwykłą obsługę zakończenia przez `SIGTERM`: zamykanie usług
przez producentowski system nie może być mylone z awarią i kończyć się paniką
lub restartem.
To ograniczenie pętli programu: zablokowane wywołanie jądra, np. uszkodzonego
sterownika lub synchronizacji, nadal może uniemożliwić zakończenie w tym czasie.

Jeśli także wyłączenie jądra wróci z błędem, obraz zostaje przywrócony i pojawia
się panika `Power off failed` z kodami. Nie udajemy, że urządzenie jest wyłączone.
Zapisz kody; sprzętowy sposób wymuszenia wyłączenia zależy od urządzenia.
Przywracanie obrazu wyłącza także kurtynę. Taki fatalny komunikat może już nie
mieć mowy, ponieważ normalne zamknięcie zdążyło wyłączyć audio; nie obiecujemy
udźwiękowienia paniki po zamknięciu sprzętu dźwiękowego.
Pętla oczekiwania na przyciski w panice R1 usypia między odczytami zamiast
obciążać cały rdzeń CPU. Nadal jest to ekran błędu, nie udane wyłączenie.
[Opis wywołania reboot(2)](https://www.man7.org/linux/man-pages/man2/reboot.2.html).

Domyślne dłuższe przytrzymanie Power pozostaje obsługiwane przez firmware.
W klawiaturze pierwsze przytrzymanie kończy pisanie: zwolnij wtedy przycisk,
jeśli nie chcesz dalej żądać wyłączenia. Przypisanie dostępności „Wyłącz
urządzenie” korzysta z tej samej drogi zamknięcia. Kurtyna, blokada i zgaszenie
podświetlenia nie są wyłączeniem odtwarzacza.

Nie trzeba ponownie flashować UPT. Na już zmodyfikowanym R1 aktualizuje się
`.rockbox` na karcie zgodnie z instrukcją instalacji.

## Testy i ograniczenia

Testy zastępują operacje systemowe kontrolowanymi atrapami: sprawdzają błędy,
krótkie I/O, przerwania, deskryptory, procesy, zachowanie BT, ograniczony czas
oczekiwania i zgłoszenie nieudanego wyłączenia. Nie wyłączają komputera,
nie zmieniają jego sieci i nie mierzą fizycznego R1.

Klawiatura nie odświeża już niepotrzebnie całego obrazu co 50 ms w bezczynności;
widoczny kursor i aktywne wejście nadal są odświeżane. Ciemne kolory nie
gwarantują oszczędności LCD. Kurtyna zachowuje dotyk i nie obiecuje odcięcia
zasilania panelu. Nie podajemy zmyślonego wydłużenia pracy ani wyniku „zero
wycieków” całego urządzenia.

Odbiór sprzętowy musi osobno sprawdzić start, stan Wi-Fi, BT, audio z mową,
blokadę/kurtynę, wyłączenie i ponowny start. Wyłączenie sprawdź również bez USB:
ładowanie i wybudzanie przez zasilanie mogą zmieniać zachowanie sprzętu.
Czarny ekran ani dioda nie są pomiarem prądu. Czas pracy porównuj w tych
samych warunkach. Zobacz `HIBY-R1-CONTROLS-PL.md`, `INTERFACE-APPEARANCE-PL.md`
oraz `HIBY-R1-NETWORK-EMULATION-PL.md`.
