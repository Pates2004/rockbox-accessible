# Dostępny dotyk

Ogólne ustawienia dotyku są teraz w Ustawienia → Ustawienia ogólne → System →
Ustawienia ekranu dotykowego. Przypisania gestów są w Dostępność → Ustawienia
Talkbox → Ustawienia przeglądania dotykowego.
W Systemie jest programowa Czułość gestów dotykowych: 50–200%, domyślnie 100%.
Większa wartość oznacza krótszy ruch potrzebny do gestu. Zmienia progi ruchu
gestów i klawiatury, nie czułość sprzętową czujnika ani siłę nacisku. Obecny
sterownik nie udostępnia regulacji nacisku. Zapis działa od razu i nie przesuwa
obszarów przycisków na ekranie.

System → Dźwięki interfejsu zawiera wszystkie osiem kombinacji przycisków,
gestów i eksploracji, łącznie z Brak i Wszystkie. Nowy profil wybiera Wszystkie;
stare zapisane źródła zachowują znaczenie. Główna siła dźwięku Wyłącz nadal
wycisza wszystkie źródła. Eksploracja klika przy nowym celu lub kontakcie,
nie przy drganiu współrzędnych na tym samym elemencie. Puste miejsce domyślnie
ma inną wysokość: -4 półtony, czyli dwa tony niżej. Można wybrać od -12 do +12
półtonów albo wyłączyć różnicę wysokości; wtedy puste miejsce wydaje zwykły
dźwięk zamiast milczeć. Konfiguracja wejścia zapisuje wersję v11 i odczytuje v1–v10.

Wspólna funkcja wymaga ekranu dotykowego i zintegrowanego eSpeaka. Domyślnie
jest włączona na HiBy R1, a wyłączona na pozostałych obsługiwanych urządzeniach.
Wejście: Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox → Ustawienia przeglądania dotykowego.
Pierwszą pozycją Dostępności są ustawienia Talkbox. Przyciski fizyczne R1 mają
osobną sekcję opisaną w `ACCESSIBILITY-BUTTONS-PL.md`.
Przyciski fizyczne pozostają dostępne, również podczas zmieniania gestów.
Kolejność pozycji w Ustawieniach przeglądania dotykowego: Przeglądanie dotykowe,
Przypisania gestów, Czas przytrzymania na ekranie, Powtarzaj akcje gestów po
przytrzymaniu, Zgłaszaj puste miejsca podczas eksploracji dotykowej,
Inna wysokość dźwięku pustych miejsc, Wysokość dźwięku dla pustych miejsc,
Ustawienia domyślne. Tryb zgłaszania pustych miejsc i oba ustawienia wysokości
są razem tutaj; nie są powielone w System → Dźwięki interfejsu.

## Profile interfejsu i odtwarzania

Przypisania gestów otwierają dwa profile: Akcje w interfejsie oraz Akcje na
ekranie odtwarzania. Każdy ma 20 przypisań i przywracanie ustawień domyślnych
tylko tego profilu. Drugi działa wyłącznie na aktywnym ekranie odtwarzacza.
Muzyka grająca w tle nie zmienia gestów menu. Eksploracja, zgłaszanie pustych
miejsc, czas przytrzymania dotyku i powtarzanie gestów pozostają wspólne.

Przy odczycie v1–v9 dotychczasowe gesty i cele uruchamiania są kopiowane do
obu profili w pamięci, bez zapisywania pliku. Dalej można zmieniać je osobno.
Reset jednego profilu zachowuje drugi i jego odwołania do wtyczek. Główny reset
przeglądania dotykowego przywraca oba profile gestów, zachowując oba profile
przycisków. Zmiana ekranu anuluje niedokończony gest zamiast zastosować do niego
przypisanie z następnego ekranu.

## Domyślne gesty

| Gest | Działanie logiczne |
| --- | --- |
| W prawo | W dół / następny element listy |
| W lewo | W górę / poprzedni element listy |
| W górę | W lewo / wstecz |
| W dół | W prawo / wejście |
| Dwukrotne stuknięcie w dowolnym miejscu | Aktywacja bieżącego elementu |
| Trzykrotne stuknięcie w dowolnym miejscu | Nieprzypisany: przechwycenie bez aktywacji |
| Dwukrotne stuknięcie z przytrzymaniem drugiego dotknięcia | Menu kontekstowe bieżącego elementu |
| Przytrzymanie pojedynczego dotknięcia | Nieprzypisany |
| W lewo, potem w prawo bez odrywania palca | Wstecz |
| W prawo, potem w lewo bez odrywania palca | Menu główne |

