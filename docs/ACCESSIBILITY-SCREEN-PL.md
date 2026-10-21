# Zgłaszanie stanu ekranu i podawanie czasu

## Blokada dotyku a przyciski

Ustawienia → Ustawienia ogólne → System → Ustawienia ekranu dotykowego zawierają
dwie niezależne opcje, domyślnie wyłączone: Odblokowywanie dowolnym przyciskiem
fizycznym i Pozwalaj na używanie przycisków fizycznych przy zablokowanym ekranie.
Nie dodają kolejnego
zegara automatycznej blokady ani nie nadpisują ustawień blokady selektywnej.

Odblokowanie wymaga świeżego naciśnięcia przycisku fizycznego. Dotyk, stare
powtórzenia, puszczenie przycisku ani zdarzenie systemowe nie odblokują ekranu
za pomocą tej zasady przycisków fizycznych.
Kontakt użyty do odblokowania jest przechwytywany, aby nie uruchomił dodatkowo
bieżącego elementu. Systemowe wyłączenie, USB i odzyskiwanie kurtyny pozostają
dostępne. Gdy włączona jest tylko druga opcja, przyciski działają według swoich
przypisań, ale dotyk i gesty nadal są zablokowane; nie pada komunikat o odblokowaniu.
Gdy obie opcje są włączone, pierwszeństwo ma odblokowanie dowolnym przyciskiem.
Preferencje zapisują się atomowo w `/.rockbox/accessibility-lock.cfg`, oddzielnie
od dotychczasowych ustawień komunikatów.

## Wybudzanie i odblokowywanie dotykiem

System → Ustawienia ekranu dotykowego → Wybudzanie i odblokowywanie ekranu ma
osobne przypisania: Jedno stuknięcie, Dwukrotne stuknięcie i Trzykrotne stuknięcie.
Każde jest domyślnie wyłączone. Można wybrać Tylko włącz podświetlenie albo
Wybudź i odblokuj ekran. Działa to niezależnie od przeglądania dotykowego i mowy,
tylko gdy podświetlenie jest zgaszone lub ekran Rockboxa jest zablokowany.
Zwykłe sterowanie na jasnym, odblokowanym ekranie pozostaje bez zmian.

Cała sekwencja jest przechwytywana i nie aktywuje elementu pod palcem. Jedno
i dwa stuknięcia czekają na przerwę 320 ms, aby mogło nadejść kolejne.
Wyłączone przypisanie dwóch lub trzech stuknięć nic nie robi i nie zastępuje
go akcją mniejszej liczby stuknięć. Ruch przekraczający próg czułości, przytrzymanie
ponad 300 ms, przycisk fizyczny lub zmiana kontekstu ekranu anulują sekwencję.
Samo podświetlenie zachowuje blokadę. Odblokowanie używa zwykłej zmiany stanu
i wybranego komunikatu. Żadna z tych opcji nie wyłącza kurtyny; nadal działa
jej fizyczny skrót awaryjny.

`/.rockbox/touch-wake.cfg` zapisuje trzy wybory atomowo, osobno od ustawień
czytania, gestów i komunikatów blokady. Uszkodzone dane oznaczają bezpieczny
powrót do Wyłącz. Przy wyłączonych przypisaniach pozostaje dotychczasowa obsługa
dotyku i podświetlenia. Włączenie wybudzania utrzymuje dotyk przy blokadzie,
co może kosztować baterię; nie podajemy niezmierzonej oszczędności energii.
Krótki zegar działa tylko między stuknięciami, a nie bezczynnie ani przy
trzymanym lub utraconym kontakcie.

To obsługa podświetlenia i programowej blokady aplikacji. Nie włącza całkowicie
wyłączonego odtwarzacza i nie obiecuje wybudzenia z głębokiego uśpienia jądra.
Dostarczanie dotyku przez kernel, zachowanie w kieszeni, czasy na sprzęcie
i zużycie baterii wymagają jeszcze próby na fizycznym R1.

## Komunikaty

Otwórz **Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox → Ustawienia ekranu → Zgłaszanie stanu ekranu**.
Ustawienia ekranu grupują kurtynę i komunikaty, bez jasności ani sprzętowych
ustawień blokady. Pierwszą pozycją Dostępności są Ustawienia Talkbox; ich
podmenu Ustawienia eSpeak zawiera wyłącznie parametry syntezy. Ustawienia
ekranu znajdują się obok niego, wewnątrz Ustawień Talkbox.

