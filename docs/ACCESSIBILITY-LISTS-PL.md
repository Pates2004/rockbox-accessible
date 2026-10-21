# Dostępna nawigacja po listach

## Pozycja elementu i zmiany treści

W Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox znajdują
się dwie preferencje:

- **Ogłaszaj pozycję elementu na liście**: po nazwie wybranej pozycji Talkbox
  mówi np. „Pliki, 1 z 10”. Dotyczy wspólnych list menu, plików, ustawień,
  zakładek i wtyczek używających list rdzenia. Liczone są pozycje dostępne
  w danej liście, nie w całym drzewie; pozycja złożona z kilku wierszy liczy
  się jako jeden element. Pusta lista nie otrzymuje indeksu.
- **Informuj o dynamicznych zmianach treści**: steruje automatycznymi
  komunikatami postępu, m.in. budowania bazy, wstawiania i wyszukiwania
  utworów oraz skanowania FM. Nie wycisza nazw wybieranych samodzielnie,
  błędów, alarmów ani końcowego potwierdzenia wykonania zadania. Nie dodaje
  automatycznego odczytu wszystkim własnym interfejsom wtyczek.

Ogłaszanie pozycji ma pięć trybów:

- Wszędzie.
- Tylko interfejs, łącznie z zakresami liczbowymi.
- Tylko pliki, łącznie z przeglądarkami i wyborem katalogów systemu plików.
- Wszędzie oprócz suwaków, domyślnie dla nowych lub zresetowanych ustawień.
- Wyłączone.

Suwaki to zakresy liczbowe, np. głośność, basy, tempo mowy i czasy oczekiwania.
Rockbox przedstawia je jako natywne listy opcji, w tym tabele liczbowych kroków
zakresu. Przełączniki, listy enum, wybór języka i wariantu głosu oraz edytor maski
bitowej domyślnie zachowują indeksy. Menu nazw ustawień, właściwości, zakładki,
playlisty, utwory arkusza cue i nawigacja po bazie danych należą do interfejsu.
Liczba lub para etykieta/wartość nie czyni wiersza suwakiem. Znane wtyczki wyboru
katalogów mają jawnie określoną rolę plików. Pozostałe niestandardowe selektory
korzystające ze wspólnych list zachowują rolę interfejsu do czasu jawnego
oznaczenia. Własne interfejsy wtyczek omijające wspólne listy pozostają poza
tym mechanizmem.

Dotychczasowe `tts announce position: on` nadal oznacza Wszędzie, a `off` —
Wyłączone. Pięć zapisywanych wartości to `on,interface,files,except-sliders,off`.
Informowanie o dynamicznych zmianach treści pozostaje domyślnie włączone
i niezależne od trybu ogłaszania pozycji.

Wyłączenie indeksów nie zmienia komunikatów granicy. Zmiana pozycji przerywa
jej poprzednią nazwę wraz z indeksem, zamiast kolejkować mijane elementy.
„1 z 10” jest jednym zleceniem syntezy, a nie trzema osobnymi wypowiedziami;
łącznik pochodzi z aktualnego katalogu języka interfejsu.
Te ustawienia dotyczą Talkboxa; nie zmieniają preferencji plików głosowych.
Te źródła rozwojowe wymagają zgodnych wtyczek ABI `0xe006`; zachowane paczki Sans
nie są aktualizowane samą zmianą źródeł.

## Granice i nawigacja

Przejście do innej pozycji anuluje zaległe komunikaty granicy, żeby szybkie
naciskanie na końcu listy nie opóźniało odczytu nowo wybranej pozycji.

Przy zawinięciu nazwa nowej pozycji trafia do kolejki od razu, po ewentualnym
komunikacie granicy, bez zwykłego opóźnienia nawigacji. Poprzednia nazwa jest
przerywana przed dźwiękiem granicy. Kolejny ruch nadal może przerwać tę mowę:
nie tworzy się kolejka wszystkich mijanych pozycji do odsłuchania później.