Edytor obejmuje 20 przypisań: cztery pojedyncze kierunki, wszystkie dwanaście
uporządkowanych par różnych kierunków, dwukrotne stuknięcie, pojedyncze
przytrzymanie, trzykrotne stuknięcie oraz dwukrotne stuknięcie z przytrzymaniem. Dla
każdego można wybrać Nieprzypisany, W górę, W dół, W lewo, W prawo, Aktywuj,
Wstecz, Menu główne, Menu kontekstowe, Zwiększ głośność, Zmniejsz głośność,
Wypowiedz stan baterii, Otwórz skrót lub aplikację, Wyłącz urządzenie,
Zablokuj lub odblokuj ekran, Podaj aktualny czas, Włącz lub wyłącz Talkbox,
Włącz lub wyłącz pliki głosowe interfejsu, Włącz lub wyłącz przeglądanie
dotykowe, Podaj aktualną datę oraz Podaj podsumowanie. Kurtyna ekranu jest
dostępna w przypisaniach, gdy obsługuje ją sterownik wyświetlacza.
Gest przeglądania dotykowego może jedynie zablokować ekran, nigdy go
odblokować. Odblokuj go przyciskami Zasilanie + Głośność w górę lub własnym
przypisaniem fizycznym.
Opcjonalne przypisania wybudzania w Systemie są odrębne od gestów czytnika;
opisują je [zasady ekranu](ACCESSIBILITY-SCREEN-PL.md).
Pozostałe pary i pojedyncze przytrzymanie domyślnie są Nieprzypisane.
Rozpoznany gest Nieprzypisany jest przechwytywany bez
działania: nie przechodzi do zwykłej obsługi dotyku i nie zamienia się w
stuknięcie ani aktywację. Odczyt pojedynczym stuknięciem i świadoma eksploracja
są odrębnymi interakcjami, nie zastępczym działaniem nieprzypisanego gestu.

Czas przytrzymania na ekranie wynosi domyślnie 900 ms; zakres to 300–2000 ms
ze skokiem 100 ms. Obejmuje przypisane pojedyncze przytrzymanie, dwukrotne
stuknięcie z przytrzymaniem i oczekiwanie na nieruchomym końcu powtarzanego
gestu. Czas przytrzymania przycisków fizycznych jest niezależny. Nieprzypisane
pojedyncze przytrzymanie wyłącza ten gest, ale nie dwukrotne stuknięcie
z przytrzymaniem.
Po przypisaniu przytrzymania nieruchomy palec czeka na ten gest; porusz palcem,
aby rozpocząć eksplorację zamiast pozostawiać go bez ruchu.

Pojedyncze krótkie stuknięcie odczytuje lub wybiera dotknięty element, ale go
nie uruchamia. Komunikat czeka na koniec okna następnego stuknięcia: 320 ms
od puszczenia palca. Kolejne dotknięcie może nastąpić w dowolnym miejscu ekranu
w tym czasie. Po puszczeniu drugiego krótkiego stuknięcia aktywacja czeka
jeszcze 320 ms na ewentualne trzecie. To okno jest zawsze zarezerwowane, także
gdy Trzykrotne stuknięcie jest Nieprzypisane: trzy stuknięcia niczego wtedy nie
wykonują, również nie aktywują wcześniej dwukrotnego stuknięcia. Dwukrotne
stuknięcie działa na bieżącym fokusie, nawet jeśli drugie jest gdzie indziej.

Aby wykonać dwukrotne stuknięcie z przytrzymaniem, puść pierwsze dotknięcie,
dotknij ponownie w tym samym oknie 320 ms i trzymaj drugi dotyk nieruchomo
przez ustawiony czas przytrzymania. Działanie następuje raz i przechwytuje
puszczenie palca, bez dodatkowego dwukrotnego lub trzykrotnego stuknięcia.
Domyślne Menu kontekstowe otwiera menu bieżącego elementu listy, muzyki lub
czytnika, gdzie jest obsługiwane. W klawiaturze, pytaniach tak/nie i nieobsługiwanych
własnych ekranach Menu kontekstowe tego gestu jest przechwytywane bez usuwania
znaku ani potwierdzania/anulowania pytania. Dotychczasowe jawne przypisania
Menu kontekstowego innym gestom i przyciskom zachowują wcześniejsze znaczenie.

