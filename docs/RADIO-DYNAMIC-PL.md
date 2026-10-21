# Mowa radia i informacje o stacji

Automatyczne skanowanie stacji trwa również po wstrzymaniu jego komunikatów.
Zwykły klawisz nawigacji przerywa bieżącą wypowiedź; następne osobne naciśnięcie
wznawia komunikaty o przyszłej lub ostatniej znalezionej częstotliwości.
Klawisze rozpoznawane przy puszczeniu wznawiają mowę przy puszczeniu.
Przytrzymanie klawisza nie przełącza mowy wielokrotnie. Przerwana wypowiedź nie
jest wznawiana od poprzedniego miejsca, a wszystkie częstotliwości nie są
gromadzone w kolejce.

OK/Enter wycisza komunikaty skanowania do końca tego skanowania. Zwykłe
przypisania Anuluj, Wstecz i Power zachowują swoje znaczenie, również gdy
klawisz kierunkowy jest na danym odtwarzaczu przypisany do anulowania.
USB, wyłączanie, ponowne uruchomienie i zdarzenia pamięci zachowują obsługę
systemową. Skanowanie przerwane anulowaniem lub wyjściem systemowym nie jest
ogłaszane jako zakończone.

Po zwykłym zakończeniu, również po zapełnieniu listy stacji, Rockbox mówi
„Skanowanie zakończone”, jeżeli mowa interfejsu jest włączona. Komunikat ten
nie zależy od ustawienia dynamicznych komunikatów ani tymczasowego wyciszenia
skanowania. Następne skanowanie otrzymuje własny, początkowy stan mowy,
a zwykła mowa interfejsu pozostaje dostępna.

Ustawienie dynamicznych komunikatów Talkboxa steruje automatycznym czytaniem
znalezionych częstotliwości przy włączonej syntezie. Przy wyłączonej syntezie
pliki głosowe zachowują własne ustawienie czytania menu. Aktualizacje obrazu
skanowania są nieme i nie wywołują dodatkowych wypowiedzi syntezatora.
Gdy synteza jest zajęta, zapamiętana pozostaje tylko ostatnia oczekująca
częstotliwość; wypowiedzi plików głosowych dzieli przynajmniej pięć sekund.
Klawisze są sprawdzane pomiędzy operacjami tunera, więc czas przerwania mowy
zależy również od jego sterownika.

Na odtwarzaczach skonfigurowanych do obsługi RDS menu radia zawiera
**Informacje RDS**. Dwa wybieralne i czytane wiersze przedstawiają nazwę
stacji oraz tekst radiowy, a przy braku danego pola — **Brak danych RDS**.
OK odświeża oba pola i czyta wybrany wiersz. Automatyczne zmiany metadanych
nie przerywają tego świadomie otwartego ekranu informacji. Czytanie wierszy
i ich odświeżanie działa również po wyłączeniu dynamicznych komunikatów.
Wstecz wraca do menu radia; USB i wyłączanie korzystają ze zwykłej obsługi listy
i zdarzeń systemowych.

Nazwa stacji i tekst radiowy mają stałe bufory dostosowane do wyniku UTF-8
dekodera: odpowiednio 25 i 193 bajty. Odczyt odbywa się przez wspólny interfejs
tunera, bez zmian sterowników i oddzielnego silnika mowy dla danego urządzenia.

## Możliwości urządzeń i weryfikacja

Konfiguracje Sansa Clip+ i Clip Zip definiują `HAVE_RDS_CAP`. Clip+ używa
odpytywania i pozwala wybrać tuner z rodziny SI4700 albo RDA5802; Clip Zip
konfiguruje tuner z rodziny SI4700 i RDS obsługiwany przerwaniem. Sterownik
SI4700 włącza dekodowanie według bitu możliwości układu. Obecny sterownik
RDA5802 nie dostarcza zdekodowanych danych RDS. Samo makro konfiguracji nie
gwarantuje odbioru na konkretnym egzemplarzu, stacji ani antenie.

Izolowane testy regresyjne wykorzystują rzeczywiste funkcje radia i wspólne
reguły mowy oraz kontrolowane zastępniki tunera, klawiszy i wyjścia głosowego:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -p test_radio_dynamic.py -v
```

Obejmują syntezę, pliki głosowe, konfiguracje z RDS i bez RDS, zakończenie
skanowania, wstrzymanie i wznowienie mowy, Enter, powtórzenia i puszczenia,
zdarzenia bezpieczeństwa, ograniczony stan, brak stacji, zapełnienie listy,
brak metadanych i ręczne odświeżanie. Obie wersje językowe wykorzystują
rzeczywiste etykiety katalogów; sprawdzana jest zgodność tekstu wyświetlanego
i czytanego oraz wykrywanie celowo przywróconych błędów mowy i bezpieczeństwa.
Wygenerowane materiały testów i raporty
trafiają do centralnego `Workspace/rockbox/radio-dynamic-tests`.
Testy te nie potwierdzają słyszalnej mowy, zgodności kompilacji firmware ani
fizycznego odbioru. Etap programowy HiBy R1 nie obejmuje fizycznej akceptacji
FM; odbiór RF/RDS na Clip+/Clip Zip, prawdziwe klawisze, czytniki ekranu
i dźwięk wymagają osobnych kompilacji i prób sprzętowych. Ta praca w źródłach
nie zmienia istniejących wydań programu.
