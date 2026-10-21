# HiBy R1 — sterowanie przyciskami

[English](HIBY-R1-CONTROLS.md)

Nowe fabryczne profile rezerwują trzykrotne Power na grupowy skrót dostępności
w interfejsie i na ekranie odtwarzania. Zapisane przypisania pozostają bez zmian.
Krótsze sekwencje Power czekają wtedy dotychczasowe 300 ms wielokliku. Ustawienie
Domyślne sterowanie Rockboxa w polu trzykrotnego naciśnięcia przywraca natychmiastową
obsługę systemową. Tabele poniżej opisują akcje systemowe, nie własne przypisania.
Zobacz `ACCESSIBILITY-SHORTCUT-PL.md` i `ACCESSIBILITY-LISTS-PL.md`.

## Opisy domyślnych przypisań w urządzeniu

W Ustawienia → Ustawienia ogólne → System → Ustawienia przycisków fizycznych
pozycje domyślne i nieprzypisane pokazują oraz odczytują także ich działanie
w wybranym profilu. Dla nieprzypisanej głośności opis dotyczy rzeczywistej regulacji
głośności, nie strzałek listy. Na końcu jest **Przewodnik po domyślnych
przyciskach**: wybierz menu, muzykę, tekst albo klawiaturę. Każde naciśnięcie
ma opis wyprowadzony z prawdziwej mapy danego kontekstu, bez zmiany przypisań.

Dwukrotne i trzykrotne naciśnięcie nie mają osobnej funkcji systemowej;
przewodnik wskazuje zwykłą funkcję przycisku. Przy własnych przypisaniach
rozpoznawanie wielokliku może grupować wejście i opóźniać pojedynczą akcję.
Przewodnik opisuje bazowe sterowanie, nie wszystkie własne mapy i wtyczki.
Power przytrzymany w menu żąda wyłączenia po dłuższym czasie, natomiast
w klawiaturze pierwsze przytrzymanie kończy pisanie. Szczegóły energii
i wyłączania: `HIBY-R1-POWER-PL.md`; kolory: `INTERFACE-APPEARANCE-PL.md`.

Profil korzysta z pięciu fizycznych przycisków: Power, Play, Next, Głośność +
i Głośność -. R1 nie ma fizycznego przycisku Previous. Poniższy opis dotyczy
nowej mapy przycisków rdzenia R1; nie oznacza zainstalowania ani sprawdzenia
wydania na odtwarzaczu.

Krótkie naciśnięcie oznacza naciśnięcie i zwolnienie. Przytrzymanie dochodzi
do pierwszego zdarzenia powtórzenia Rockboksa. Przy kombinacji najpierw naciśnij
pierwszy wymieniony przycisk, dodaj drugi, następnie zwolnij drugi przed
pierwszym. Kombinacji z Power używaj krótko: dalsze trzymanie Power, również
w kombinacji, może zażądać wyłączenia. Szybkie zwolnienie obu przycisków
w odwrotnej kolejności również nie wykonuje ich krótkich akcji; pozostawienie
jednego wciśniętego może uruchomić jego zwykłe powtarzanie.

## Listy, menu, przeglądarka plików i zakładki

| Przycisk | Działanie |
| --- | --- |
| Krótka Głośność + / Głośność - | Poprzednia / następna pozycja po zwolnieniu |
| Przytrzymanie Głośności + / Głośności - | Zwiększenie / zmniejszenie głośności odsłuchu; bez ruchu po liście |
| Next | Aktywacja wybranej pozycji |
| Przytrzymanie Next | Menu kontekstowe; na liście wyboru ustawienia przywrócenie wartości domyślnej |
| Play | Wstecz / anulowanie |
| Przytrzymanie Play | Menu główne |
| Power | Aktywacja / OK, tak jak krótki Next |
| Power + Play | Ekran główny / menu główne |
| Power + Głośność + | Blokowanie / odblokowanie |
| Power + Głośność - | Szybkie ustawienia |