Te funkcje pochodzą z generacji ABI `0xe004`; obecne wspólne ustawienia wymagają
zgodnych modułów `0xe006`. Starsze paczki alpha10/Windows13 ich nie zawierają.
Talkbox to nazwa czytnika w interfejsie; dostarczony silnik
eSpeak oraz jego licencje pozostają bez zmian.

Ustawienia → Ustawienia ogólne → Ekran → Przewijanie →
Zawijanie listy steruje istniejącą wspólną preferencją. Nie dodano drugiego
przełącznika zawijania. Po wyłączeniu lista zatrzymuje się na pierwszej/ostatniej
pozycji; po włączeniu przechodzi na drugi koniec. Własne ograniczenia list,
w tym brak zawijania niektórych list wartości korektora, nadal obowiązują.

W starszych wydaniach podmenu „Przewijanie” nosi nazwę „Przewijanie napisów”.
Nowa nazwa obejmuje także przewijanie całych list; położenie przełącznika
i zapisywana preferencja nie zmieniają się.

Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox →
Ogłaszanie początku i końca listy:

- Mowa i dźwięk.
- Tylko dźwięk, domyślnie.
- Tylko mowa.
- Wyłączone.

Samo dojście do pierwszej lub ostatniej pozycji niczego dodatkowo nie ogłasza.
Robi to dopiero próba przejścia dalej. Bez zawijania każde osobne naciśnięcie
na granicy ponownie zleca wybrany dźwięk lub komunikat, także szybkie naciśnięcia.
Przy zawijaniu granica jest ogłaszana przed nową pozycją na drugim końcu.
Przejście o stronę lub przyspieszony ruch ze środka listy najpierw zatrzymuje
się na jej skraju, bez przedwczesnego komunikatu i pominięcia skrajnej pozycji.
Powtarzanie przy przytrzymaniu zachowuje dotychczasowy brak zawijania.

Dźwięk respektuje głośność Dźwięków interfejsu i wybrane źródła: przyciski
fizyczne lub rozpoznane gesty. Wyłączenie dźwięków interfejsu wycisza także
granicę. Dźwięk powtarzanej akcji respektuje ustawienie powtórzeń; nie tłumi
to osobnych naciśnięć. Mowa respektuje dostępność syntezy, głośność i lokalne
wyciszenie danej listy. Kolejki mowy i mikser mają skończoną pojemność; przy
dowolnie szybkim naciskaniu nie da się zagwarantować ukończenia każdej wypowiedzi.

Starszy odroczony odczyt pozycji nie zastępuje komunikatu granicy, gdy nadal
stoisz na końcu lub początku listy. Jeśli odczyt pozycji po zawinięciu czeka,
kolejny ruch anuluje jej poprzedni komunikat granicy. Niema pozycja nie rezerwuje
kolejki mowy dla późniejszej, niezwiązanej akcji. Etykiety przeznaczone tylko do
wypowiadania są odczytywane przez identyfikatory mowy, a nie tablicę tekstów ekranu.

Cztery niezależne akcje do przypisania w profilach interfejsu i odtwarzania:

- Przejdź na początek listy.
- Przejdź na koniec listy.
- Przejdź na początek bieżącej strony.
- Przejdź na koniec bieżącej strony.

Fabrycznie gest w górę, potem w dół wybiera początek całej listy; w dół, potem
w górę — jej koniec. Akcje strony wybierają widoczne pozycje odpowiedniego
ekranu głównego/zdalnego, nie poprzednią ani następną stronę. Skok ogłasza wybraną
pozycję, nie ostrzeżenie o przekroczeniu granicy. Nie zmienia ekranu muzyki,
klawiatury ani czytnika tekstu w listę plików.

Wspólny mechanizm obejmuje menu, ustawienia i listy wartości, przeglądarkę plików,
zakładki oraz wtyczki korzystające z list rdzenia. Nie obejmuje automatycznie
własnych graficznych interfejsów, gier ani surowych pętli przycisków we wtyczkach.
Używaj kompletnego zgodnego wydania i dołączonych wtyczek: nowe ABI integracji
to `0xe006`. Dotychczasowe paczki Sans pozostają przy `0xe003` i nie są zmieniane.