Podmenu jest dostępne w kompilacjach ze zintegrowanym eSpeakiem i programową
blokadą klawiszy (`HAVE_ESPEAK` bez `HAS_BUTTON_HOLD`), również bez ekranu
dotykowego. Sprzętowy przełącznik Hold nie należy do tej funkcji. Podmenu
zawiera wyłącznie dwa wybory komunikatów. Ustawienia przycisków fizycznych
i ogólne ustawienia ekranu dotykowego należą do Systemu. Zaawansowana blokada
klawiszy nadal jest w Systemie, a czasy podświetlenia w Ekran → Ustawienia
wyświetlacza. Usunięto tylko dodatkowe odnośniki do tych samych ustawień,
nie ich wartości ani pierwotne pozycje.

## Wybór komunikatów

**Komunikat przy odblokowaniu ekranu** ma sześć opcji. Indeks oznacza wartość
zapisywaną w prywatnym pliku ustawień komunikatów; wartością domyślną jest 0.

| Indeks | Opcja | Komunikat |
| --- | --- | --- |
| 0 | Powiedz ekran odblokowany | Ekran odblokowany (domyślnie) |
| 1 | Podaj aktualny czas | Aktualny czas |
| 2 | Wypowiedz stan baterii | Stan baterii |
| 3 | Podaj czas i stan baterii | Aktualny czas, następnie stan baterii |
| 4 | Podaj stan ekranu, czas i stan baterii | Ekran odblokowany, następnie aktualny czas i stan baterii |
| 5 | Nic nie mów | Bez komunikatu przy odblokowaniu |

**Komunikat przy blokowaniu ekranu** ma dwie opcje:

| Indeks | Opcja | Komunikat |
| --- | --- | --- |
| 0 | Powiedz ekran zablokowany | Ekran zablokowany (domyślnie) |
| 1 | Nic nie mów | Bez komunikatu przy blokowaniu |

Opcje dotyczą rzeczywistych zmian stanu blokady programowej. Przyciemnienie,
wyłączenie podświetlenia ani przełączenie kurtyny nie oznacza zablokowania lub
odblokowania ekranu. Komunikaty korzystają ze zwykłego mechanizmu mowy interfejsu.
Opcja **Nic nie mów** wyłącza dany komunikat zmiany stanu, zachowując pozostałą
mowę interfejsu.

Akcja **Podaj aktualny czas** jest również dostępna w dotychczasowych edytorach
przypisań gestów i przycisków fizycznych na urządzeniach udostępniających te
edytory. Korzysta z istniejącego zegara i ustawionego formatu 12- lub
24-godzinnego; nie podaje daty. Przy braku zegara lub nieprawidłowej godzinie
podaje **Nieznane**; tak samo sygnalizuje niedostępny stan baterii. Nie zastępuje
brakujących danych wymyśloną wartością.

W edytorach przypisań są też akcje **Podaj aktualną datę** oraz **Podaj
podsumowanie**. Podsumowanie czyta tytuł utworu (lub nazwę pliku), aktualny czas,
datę i stan baterii. Czas i data pochodzą z jednego odczytu zegara. Brak utworu
lub prawidłowego zegara sygnalizuje jako **Nieznane** w odpowiedniej części.
Przy szybkim przełączaniu utworów wybór odtwarzania może już wskazywać następny
utwór; nie jest to identyfikacja aktualnie słyszalnej próbki dźwięku.
Te akcje korzystają ze zwykłego ustawienia mowy interfejsu, nie z wymuszonego
komunikatu przełączania usług. Nie zmieniają odtwarzania, zegara ani stanu baterii.

Jeżeli komunikat przerwie czytanie pliku tekstowego, anulowany fragment nie
jest uznawany za przeczytany. Czytnik zachowuje usłyszane miejsce i po komunikacie
wznawia od niego odczyt; ostatnie słowo może się powtórzyć. Czytnik wstrzymany
przez użytkownika pozostaje wstrzymany. Także zakładka utworzona po komunikacie
korzysta z zachowanego miejsca, a nie z końca anulowanego fragmentu.