Krótkie naciśnięcia głośności nawigują dopiero po zwolnieniu bez przytrzymania.
Każde powtórzenie przytrzymanego przycisku zmienia rzeczywistą głośność odsłuchu:
ani początkowe naciśnięcie, ani zwolnienie nie przesuwa wyboru. Działa to przez
API akcji rdzenia na listach, w czytniku i specjalizowanych edytorach,
z uwzględnieniem blokady/podświetlenia, remapowania i jawnych kombinacji
z modyfikatorem. Zwykłe listy wyboru ustawień używają krótkiej Głośności + / -
do wyboru wartości, Next lub Power do zapisania i Play do anulowania.
Ekran odtwarzania otwórz przez odpowiednią pozycję menu głównego.

Znaczenie akcji semantycznej określa dany ekran: przykładowo menu kontekstowe
zakładek udostępnia istniejące operacje na zakładkach. Akcja menu głównego
nie wymusza takiego przejścia w dowolnej wtyczce lub oknie dialogowym.

## Ekran odtwarzania

To mapowanie zależy od bieżącego ekranu, nie od samego odtwarzania muzyki.
Dlatego głośność steruje tutaj głośnością, Play i Next zmieniają utwory,
a Power przełącza odtwarzanie i pauzę. Po powrocie do menu krótkie przyciski
głośności znów poruszają się po liście, nawet gdy muzyka nadal gra w tle.
Przypisane ogólne strzałki także są tłumaczone na akcje danego ekranu.
Ustawienia przycisków fizycznych rozdzielają teraz Akcje w interfejsie i Akcje
na ekranie odtwarzania, każde z osobnymi przypisaniami pojedynczych, dwukrotnych,
trzykrotnych naciśnięć oraz przytrzymań. Drugi profil działa tylko w aktywnym
WPS, nie w menu podczas grania muzyki w tle. Starsze globalne przypisania są
zachowane w obu profilach przy migracji; można je zmieniać niezależnie.
Próg czasu przytrzymania pozostaje wspólny. Nie zmienia to
awaryjnego wyłączania, kombinacji blokady ani odzyskiwania kurtyny.

| Przycisk | Działanie |
| --- | --- |
| Play | Poprzedni utwór / początek, zgodnie z dotychczasowymi zasadami odtwarzania |
| Przytrzymanie Play | Przewijanie wstecz; zwolnienie kończy je bez przeskoku utworu |
| Next | Następny utwór |
| Przytrzymanie Next | Przewijanie naprzód; zwolnienie kończy je bez przeskoku utworu |
| Power | Odtwarzanie / pauza |
| Głośność + / Głośność - | Zwiększenie / zmniejszenie głośności; przytrzymanie powtarza |
| Power + Play | Menu główne |
| Power + Next | Menu kontekstowe odtwarzania |
| Play + Next | Przeglądanie plików |
| Play + Głośność + | Ekran wysokości dźwięku / prędkości |
| Play + Głośność - | Zatrzymanie odtwarzania |
| Power + Głośność + | Blokowanie / odblokowanie |
| Power + Głośność - | Szybkie ustawienia |

Next jest tutaj przyciskiem multimedialnym; jego przytrzymanie przewija.
Menu kontekstowe odtwarzania otwiera Power + Next. Przytrzymanie Power nie ma
przypisanej akcji menu ani odtwarzania/pauzy.

## Wspólny czytnik tekstu z mową

| Przycisk | Działanie |
| --- | --- |
| Play / Next | Przesunięcie wstecz / naprzód o wybraną jednostkę tekstu |
| Przytrzymanie Play | Powtarzanie nawigacji tekstu wstecz |
| Krótka Głośność + / Głośność - | Poprzednia / następna jednostka tekstu |
| Przytrzymanie Głośności + / Głośności - | Zwiększenie / zmniejszenie głośności odsłuchu; bez zmiany kursora i jednostki |
| Power | Pauza / wznowienie czytania |
| Przytrzymanie Next | Menu kontekstowe czytnika |
| Power + Play | Zamknięcie czytnika i powrót do wywołującego ekranu |
| Power + Głośność + | Blokowanie / odblokowanie |

