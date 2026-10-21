# HiBy R1: bezpieczeństwo pamięci USB

## Aktualny stan

Projekt nie został przetestowany na fizycznym R1. Nie znamy jeszcze firmware,
automountera ani usług przyszłego odtwarzacza użytkownika. Domyślna kompilacja
R1 **odmawia udostępnienia karty jako zapisywalnej pamięci masowej USB**.
To zabezpieczenie, a nie gotowa funkcja przesyłania plików. Nie ma opcji
„włącz mimo ryzyka”.

Odziedziczona implementacja pozostawiała system plików zamontowany w Linuksie,
a jednocześnie udostępniała komputerowi jego surowe urządzenie. Ustawiała też
LUN przed potwierdzeniami wątków Rockboxa. Równoczesny zapis może uszkodzić
dane. Zabezpieczenie R1 nie przypisuje już surowego urządzenia karty podczas
konfiguracji trybu ani zwykłego włączenia USB. Inne odtwarzacze pozostają
bez zmian.

Przesyłanie plików przez ADB może później ograniczyć wyjmowanie karty, ale ta
zmiana nie wdraża ani nie sprawdza aktualizatora ADB. Nie zastępuj bibliotek
ani modułów działającego Rockboxa bez ustalonej bezpiecznej procedury.
Zachowaj kopię danych i możliwość odzyskania systemu.

## Kontrakt transakcji

Natywny adapter realizuje obecnie jedynie sprawdzane odłączenie gadgetu oraz
ostrożną kontrolę dostępności lokalnego katalogu karty. Konfiguracja jest na
stałe niezweryfikowana; nie ma jeszcze natywnego adaptera odmontowania,
ponownego montowania ani kontroli automountera. Wspólny silnik transakcji,
bez alokacji pamięci, jest sprawdzany na atrapach operacji, nie jądrze playera.

Włączenie rzeczywistej funkcji wymaga sprawdzonego adaptera, który:

- Przejmuje ciągłą wyłączną kontrolę nad odpowiednimi automounterami,
  procesami/przestrzeniami montowań i konfiguracją gadgetu, utrzymując ją do
  końca przywracania. Migawka listy montowań nie zapewnia takiej kontroli.
- Zapamiętuje rzeczywistą tożsamość urządzenia, kompletne opcje i miejsce
  montowania; odrzuca niejednoznaczności, aliasy i nakładające się montowania.
- Zamyka zasoby, synchronizuje i wykonuje zwykłe odmontowanie. Bez lazy/force
  i bez współdzielenia zapisywalnego systemu plików z komputerem.
- Sprawdza odłączenie, zapis LUN i podłączenie UDC, także błędy zapisu,
  odczytu, zamknięcia i zgodność odczytu kontrolnego. Ponawia kontrolę
  wyłączności i nakładających się montowań.
- Odłącza komputer i zwalnia LUN przed odtworzeniem tego samego systemu
  plików i opcji. Niebezpieczny błąd przywracania musi nadal blokować
  użytkowników plików w Rockboxie.

Loader kopiuje aplikację do `/tmp`, ale jego przypięta wersja szuka bibliotek
na karcie. Kodeki i wtyczki również są ładowane dynamicznie. Takie mapowania
mogą blokować zwykłe odmontowanie; sam program w RAM nie oznacza wolnej karty.
Docelowo może być potrzebne sprawdzone przenoszenie zależności do RAM albo
inna metoda aktualizacji.

## API integracji

Nagłówek: `firmware/target/hosted/hiby/usb-storage-hiby.h`.

`hiby_usb_storage_target_prepare()`, `hiby_usb_storage_target_export()`,
`hiby_usb_storage_target_restore()` i `hiby_usb_storage_target_status()`
zwracają `struct hiby_usb_storage_status`. Pola: `success`, `safe_to_resume`,
`error`, `system_error`, `recovery_error`, `state`, `configuration_verified`.
`hiby_usb_storage_target_safe_to_resume()` zwraca bieżący wynik kontroli
bezpiecznego wznowienia. Błędy systemowe są dodatnimi wartościami errno;
pole `error` wskazuje etap transakcji.

Domyślne przygotowanie kończy się `HIBY_USB_STORAGE_ERROR_UNVERIFIED`.
`safe_to_resume` jest prawdziwe dopiero po sprawdzonym odłączeniu i dostępności
lokalnej karty, nigdy tylko dlatego, że przygotowanie się nie udało. Udane
przywrócenie oznacza powrót lokalnego dostępu, **nie** udany transfer USB.
Getter statusu zachowuje ostatni błąd przez udane sprzątanie i ponowne
zastosowanie ustawień, do kolejnej próby przygotowania.

Koordynator podłącza prywatną zmianę trybu USB, obie ścieżki ACK/bez ACK,
odłączenie/przywracanie oraz dostępny komunikat PL/EN w aplikacji. Nie wolno
zgłaszać udanego trybu wyłącznego po błędzie. Bezpieczna odmowa może zwolnić
czekające wątki; niebezpieczne przywracanie nie może ogłaszać gotowości plików.
Kopię zachowanego statusu należy pobrać bezpośrednio po `handle_usb_events`,
przed `settings_apply`. Błąd z tej kopii należy ogłosić dopiero po bezpiecznym
przywróceniu fontów i ustawień. Firmware nie wywołuje TTS. Komunikat przy
niebezpiecznym przywracaniu nie może wymagać plików z niedostępnej karty.

## Ograniczenia weryfikacji

Testy atrap sprawdzają transakcję i zabezpieczenia R1 bez montowania,
zapisywania sysfs ani dotykania odtwarzacza. Nie potwierdzają rzeczywistego
transferu, kontroli usług producenta, odporności na utratę zasilania ani
dostępności na sprzęcie. Zmiana nie obejmuje bootloadera ani firmware producenta.