## Automatyczna blokada po bezczynności

W kompilacji ze zintegrowanym eSpeakiem, ekranem dotykowym i bez sprzętowego
Hold otwórz **Ustawienia → Ustawienia ogólne → System → Ustawienia ekranu
dotykowego → Automatyczna blokada ekranu po bezczynności**. To nie jest jasność
ani czas podświetlenia. Jeden mechanizm blokady ma rozłączne tryby:

- **Zgodnie z zaawansowaną blokadą klawiszy** (`-1`, domyślnie): zachowuje
  dotychczasowe działanie opisane poniżej. Wyłączona stara blokada pozostaje
  wyłączona także w czystym profilu.
- **Wył.** (`0`): nie blokuje automatycznie, nawet jeżeli zaznaczono stare flagi
  automatycznej blokady. Blokada ręczna nadal działa.
- **5, 10, 15, 30, 45, 60, 120, 180, 300 lub 600 sekund**: blokuje po wybranej
  bezczynności, bez dodatkowego włączania dwóch starych flag. Podświetlenie,
  ładowanie i kurtyna nie zmieniają tego czasu. Inny zapisany czas z zakresu
  1–600 sekund również pozostaje do wyboru bez zaokrąglania.

Wybrany czas zastępuje stary termin blokady. Nie tworzy drugiego wątku, zegara
okresowego ani konkurencyjnej blokady. Przyjęte naciśnięcia przycisków i kontakty
dotykowe rozpoczynają czas od nowa. Zdarzenia systemowe, odświeżanie ekranu,
muzyka, mowa, oczekiwanie na gest, osierocone puszczenia i odrzucone wejście
nie są aktywnością. Powtarzanie akcji zachowuje własny znacznik czasu.
Udana zmiana czasu rozpoczyna pełny nowy okres przy następnym pobraniu akcji;
nie odblokowuje już zablokowanego ekranu. Nieudany zapis i przerwanie menu
przez USB nie zmieniają aktywnej polityki. Blokowanie wymaga znanej fizycznej
kombinacji odblokowania. Wyjątki dla wybranych akcji nadal działają, ale stare
flagi uzbrajania nie uruchamiają ani nie przełączają dodatkowego zegara przy
wybranym czasie lub opcji Wył.

Dla trybu **Zgodnie z zaawansowaną blokadą klawiszy** otwórz **Ustawienia →
Ustawienia ogólne → System → Zaawansowana blokada klawiszy**:

1. Ustaw **Włączone** na **Tak**.
2. Otwórz **Ustawienia** i zaznacz **Automatyczna blokada włączona**
   (`SEL_ACTION_AUTOLOCK`).
3. Zaznacz **Zawsze automatycznie blokuj** (`SEL_ACTION_ALWAYSAUTOLOCK`), aby
   automatyczna blokada była uzbrojona bez ręcznego uruchamiania poleceniem
   blokady. Wyjdź z menu zaawansowanej blokady, aby zastosować wybór. Bez tej
   flagi zwykłe polecenie blokady uzbraja lub rozbraja automatyczną blokadę.
4. Przejdź do **Ekran → Ustawienia wyświetlacza** i w pozycji **Podświetlenie**
   wybierz dodatni czas. Jeśli jest dostępne,
   skonfiguruj także **Podświetlenie w trakcie ładowania**: podczas podłączenia
   zasilania zewnętrznego to ustawienie zastępuje zwykły czas.

Istniejące ustawienia `global_settings.backlight_timeout`
i `global_settings.backlight_timeout_plugged` pozostają w menu
**Ekran → Ustawienia wyświetlacza**. Tylko tryb zgodny ze starą blokadą używa
aktywnego czasu podświetlenia do dotychczasowego mechanizmu blokady. Mierzy
bezczynność wejścia, nie faktyczny moment zgaśnięcia światła. **Wył.** (ujemny
czas) oraz **Wł.** / zawsze włączone
(czas zerowy) wyłączają licznik automatycznej blokady. Aby go używać, wybierz
dodatnią liczbę sekund.

Blokada programowa chroni wejście. Jest niezależna od kurtyny i jasności
wyświetlacza; sama nie gwarantuje czarnego ekranu ani oszczędności energii.
Na HiBy R1 fizyczny skrót **Power + Głośność +** blokuje lub odblokowuje ekran.
Gest czytnika może go zablokować, ale nie odblokuje już zablokowanego ekranu.
Awaryjny skrót kurtyny **Power + Next** ma inne zadanie: przywraca widoczny obraz.