Jednostki to znak, słowo, wiersz, akapit i strona. Rozmiar kroku nawigacji
określają istniejące ustawienia czytnika. Jego udźwiękowione menu kontekstowe
udostępnia zakładki, właściwości, początek/koniec tekstu, ustawienia czytnika
i mowy. W tym menu obowiązuje zwykłe sterowanie listą. Pozioma oś tekstu
i pionowa oś jednostek odpowiadają czytnikowi Sansy. Krótkie naciśnięcie zmienia
jednostkę raz po zwolnieniu; przytrzymanie głośności nie nawiguje tekstu ani
jednostek. Zwolnienie przytrzymanego Next nie przesuwa tekstu naprzód.
Kombinacja wyjścia nie przesuwa również tekstu ani nie przełącza mowy.

Są to przypisania wejścia istniejącego wspólnego czytnika. Testy mapy na hoście
sprawdzają wynikowe akcje semantyczne; nie potwierdzają słyszalnej syntezy,
trasowania dźwięku, zapisu zakładek ani zachowania fizycznego odtwarzacza.

## Ustawienia wielopolowe, szybkie ustawienia i tempo

W edytorach czasu, korektora, koloru i innych wartości: krótka Głośność + / -
zwiększa / zmniejsza wartość po zwolnieniu. Play / Next wybiera poprzednie /
następne pole; Power zatwierdza lub wykonuje istniejącą operację OK edytora.
Przytrzymaj Play, aby anulować lub wyjść bez dodatkowej zmiany pola przy
zwolnieniu. Przytrzymanie głośności zmienia odsłuch, a nie edytowaną wartość.
Korektor używa OK do zmiany trybu edycji. Lista wyboru ustawienia korzysta
ze sterowania listą opisanego wcześniej. Semantyczna akcja ekranu głównego
nie wymusza zamknięcia specjalizowanego edytora, który jej nie obsługuje.

W szybkich ustawieniach krótka Głośność + / Głośność - obsługuje górne / dolne
ustawienie, Play / Next lewe / prawe, a krótki Power wychodzi. Na ekranie
wysokości dźwięku krótka Głośność + / Głośność - zmienia wysokość;
Play / Next zmniejsza / zwiększa prędkość, Power + Play
resetuje, Power + Next zmienia tryb, a krótki Power wychodzi. Zmiany prędkości
podlegają istniejącemu trybowi i ustawieniom timestretch.
W obu ekranach przytrzymanie głośności zmienia odsłuch zamiast ustawień czy
wysokości dźwięku. Istniejące akcje edytorów i kombinacji pozostają kontekstowe.

Okna potwierdzenia akceptują krótki Next lub Power. Play anuluje.
Przytrzymanie Next lub Power nigdy nie zatwierdza okna po zwolnieniu przycisku.

## Klawiatura ekranowa

Tryby dostępnego pisania opisuje `ACCESSIBILITY-TYPING-PL.md`. Przytrzymanie
Power (domyślnego Entera) kończy pisanie przy pierwszym powtórzeniu, bez dopisania
znaku przy zwolnieniu. Zwolnij go od razu: dalsze trzymanie nadal prowadzi do
dotychczasowego awaryjnego wyłączenia urządzenia.

| Przycisk | Działanie |
| --- | --- |
| Krótka Głośność + / Głośność - | W górę / dół siatki znaków po zwolnieniu |
| Przytrzymanie Głośności + / Głośności - | Zwiększenie / zmniejszenie głośności odsłuchu; bez ruchu w siatce |
| Play / Next | W lewo / prawo siatki znaków |
| Przytrzymanie Play / Next | Kursor tekstu w lewo / prawo |
| Power | Wstawienie wybranego znaku |
| Play + Next | Następna strona klawiatury |
| Power + Głośność - | Usunięcie poprzedniego znaku |
| Power + Next | Zakończenie i zatwierdzenie tekstu |
| Power + Play | Anulowanie wpisywania |
| Power + Głośność + | Blokowanie / odblokowanie |

