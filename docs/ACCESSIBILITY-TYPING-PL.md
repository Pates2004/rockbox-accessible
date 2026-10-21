# Dostępne pisanie

## Echo, wielkie litery i usuwanie

Ustawienia pisania zawierają teraz Tryb pisania, Echo pisania, Oznajmianie
wielkich liter, Zmianę wysokości głosu dla wielkich liter i Oznajmianie usunięcia
znaku. Trzy opisane dalej tryby pisania pozostają dostępne. Tryb nadal jest
zapisywany w `/.rockbox/accessibility-typing.cfg`; cztery pozostałe preferencje
trafiają atomowo do `/.rockbox/accessibility-typing-echo.cfg`.

Echo pisania: Brak, Znaki, Słowa albo Znaki i słowa (domyślnie). Słowo jest
odczytywane po wpisaniu jego granicy; zatwierdzenie ostatniego właśnie edytowanego
słowa również może je odczytać. Nieudane wpisanie i usuwanie na początku tekstu
nie oznajmiają nieistniejącej zmiany. Ruch kursora ani anulowanie nie udają
wpisania nowego słowa. Rozpoznawanie klawisza pod palcem i przy nawigacji działa
niezależnie od echa, także przy wyborze Brak.

Oznajmianie wielkich liter: Brak (domyślnie, zachowuje wcześniejszą mowę),
Powiedz wielka albo Zmień wysokość głosu. Zmiana wysokości jest względna wobec
bieżącego ustawienia eSpeaka: od -80% do +100%, początkowo +20%. Dotyczy tylko
kolejkowanej wypowiedzi tego znaku i jest ograniczana do zakresu silnika. Nie
zmienia zapisanej wysokości ani kolejnych zwykłych wypowiedzi.

Oznajmianie usunięcia: Powiedz usunięto i znak (domyślnie), Tylko usuwany znak
albo Brak. Domyślnie usłyszysz np. „usunięto b”. Uwzględniane są granice znaków
Unicode i rzeczywista pozycja kursora, nie pozycje bajtów. Klawiatura nie ma
znacznika tajnego pola hasła; te ustawienia nie tworzą trybu prywatności haseł.

Otwórz **Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox → Ustawienia pisania**. Wybór jest zapisywany osobno w `.rockbox/accessibility-typing.cfg`. Nie zmienia istniejących przypisań dostępności ani układu ustawień udostępnianych wtyczkom. Brak lub niepoprawna zawartość pliku wybiera tryb **Przeglądaj i wpisuj po podniesieniu palca**, odpowiadający wcześniejszemu wpisywaniu po zwolnieniu dotyku. Nieudany zapis zgłasza błąd i pozostawia poprzedni tryb.

- **Przeglądaj i wpisuj po podniesieniu palca:** dotknij klawisza, aby go usłyszeć. Przesuwaj palec po klawiszach; każdy nowy wskazany klawisz zostanie odczytany od razu. Podnieś palec wewnątrz prawidłowego klawisza, aby wpisać wskazany znak jeden raz. Krótkie nieruchome stuknięcie również wpisuje znak. Opuszczenie prawidłowych obszarów klawiatury anuluje dotknięcie do następnego naciśnięcia.
- **Przeglądaj i wpisuj dwukrotnym stuknięciem:** przesuwaj palec, aby od razu wskazywać i słyszeć klawisze. Krótkie przytrzymanie nieruchomego dotyku również wskazuje klawisz. Podniesienie palca nie wpisuje znaku. Dwa szybkie nieruchome stuknięcia wpisują wskazany klawisz jeden raz; miejsce tych stuknięć nie wybiera innego klawisza. Każde stuknięcie musi zakończyć się w prawidłowym obszarze klawiatury. Od pierwszego do drugiego podniesienia palca może upłynąć najwyżej 320 ms. Przeglądanie, nieprawidłowe dotknięcie, przycisk fizyczny, blokada lub zmiana ekranu kasują oczekujące dwukrotne stuknięcie.
- **Strzałki i Enter; przytrzymaj Enter, aby zakończyć:** przesuwaj fokus przyciskami kierunkowymi lub skonfigurowanymi gestami nawigacji dostępności. Enter wpisuje znak, a przytrzymany Enter kończy pisanie. Pod rzędami znaków strzałki w górę i w dół pozwalają też dotrzeć do odczytywanych przycisków **OK**, **Usuń** i **Anuluj**; strzałki w lewo i w prawo wybierają przycisk. Wiersz edycji nad klawiszami nadal pozwala przesuwać kursor tekstu, a Enter w tym wierszu usuwa znak. Dotychczasowe kombinacje zmiany strony i przesuwania kursora pozostają dostępne.

Ten sam fokus i odczyt obejmują małe i wielkie litery, interpunkcję, polskie znaki, spacje oraz własne układy klawiatury. Spacja jest odczytywana jako pusty znak. Przeglądanie dotykiem odczytuje również obszary **OK**, **Usuń**, **Anuluj**, następnej strony oraz przesuwania kursora tekstu w lewo i w prawo; uruchamiaj je zgodnie z wybranym trybem pisania. **Usuń** kasuje poprzedni znak, **OK** zatwierdza tekst, a **Anuluj** zwraca do wywołującej funkcji wynik anulowania klawiatury. Ruch kursora odczytuje znak na nowej pozycji lub komunikat **Koniec tekstu**. Nadal obowiązuje pojemność bufora: znak, który się nie mieści, nie zostaje wstawiony.

Na HiBy R1 funkcję Enter domyślnie pełni Power. Krótkie naciśnięcie wpisuje znak, a pierwsze powtórzenie przytrzymania kończy pisanie. Późniejsze zwolnienie nie może dopisać znaku ani uruchomić opcji kolejnego ekranu. W razie potrzeby nadal korzystaj ze sprzętowego awaryjnego wyłączenia przyciskiem Power; pisanie nie zmienia jego progu w firmware. Kolejność zakończenia pisania i wyłączenia oraz fizyczny ekran dotykowy wymagają jeszcze sprawdzenia na R1. Własne przypisania mogą zmieniać działanie przycisków.

W trybach dotyku bezpośredniego ruch służy przeglądaniu klawiatury; globalne gesty nawigacji pozostają dostępne w trybie strzałek. Blokada, opuszczenie klawiatury, podłączenie USB lub anulowanie dotyku usuwają niedokończone sekwencje. Potem wymagane jest nowe dotknięcie. Wyłączona dostępność i pisanie Morse'em zachowują dotychczasową obsługę klawiatury. Przeglądanie nie klika przy każdym ruchu; zatwierdzona czynność dotykowa wysyła jedno żądanie sprzężenia gestu zgodnie z obecnymi ustawieniami klikania.

Jeśli klawiatura nie może utworzyć swoich widoków, odczytuje komunikat **Nie można otworzyć klawiatury**, zwraca anulowanie bez zatwierdzania tekstu i przywraca poprzedni motyw. Po tym błędzie sesja pisania nie pozostaje aktywna.

Tryby dotyczą wspólnej klawiatury rdzenia, również otwieranej przez wtyczki. Niezależne klawiatury wtyczek wymagają własnej integracji. Testy hosta mogą sprawdzić przejścia stanów, edycję UTF-8 i błędy zapisu; nie potwierdzają działania fizycznego R1, NVDA ani całej gotowej paczki aplikacji.