Automatyczna blokada działa w kontekstach rdzenia korzystających ze wspólnego
API akcji z flagą `ALLOW_SOFTLOCK`. Wtyczki odczytujące surowe przyciski,
konteksty bez tej flagi i sprzętowe przełączniki Hold pozostają poza tym
zakresem. Nie jest to blokada bezczynności obejmująca całe urządzenie.

## Zapis, migracja i weryfikacja

Oba wybory komunikatów są zapisywane niezależnie w
`/.rockbox/accessibility-screen.cfg`, z nagłówkiem `RBACCESSIBILITY-SCREEN:1`
i indeksami `unlock` oraz `lock` podanymi w tabelach. W symulatorze Windows
jest to `simdisk/.rockbox/accessibility-screen.cfg` w katalogu programu. Zapis używa sąsiedniego
pliku tymczasowego, sprawdza operacje zapisu, synchronizacji i zamknięcia,
a następnie atomowo zmienia nazwę. Nieudany zapis zachowuje poprzedni wybór
i zgłasza błąd zapisu konfiguracji. Brak lub nieprawidłowe dane przywracają
domyślne komunikaty stanu. Nie potrzeba nowych pól ustawień globalnych ani
zmiany układu ABI wtyczek.

Osobny plik `/.rockbox/accessibility-lock.cfg` zapisuje teraz
`RBACCESSIBILITY-LOCK:2`: zachowuje `unlock-button` i `physical-buttons`,
a dodaje `timeout` (`-1`, `0` lub 1–600 sekund). Wersja1 jest odczytywana bez
przepisywania i zachowuje tryb zgodny ze starą blokadą. Dopiero udana zmiana
opcji zapisuje atomowo wersję2. Uszkodzone lub niekompletne dane przywracają
obie polityki przycisków wyłączone oraz stary tryb czasu. Samo otwarcie wyboru
nie zaokrągla ani nie przepisuje poprawnego niestandardowego czasu. Ustawienia
komunikatów w `accessibility-screen.cfg` i stare ustawienia globalne nie są
resetowane ani migrowane.

Przypisania gestów i przycisków pozostają w osobnym pliku `accessibility.cfg`.
Akcja podawania czasu wprowadziła format wejścia `RBACCESSIBILITY:5`.
Przypisania z wersji v1–v4 zachowują znaczenie, w tym dawny znacznik v4
**Domyślne sterowanie Rockboxa** (16), którego nie wolno zamienić w nowo dopisaną
akcję podawania czasu (również 16). Przełączanie usług wprowadziło v6;
rozszerzenie gestów wprowadziło v7, v8 dodał dźwięki wejścia, v9 profile
przycisków, a v10 osobne profile gestów. Bieżący opis jest w instrukcjach dotyku i przycisków.
Znaczniki systemowe v5 (17) i v6 (19) zachowują znaczenie, zamiast stawać się
przełączaniem eSpeaka lub przeglądania dotykowego. Zmiana komunikatów nie
resetuje przypisań. Zobacz [przełączanie usług](ACCESSIBILITY-SHORTCUT-PL.md)
i [ustawienia dotyku](ACCESSIBILITY-TOUCH-PL.md).

Przy ręcznym odzyskiwaniu ustawień zatrzymaj Rockbox przed edycją lub zmianą
nazwy któregokolwiek pliku konfiguracji i zachowaj potrzebne dane do odtworzenia.

Testy etykiet, zapisu i akcji sprawdzają tłumaczenia, właścicieli menu, migrację
wersji1/2, błędy zapisu atomowego, rozłączne polityki jednego terminu blokady,
przyjmowaną i odrzucaną aktywność, przytrzymanie dotyku, przepełnienie zegara
i rozdzielenie ustawień. Nie potwierdzają fizycznego czasu
reakcji przycisków R1, działania dotyku, dokładności baterii, dostępności
NVDA/UI Automation ani oszczędności energii. Kompilacje natywne, rzeczywiste
próby mowy w symulatorze i odbiór na urządzeniu wymagają osobnej weryfikacji.