Tryb edycji wiersza Rockboksa zachowuje dotychczasową interpretację akcji
kursora i wyboru. Klawiatura tekstowa nie ma zwykłego menu kontekstowego:
przytrzymanie Play / Next zachowuje specjalizowane akcje kursora tekstu zamiast
przypisań z menu i czytnika. Przytrzymany przycisk kursora nie przesuwa dodatkowo
wyboru w siatce przy zwolnieniu. Jawne kombinacje z Power zachowują usuwanie,
zatwierdzanie i anulowanie tekstu zamiast zwykłych znaczeń nawigacyjnych.

## Blokada i awaryjne wyłączanie

Najpierw naciśnij Power, krótko dodaj Głośność + i zwolnij oba przyciski.
Ta sama kombinacja odblokowuje. Wspólna blokada programowa wyłącza dotyk
zgodnie ze swoją standardową polityką i filtruje zwykłe akcje; zaawansowane
ustawienia blokady mogą przepuszczać wybrane akcje. Gdy podświetlenie jest
wyłączone, istniejąca obsługa blokady może najpierw obudzić ekran; w razie
potrzeby zwolnij przyciski i powtórz kombinację. Nie usuwaj przypisania
kombinacji odzyskiwania dostępu.

Zachowano istniejący sterownik oraz `POWEROFF_BUTTON = BUTTON_POWER`,
`POWEROFF_COUNT = 25`. Przytrzymanie Power żąda wyłączenia po przekroczeniu
progu powtórzeń sterownika; nie otwiera menu kontekstowego ani nie przełącza
odtwarzania po zwolnieniu. Nie jest to zmierzony czas ani gwarancja sprzętowego
resetu.

## Klawisze symulatora Windows

Osobno utrzymywana mapa wejścia SDL dla R1 używa:

| Klawisz komputera | Fizyczny przycisk R1 |
| --- | --- |
| Strzałka w górę / numeryczne 8 | Głośność + |
| Strzałka w dół / numeryczne 2 | Głośność - |
| Strzałka w prawo / Enter / numeryczny Enter | Next |
| Strzałka w lewo / Backspace | Play |
| Spacja / Insert / Escape | Power |

Do kombinacji z Power używaj Spacji lub Insert. Przytrzymanie Escape również
uruchamia ścieżkę wyłączania przez Power. Numeryczne 0 pozostaje skrótem zrzutu
ekranu. Trasowanie dotyku symulatora R1 musi przepuszczać przypisane klawisze
fizyczne zamiast zmieniać strzałki w wirtualne przyciski dotykowej siatki 3×3.
Testy mapy na hoście nie dowodzą, że konkretny plik wykonywalny symulatora
zawiera tę integrację.

## Integracja i ograniczenia

- W `apps/SOURCES` wybierz `keymaps/keymap-hibyr1.c` pod `#ifdef HIBY_R1`
  wewnątrz istniejącej gałęzi `HIBY_R3PROII_PAD`; inne urządzenia zachowują
  swoją mapę. Pozostaw `CONFIG_KEYPAD HIBY_R3PROII_PAD` dla istniejących
  wtyczek. Mapa rdzenia nie wymaga nowego ID, edycji configure ani keymaps.make.
- Zachowaj `keymap-touchscreen.c`. Nowa mapa eksportuje
  `target_get_context_mapping`; fizyczne przejścia używają `CONTEXT_CUSTOM2`.
  Czytnik R1 korzysta ze wspólnego `get_action` z kontekstem
  `CONTEXT_CUSTOM | CONTEXT_CUSTOM2 | CONTEXT_STD`, dzięki czemu istniejący
  mechanizm remapowania akcji rdzenia może nadpisywać również jego akcje
  semantyczne. Inne urządzenia zachowują dotychczasowy callback czytnika.