Aby eksplorować, przytrzymaj palec około 220 ms, potem przesuwaj go bez
odrywania. Eksploracja nie aktywuje elementów. Puste obszary mogą mówić
„Brak elementu”, jeżeli dany ekran udostępnia
semantyczne rozpoznawanie elementów pod palcem.

Działania zależą od ekranu: podczas słuchania muzyki W lewo/W prawo zmieniają
utwór, Aktywuj wstrzymuje lub wznawia, a W górę/W dół zmieniają głośność.
W czytniku tekstu W górę/W dół wybierają poprzednią/następną jednostkę czytania,
W lewo/W prawo przemieszczają się o tę jednostkę, Aktywuj wstrzymuje lub
wznawia, a Menu kontekstowe otwiera menu tekstu. W ustawieniach W górę/W dół
zwiększają lub zmniejszają wartość, a W lewo/W prawo zmieniają pole. W
klawiaturze kierunki przesuwają kursor znaków, Aktywuj wybiera znak, Wstecz
anuluje, Menu główne kończy wpisywanie, a Menu kontekstowe usuwa znak.

## Powtarzanie przytrzymanego gestu

Powtarzaj akcje gestów po przytrzymaniu jest domyślnie wyłączone. Po włączeniu
narysuj pełny gest jednego lub dwóch kierunków, a następnie trzymaj palec
nieruchomo na jego końcu. Po ustawionym czasie przytrzymania dozwolony gest
może wykonać pierwszą akcję bez puszczania palca, a następnie powtarzać ją
co 160 ms. Puszczenie kończy powtarzanie bez dodatkowej akcji. Ruch po rozpoczęciu
powtarzania, zmiana ekranu/kontekstu, wejście fizyczne, blokada lub wyłączenie
przeglądania dotykowego anulują je. Dotyk należący do dwukrotnego stuknięcia
z przytrzymaniem nie może równocześnie rozpocząć powtarzania gestu.

Powtarzane są tylko sprawdzone działania: W górę/W dół na listach, wszystkie
cztery kierunki czytnika, W górę/W dół regulujące głośność w odtwarzaniu muzyki,
kierunkowa regulacja wartości liczbowych/zmiana pól w korektorze, ustawieniach
kolorów i czasu oraz jawne akcje głośności. Zwykłe ustawienia, szybkie menu,
klawiatura, pytania tak/nie i nieznane własne ekrany nie otrzymują powtarzania
kierunków. Aktywacja, Wstecz, Menu główne, Menu kontekstowe, otwieranie celu,
wyłączanie urządzenia, blokada, kurtyna, przełączanie usług/dotyku i komunikaty
głosowe wykonują się jednokrotnie. Pozostałe gesty zachowują zwykłe działanie
po puszczeniu lub eksplorację; samo przytrzymanie nie zezwala na ich powtarzanie.

## Bezpieczne zmiany

Wybierz Przypisania gestów, gest i jego działanie. Zmiana działa próbnie przez
20 sekund, ale nie jest jeszcze zapisana. Potwierdź „Zachować je?”, aby zapisać.
Anulowanie, upływ czasu, wejście w USB lub błąd zapisu przywracają poprzednie
przypisania i anulują oczekujące dotknięcia. Tak samo zabezpieczone są
włączanie i wyłączanie przez menu, czas przytrzymania, powtarzanie oraz
Ustawienia domyślne. Reset dotyku przywraca domyślne gesty, czas 900 ms
i wyłączone powtarzanie; zachowuje przypisania i czas przycisków fizycznych,
wybór źródła dźwięków oraz ścieżki wtyczek nadal używane przez przyciski.
Po potwierdzeniu przywraca też tryb Tylko dźwięk dla pustych miejsc. Są to dwa
osobne pliki ustawień: gdy nie powiedzie się tylko drugi zapis, sterowanie
pozostaje przywrócone, wcześniejszy tryb pustych miejsc nadal działa, a komunikat
informuje o częściowym przywróceniu. Nie jest to wspólna transakcja obu plików.
Potwierdzenie lub anulowanie przyciskami
fizycznymi działa także po usunięciu potrzebnych przypisań dotykowych.

