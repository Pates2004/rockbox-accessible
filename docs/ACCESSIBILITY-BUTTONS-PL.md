# Ustawienia przycisków fizycznych HiBy R1

Ustawienia → Ustawienia ogólne → System → Ustawienia przycisków fizycznych.
System zawiera kolejno ustawienia ekranu dotykowego, ustawienia przycisków
fizycznych i Dźwięki interfejsu. Wersje z dotykiem i eSpeakiem przenoszą
ustawienia ekranu dotykowego z Wyświetlacza; wersje bez eSpeaka zachowują jego
dotychczasowe położenie. Pierwszą pozycją Dostępności są nadal ustawienia
Talkbox; przeglądanie dotykowe i przypisania gestów są w Ustawienia Talkbox →
Ustawienia przeglądania dotykowego. Podmenu Ustawienia eSpeak zawiera tylko
parametry syntezy; edytor przycisków fizycznych pozostaje w Systemie.
Edytor obejmuje pięć rzeczywistych przycisków: Zasilanie, Play, Następny,
Głośność + i Głośność -. Nie pokazuje nieistniejącego przycisku Poprzedni.

Menu rozdziela **Akcje w interfejsie** oraz **Akcje na ekranie odtwarzania**.
Drugi profil działa tylko na aktywnym ekranie odtwarzania (WPS); muzyka grająca
w tle menu nie zmienia przypisań tego menu. Każde podmenu ma te same 20 pozycji
przycisk/naciśnięcie oraz reset tego profilu. W menu nadrzędnym pozostają wspólny
czas przytrzymania, reset obu profili i przewodnik po sterowaniu domyślnym.
Zmiana ekranu nie zmienia czasu przytrzymania w połowie naciśnięcia.
Oczekujące wejście jest anulowane przy zmianie kontekstu, a nie wykonywane
według przypisania z nowego ekranu.

Każdy przycisk ma pojedyncze, dwukrotne i trzykrotne naciśnięcie oraz
przytrzymanie. Czas przytrzymania przycisków wynosi domyślnie 700 ms; zakres to
300–2000 ms ze skokiem 100 ms. Jest niezależny od domyślnych 900 ms dotyku.
Okno wielokrotnego naciśnięcia fizycznego wynosi 300 ms. Własne przypisanie
dwukrotnego/trzykrotnego naciśnięcia, również jawny wybór Nieprzypisany,
rezerwuje odpowiednią liczbę kliknięć; krótsza akcja czeka, dopóki sekwencja
może być kontynuowana. Domyślne sterowanie Rockboxa dla wyższej liczby kliknięć
nie dodaje tego oczekiwania.

- Domyślne sterowanie Rockboxa zachowuje dostępny profil zależny od kontekstu,
  opisany w `HIBY-R1-CONTROLS-PL.md`, w tym natywną obsługę przytrzymania/puszczenia.
- Nieprzypisany dla dwukrotnego lub trzykrotnego naciśnięcia rezerwuje tę
  sekwencję i przechwytuje ją bez funkcji natywnej ani akcji krótszej sekwencji.
  Nie aktywuje zastępczo elementu ani nie zmienia głośności.
- Nieprzypisany dla pojedynczego naciśnięcia lub przytrzymania zachowuje własną
  funkcję. Dla głośności jest to regulacja poziomu, nie nawigacja po liście;
  pozostałe przyciski zachowują natywne przypisanie. Gdy wyższe sekwencje mają
  Domyślne sterowanie Rockboxa, zwykła regulacja głośności działa natychmiast
  zgodnie z natywną obsługą.
- Kierunki, Aktywuj, Wstecz, Menu główne i Menu kontekstowe używają semantycznych
  akcji bieżącego ekranu; nie zgadują przypisań dowolnej wtyczki.
- Wypowiedz stan baterii ogłasza procent lub nieznany stan, gdy brak odczytu.
- Podaj aktualny czas i Podaj aktualną datę respektują wspólne ustawienia mowy
  i lokalny format czasu/daty. Podaj podsumowanie mówi kolejno: bieżący utwór,
  czas, data, bateria; używa tytułu utworu, a przy jego braku nazwy pliku.
  Niedostępne pola ogłasza jako nieznane i kontynuuje pozostałe. Te akcje nie
  włączają samodzielnie mowy.