- Tylko R1 przechwytuje istniejące `ACTION_LIST_VOLUP` / `ACTION_LIST_VOLDOWN`
  po wspólnej obsłudze blokady i podświetlenia w `get_action` oraz
  `get_custom_action`. Każda przepuszczona akcja wywołuje `adjust_volume` raz
  i zwraca `ACTION_NONE`, więc GUI listy nie zmienia głośności po raz drugi.
  Akcje głośności WPS pozostają natychmiastowe i korzystają z istniejącej obsługi
  odtwarzania. Nie dodano akcji, API wtyczek ani układu ustawień; natywne
  remapowanie nadal poprzedza domyślne przypisania fizyczne.
- Każdy ekran udostępniający blokadę musi przekazywać `ALLOW_SOFTLOCK` do
  wspólnego API akcji. Wywołania R1 przekazują ją teraz w `apps/recorder/keyboard.c`,
  `apps/gui/quickscreen.c`, `apps/gui/color_picker.c`, `apps/menus/eq_menu.c`,
  `apps/screens.c`, `apps/gui/yesno.c` oraz `apps/plugins/pitch_screen.c`.
  Sam wpis mapy nie włącza blokady w wywołaniu bez tej flagi. Czytnik R1 ją
  przekazuje. Testy na hoście kompilują rzeczywiste wyrażenia wywołań dla R1,
  Sansy i R3 Pro II, zachowując konteksty i czasy oczekiwania innych urządzeń,
  oraz sprawdzają blokowanie, filtrowanie akcji i odblokowanie z argumentami R1.
- Wtyczki czytające surowe przyciski nadal mogą wymagać nieistniejącego
  Previous. Wymagają osobnego przeglądu i dostosowania; mapa rdzenia nie
  potwierdza ich dostępności. Edytor gestów jest we wspólnym module dostępności,
  poza mapą sprzętową; opisuje go `ACCESSIBILITY-TOUCH-PL.md`.
- Aktualny zestaw gestów we wspólnym module:
  ruch w prawo = Dół, w lewo = Góra, w górę = Lewo, w dół = Prawo,
  podwójne stuknięcie = OK, lewo–prawo = Wstecz, prawo–lewo = Ekran główny.
  Dodatkowe konfigurowalne ścieżki dwusegmentowe to góra–dół, dół–góra,
  lewo–góra, prawo–góra, góra–lewo, góra–prawo, lewo–dół i dalsze kombinacje.
  Dodatkowe ścieżki są domyślnie nieprzypisane. Eksploracja i edytor gestów należą
  do wspólnego modułu dostępności, nie do tej mapy. Kurtynę i granice jej
  awaryjnego wyłączania opisuje `ACCESSIBILITY-CURTAIN-PL.md`, a tryby pisania
  `ACCESSIBILITY-TYPING-PL.md`.
- Fizyczne kombinacje, czas wyłączania, zaawansowana blokada/podświetlenie,
  rzeczywista mowa i NVDA wymagają oddzielnej walidacji działania lub sprzętu.

Testy regresyjne uruchom w WSL albo środowisku POSIX z Pythonem 3
i kompilatorem C:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/tests/test_hiby_r1_keymap.py
HIBY_R1_KEYMAP_SANITIZE=1 PYTHONDONTWRITEBYTECODE=1 python3 tools/tests/test_hiby_r1_keymap.py
```

Natywny Unix wymaga dodatkowo bezwzględnej, zewnętrznej ścieżki
`ROCKBOX_WORK_ROOT`. Wygenerowane harnessy C i logi kompilatora pozostają
w centralnym `Workspace/hiby-r1-keymap-tests`, poza źródłami. Testy wykonują
rzeczywiste mapy R1 i dotyku, wspólny kod pobierania i wyszukiwania akcji,
blokady i podświetlenia oraz oba punkty wejścia akcji z zastępczymi usługami
platformy. Sprawdzają kolejność krótkich naciśnięć, przytrzymań i kombinacji,
przechwytywanie globalnej głośności i natywne remapowanie oraz wykonują kod
ruchu siatki klawiatury, pól czasu i dispatchu czytnika. Obsługa trybu punktowego
jest włączona. Próby punktów wejścia innych urządzeń sprawdzają, że przechwytywanie
jest wyłącznie dla R1. Testy nie budują symulatora ani wydania firmware.