Własne ekrany wtyczek i wtyczki odczytujące surowe przyciski nie zyskują
automatycznie elementów dotykowych. We własnych kontekstach akcji wtyczek
dostępny dotyk jest przechwytywany bez zgadywania przypisań; wyjdź przyciskami.

Nieprzypisany gest nie wykonuje przypisanej akcji. W przyciskach fizycznych
Nieprzypisany dla dwukrotnego/trzykrotnego naciśnięcia rezerwuje tę sekwencję
i przechwytuje ją bez funkcji natywnej ani akcji krótszego naciśnięcia.
Nieprzypisany dla pojedynczego naciśnięcia/przytrzymania zachowuje własną
funkcję, w tym samą regulację głośności. Domyślne sterowanie Rockboxa zachowuje
natywne dostępne sterowanie bez dodawania oczekiwania na wielokrotne naciśnięcie.
Są to ustawienia odrębne od wtyczki Key Remap.

Włącz lub wyłącz przeglądanie dotykowe można przypisać gestowi lub przyciskowi.
Zapisuje zmianę bezpośrednio i atomowo, bez próby 20-sekundowej; błąd zapisu
zachowuje wcześniejszy stan. Podczas trwającej próby przypisań ta akcja jest
pomijana, aby nie zapisać niepotwierdzonych zmian. Wyłączone przeglądanie omija
wszystkie gesty dostępności i dotykowe tryby pisania oraz przywraca zwykły tryb
dotyku Rockboxa. Gest może je wyłączyć; włącz je ponownie przypisanym przyciskiem
lub przez menu. Sterowanie fizyczne i kombinacje awaryjne pozostają dostępne
także przy wyłączonym przeglądaniu dotykowym i mowie.

Podaj aktualną datę korzysta z lokalnego formatu daty. Podaj podsumowanie mówi
kolejno: bieżący utwór, czas, data, bateria. Używa tytułu utworu, a przy jego
braku nazwy pliku. Niedostępne pola ogłasza jako nieznane i kontynuuje pozostałe.
Czas, data, bateria i podsumowanie respektują wspólne ustawienia dostępności
mowy; nie włączają samodzielnie mowy.

Po wybraniu Otwórz skrót lub aplikację wybierasz cel przed potwierdzeniem.
Każde przypisanie pamięta własny cel: konkretną wtyczkę, menu Skróty lub Ekrany
systemowe albo bezpośrednio Pliki, Bazę danych, Wznów odtwarzanie, Ustawienia
lub Listy odtwarzania. Można przypisać cztery różne ścieżki wtyczek i używać
tej samej w wielu gestach/przyciskach; edytor wypowiada przypisany cel.
Pojedyncze skróty i dowolne ekrany systemowe nie mają bezpośrednich przypisań.
Bezpośrednie cele opuszczają obsługiwane listy/menu rdzenia, odtwarzanie,
czytnik i ustawienia zwykłą drogą powrotu z ekranu. Nie wymuszają wyjścia
z surowych wtyczek, klawiatury, pytań tak/nie ani nieznanych własnych kontekstów.
Nieobsługiwany cel/kontekst, w tym Baza danych w kompilacji bez jej obsługi,
powoduje komunikat „Ten ekran jest tutaj niedostępny”.

System → Dźwięki interfejsu → Dźwięki interfejsu dla obejmuje dowolną kombinację
przycisków, gestów i eksploracji: osiem wyborów łącznie z Brak i Wszystkie.
Nowy profil używa Wszystkie oraz średniej siły; zapisane wcześniej źródła i siła
pozostają bez zmian. Wyłącz wycisza wszystkie źródła. Rozpoznany gest daje jeden
dźwięk, a eksploracja klika przy zmianie celu lub nowym kontakcie, nie przy każdym
przesunięciu współrzędnych. Powtarzane gesty i przyciski respektują opcję dźwięku
powtórzeń. Nieprzypisany gest może nadal dawać ten opcjonalny dźwięk.