- Włącz lub wyłącz przeglądanie dotykowe pozwala przywrócić je przyciskiem
  fizycznym także przy wyłączonym przeglądaniu i mowie. Wyłączenie omija wszystkie
  gesty dostępności i dotykowe tryby pisania oraz przywraca zwykły dotyk Rockboxa.
- Otwórz skrót lub aplikację pamięta dla danego przypisania konkretną wtyczkę,
  menu Skróty albo Ekrany systemowe lub bezpośrednio Pliki, Bazę danych,
  Wznów odtwarzanie, Ustawienia albo Listy odtwarzania. Mieszczą się cztery różne ścieżki;
  wiele przypisań może współdzielić jedną bez zmieniania pozostałych.
  Pojedyncze skróty i dowolne ekrany systemowe nie mają bezpośrednich przypisań.
  Bezpośrednie cele używają zwykłej drogi powrotu z obsługiwanych list/menu
  rdzenia, odtwarzania, czytnika i ustawień. Nie wymuszają wyjścia z surowych
  wtyczek, klawiatury, pytań tak/nie ani nieznanych własnych kontekstów.
  Nieobsługiwany cel/kontekst, w tym Baza danych w kompilacji bez jej obsługi,
  powoduje komunikat „Ten ekran jest tutaj niedostępny”.
- Wyłącz urządzenie korzysta ze zwykłego zamykania Rockboxa; fizyczne
  przytrzymanie Zasilania nadal działa.
- Zablokuj lub odblokuj ekran może odblokować ekran przyciskiem fizycznym.
  Gest może go jedynie zablokować i nie omija już działającej blokady dotyku.

Własne przypisania przytrzymania mogą powtarzać sprawdzoną nawigację oraz jawne
akcje głośności: W górę/W dół na listach, wszystkie cztery kierunki czytnika,
W górę/W dół regulujące głośność muzyki i kierunkową regulację wartości
liczbowych/zmianę pól w korektorze, ustawieniach kolorów i czasu. Zwykłe
ustawienia, szybkie menu, klawiatura, pytania tak/nie i nieznane własne ekrany
nie otrzymują powtarzania kierunków. Aktywacja, Wstecz, Menu główne, Menu
kontekstowe, otwieranie celu, wyłączenie urządzenia, blokada, kurtyna,
przełączanie usług/dotyku i komunikaty pozostają jednokrotne. Powtórzenia
przycisków są niezależne od opcji powtarzania dotyku, domyślnie wyłączonej.
Domyślne sterowanie Rockboxa oraz Nieprzypisany dla pojedynczego naciśnięcia
i przytrzymania zachowują natywne powtórzenia i obsługę puszczenia, w tym
przewijanie/zakończenie przewijania, jeżeli występuje w natywnym przypisaniu.

Zasilanie + Głośność + pozostaje awaryjną kombinacją blokowania/odblokowania.
Edytor nie zastępuje istniejących kombinacji ani sprzętowego wyłączania.
Kombinacja anuluje oczekujące wielokrotne naciśnięcie i zapobiega przypadkowym
akcjom po puszczeniu jej części. Zmiana kontekstu, wejście w USB i wyłączanie
również anulują oczekujące wejście; sama aktualizacja stanu baterii lub ładowarki
tego nie robi. Wejście fizyczne anuluje oczekujące gesty dotykowe przez główną
obsługę wejścia.

Osobne akcje Włącz lub wyłącz Talkbox oraz Włącz lub wyłącz pliki głosowe
interfejsu można przypisać bezpośrednio przyciskom i gestom. Nie ma osobnego
podmenu Skrót dostępności ani wyboru jednej usługi. Stary
`/.rockbox/accessibility-shortcut.cfg` jest ignorowany i pozostaje bez zmian;
jego dawne wartości enabled/service nie wpływają na te akcje.
Wykonują się raz na rozpoznanie,
nie wielokrotnie podczas przytrzymania. Zlecają komunikat o nowym stanie również
przy wyłączonej zwykłej mowie. [Przełączanie usług](ACCESSIBILITY-SHORTCUT-PL.md)
opisuje brakujące pliki głosowe, niezależność ustawień i przyszły skrót publiczny.

