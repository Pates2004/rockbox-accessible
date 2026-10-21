# Gotowe kolory interfejsu

## Jasność i czas podświetlenia

Ustawienia → Ustawienia ogólne → Wyświetlacz → Ustawienia wyświetlacza
rozdzielają te funkcje. Jasność zmienia poziom światła (na R1 zakres1–100),
a Podświetlenie i Podświetlenie podczas ładowania wybierają czas albo
Nigdy/Zawsze. Nie są różnymi nazwami tej samej opcji. Dodatnie czasy są
odczytywane liczbą i jednostką; poprawiono callback, który zastępował je słowem
„Rockbox”, bez zmieniania nazw czasów na jasność. Kurtyna jest niezależna.

## Wybór kolorów

Na odtwarzaczu z kolorowym ekranem wybierz Ustawienia → Ustawienia motywu → Kolory → Gotowe kolory interfejsu. Dostępne pozycje są poleceniami, a nie osobnym zapisywanym trybem:

- **Ciemny interfejs:** prawie biały tekst na prawie czarnym tle oraz biały tekst zaznaczonej pozycji na ciemnoniebieskim pasku.
- **Jasny interfejs:** prawie czarny tekst na białym tle oraz ten sam ciemnoniebieski pasek zaznaczenia z białym tekstem.
- **Domyślne kolory interfejsu:** przywrócenie domyślnych wartości tekstu, tła, zaznaczenia, separatora i stylu zaznaczenia z kompilacji. Nie jest to przywrócenie ustawień fabrycznych ani całego motywu.

Każde polecenie korzysta z istniejących ustawień kolorów Rockboksa. Od razu stosuje zmiany i zleca zwykły zapis ustawień, więc wynik pozostaje po prawidłowym wyłączeniu i ponownym uruchomieniu. Nie powstaje dodatkowy profil ani format konfiguracji. Poszczególne kolory nadal można zmieniać osobno. Wczytanie innego motywu może je zastąpić.

## Co się zmienia

Polecenie wybiera wbudowany pasek stanu i prosty interfejs głównego ekranu, usuwa wybór obrazka tła oraz własnej konfiguracji obszaru interfejsu, a także wyłącza kolory zależne od rodzaju pliku. Dzięki temu poprzednia skórka lub obrazek nie zasłaniają wybranej palety. Widoczność paska stanu oraz jego położenie na górze lub na dole pozostają bez zmian.

Czcionki, zestawy ikon, skórki odtwarzania i radia, ustawienia ekranu pilota oraz dostępności pozostają bez zmian. Pliki motywów nie są usuwane ani nadpisywane. Polecenia nie zapamiętują automatycznie poprzednich dowolnych kolorów i skórek: aby wrócić do wcześniejszego motywu, wczytaj go ponownie z ustawień motywu albo przywróć zapisaną konfigurację. Domyślne kolory interfejsu zachowują prosty interfejs; nie wczytują poprzedniego motywu ani domyślnego obrazka tła.

## Zakres i energia

To paleta podstawowego interfejsu, nie filtr zmieniający każdy ekran. Własne skórki odtwarzania, okładki, ikony bitmapowe, wtyczki i ekrany samodzielnie dobierające kolory mogą wyglądać inaczej. Własny mechanizm kolorowania listy również może zastąpić zwykły kolor tekstu. Kolejny motyw może nadpisać ustawienia palety.

Ciemny wygląd jest niezależny od kurtyny ekranu. Nie ukrywa interfejsu, nie wyłącza podświetlenia, nie zmienia jasności i nie gwarantuje oszczędności baterii na ekranie LCD R1. Nie dodaje pracującego w tle wątku, okresowego zegara ani ciągłego przeliczania kolorów. Etykiety menu są tłumaczone i korzystają ze zwykłego udźwiękowienia Rockboksa; nie jest to potwierdzenie dostępności przez NVDA w Windows ani odbioru na fizycznym urządzeniu.