W Ustawieniach przeglądania dotykowego opcja **Zgłaszaj puste miejsca podczas
eksploracji dotykowej** ma trzy wybory: **Tylko dźwięk** (domyślnie),
**Dźwięk i mowa** oraz **Tylko mowa**. Dźwięk wymaga włączonych dźwięków
interfejsu i wybranej eksploracji w ich źródłach. Tylko dźwięk przy wyciszonych
dźwiękach nie zgłasza niczego; tryb mowy nie uruchamia wyłączonego eSpeaka.
Pusty obszar nie powtarza komunikatu przy drganiu palca. Zajęte elementy nadal
są odczytywane normalnie. **Wysokość dźwięku dla pustych miejsc** pozostaje
osobnym ustawieniem w tym samym menu przeglądania dotykowego; domyślnie odróżnia je o cztery
półtony w dół, jeżeli rozróżnienie wysokości jest włączone.

## Zapis i ograniczenia

Konfiguracja jest niezależna od zwykłych ustawień Rockboxa. Na odtwarzaczu
znajduje się w `/.rockbox/accessibility.cfg`, a w symulatorze we własnych danych
`.rockbox` obok programu. Ta generacja wymaga zgodnych modułów wtyczek ABI
`0xe006`. Format `RBACCESSIBILITY:11` zapisuje włączenie, źródła dźwięków, osobne
czasy przytrzymania przycisków i dotyku, powtarzanie, osobne przypisania gestów
i przycisków dla interfejsu i ekranu odtwarzania, cztery ograniczone ścieżki aplikacji oraz
rozróżnienie wysokości pustych miejsc. Osobny `empty-feedback.cfg` pamięta tryb
sygnalizacji pustych miejsc; ładowanie nie przepisuje ustawień przycisków.
Starsze pliki v1–v10 są migrowane przy kolejnym potwierdzonym zapisie. Globalne
przypisania fizyczne v1–v8 kopiowane są do obu profili w pamięci, zachowując poprzednie
działanie do czasu zmiany przez użytkownika. Osobne profile przycisków z v9
pozostają niezależne. Stare
przypisanie systemowe przycisku nie staje się kurtyną, czasem, przełączaniem
usług ani dotyku. Sam odczyt starszego pliku nie zapisuje go ponownie.
Niezależne akcje mowy/plików głosowych opisuje
[przełączanie usług](ACCESSIBILITY-SHORTCUT-PL.md).
Nieznana wersja, błędny, zbyt duży, niepełny plik lub wartości spoza zakresu
przywracają czyste ustawienia docelowe, nigdy częściowe przypisania.
Pełna bieżąca konfiguracja R1 mieści się w limicie 4096 bajtów także przy
czterech ścieżkach wtyczek o maksymalnej długości.
Potwierdzone zmiany i bezpośrednie przełączanie przeglądania dotykowego tworzą
sąsiedni plik tymczasowy; sprawdzane są zapis, synchronizacja i zamknięcie,
potem następuje atomowa zmiana nazwy. Błąd zapisu nie zastępuje poprzedniego pliku.

W razie potrzeby ręcznego odzyskania sterowania zatrzymaj Rockboxa i zmień
nazwę `accessibility.cfg`, zachowując go jako kopię. Kolejny start użyje
domyślnych przypisań. Nie edytuj pliku podczas działania programu. Wyłączenie
dostępności przywraca zwykły tryb dotyku Rockboxa. Włączona dostępność wymaga
trybu punktowego do eksploracji.

Starsze aplikacje nie rozumieją v11. Przy powrocie do starej wersji przywróć jej
pasującą konfigurację albo zachowaj plik v11 przez zmianę nazwy i użyj ustawień
domyślnych. Nie ma cichej konwersji tracącej niezależne profile.

V11 ma osobne akcje przejścia na początek/koniec całej listy lub bieżącej strony.
Fabryczne gesty w górę, a potem w dół oraz w dół, a potem w górę wybierają skrajne
pozycje całej listy. Zapisane przypisania pozostają bez zmian. Szczegóły:
`ACCESSIBILITY-LISTS-PL.md`.

Opis dotyczy bieżących źródeł v11, nie akceptacji konkretnego wydania.
To funkcja wspólnego rdzenia, nie Android TalkBack ani interfejs NVDA/UI
Automation. Kompilowane testy hosta są odrębne od kompilacji natywnych, prób
mówiącego interfejsu i dostrojenia prawdziwego ekranu dotykowego. Własnego
rysowanego ekranu bez semantycznych elementów samo rozpoznawanie gestów nie
uczyni eksplorowalnym. Testy hosta nie potwierdzają użyteczności, opóźnień ani
doboru progów na fizycznym R1.