Zmiany w edytorze działają próbnie przez 20 sekund; zapis wymaga potwierdzenia. Anulowanie,
upływ czasu, USB i błąd zapisu przywracają poprzednią konfigurację. Reset przycisków
przywraca skompilowane przypisania bez kasowania gestów i zakresu dźwięków;
Reset dotyku przywraca przypisania dotykowe, czas 900 ms i wyłączone powtarzanie;
zachowuje przypisania przycisków, ich czas przytrzymania, źródła dźwięków
i ścieżki wtyczek nadal używane przez przyciski.

Przypisana akcja Włącz lub wyłącz przeglądanie dotykowe zapisuje zmianę
bezpośrednio i atomowo, bez próby z potwierdzeniem. Błąd zapisu zachowuje
poprzedni stan. Podczas trwającej próby przypisań nie wykonuje się i nie
zapisuje niepotwierdzonych zmian. Gest może wyłączyć przeglądanie, a przypisanie
fizyczne lub menu pozwala je ponownie włączyć; sterowanie awaryjne pozostaje dostępne.

System → Dźwięki interfejsu reguluje wspólną siłę i powtórzenia. Przyciski fizyczne,
rozpoznane gesty i eksplorację dotykową można wybierać niezależnie, także żadne
albo wszystkie trzy źródła. Nowy profil wybiera wszystkie trzy; dotychczasowy
wybór źródeł pozostaje zachowany.
Wyłącz wycisza dźwięki niezależnie od źródła.
Osobne ustawienia czasu przytrzymania/powtarzania dotyku oraz dźwięki opisuje
`ACCESSIBILITY-TOUCH-PL.md`. Prywatny `accessibility.cfg` ma teraz format
`RBACCESSIBILITY:11`. Pliki v1–v10 zachowują przypisania i historyczne znaczenie
sterowania systemowego; brakujące pola/gesty otrzymują wartości domyślne.
Dotychczasowe maski źródeł 1/2/3 zachowują znaczenie. V8 wprowadził maski 0–7
i ustawienia wysokości kliku na pustym obszarze, domyślnie włączone
ze zmianą o -4 półtony. Sam odczyt nie zmienia pliku. Kolejny potwierdzony zapis
albo bezpośrednie przełączenie przeglądania zapisuje v11 atomowo. V9 wprowadził
osobne przypisania interfejsu i ekranu odtwarzania, ze wspólnym czasem
przytrzymania i czterema ścieżkami wtyczek. Przypisania v1–v8 i ich cele
kopiowane są do obu profili w pamięci, zachowując dotychczasowe działanie
globalne. Następnie można zmieniać każdy profil niezależnie. Reset dotyku
zachowuje oba profile przycisków oraz nadal używane przez nie ścieżki wtyczek.
W celu ręcznego odzyskania zatrzymaj Rockboxa i zmień nazwę tego pliku;
nie modyfikuj go podczas działania programu.

V10 zapisuje także dwa niezależne profile gestów. Osobne profile przycisków
z v9 pozostają niezależne; kopiowania do obu wymagają tylko przypisania v1–v8.

V11 dodaje skrót grupy usług oraz cztery akcje początku/końca listy lub strony.
Fabryczne trzykrotne Power wywołuje grupę w obu profilach; zapisane przypisania
pozostają bez zmian. Domyślna grupa obejmuje Talkbox i przeglądanie dotykowe.
Zobacz `ACCESSIBILITY-SHORTCUT-PL.md` i `ACCESSIBILITY-LISTS-PL.md`. Rezerwacja
trzykrotnego naciśnięcia opóźnia krótsze sekwencje Power o dotychczasowe 300 ms.

Opis dotyczy bieżących źródeł v11, nie akceptacji konkretnego wydania.
To obsługa wspólnego rdzenia, nie uniwersalne mapowanie surowych przycisków wtyczek.
Niektóre wtyczki wymagają osobnych adapterów. Testy hosta i klawiatury/PCM Windows
nie potwierdzają działania przycisków, dotyku, Bluetooth, NVDA/UI Automation ani
wydajności baterii na rzeczywistym R1.
