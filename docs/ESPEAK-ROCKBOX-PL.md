# Ustawienia Talkbox i eSpeak

Otwórz **Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox**.
Talkbox jest czytnikiem ekranu. Jego podmenu **Ustawienia eSpeak** zawiera
wyłącznie parametry silnika syntezy, w tej kolejności:

1. Język syntezy mowy
2. Wariant głosu
3. Tempo mowy
4. Skala tempa mowy
5. Wysokość głosu
6. Głośność mowy
7. Modulacja
8. Odstęp między słowami
9. Interpunkcja

Język może być zgodny z językiem interfejsu albo wybrany niezależnie.
Zmiana skali tempa zmienia sposób prezentacji, nie zapisaną prędkość.
Wysokość i modulacja są wyświetlane i wypowiadane jako 0–99%, domyślnie 50%.
To procentowa etykieta skali sterowania eSpeaka, nie procent częstotliwości
w hercach ani zmiana względem głosu domyślnego. Głośność ma zakres 0–200%,
domyślnie 100%. Klucze konfiguracji, zapisane liczby i brzmienie nie zmieniają się.
Silnikiem pozostaje zintegrowany fork eSpeak 1.44.05; nazwa Talkbox nie
zastępuje informacji o jego autorstwie ani nie zmienia jego API.

Grupa Talkbox zawiera kolejno:

1. Ustawienia eSpeak
2. Synteza mowy — włącza lub wyłącza Talkbox
3. Przyciszanie audio
4. Poziom audio podczas mowy
5. Ustawienia czytania tekstu — Zakres nawigacji i Wiersze na stronie
6. Ustawienia przeglądania dotykowego — w tym profile przypisań gestów
7. Ustawienia ekranu — Kurtyna ekranu i Zgłaszanie stanu ekranu
8. Ustawienia pisania — tryb, echo, wielkie litery i zgłaszanie usuwania
9. Ogłaszanie początku i końca listy

Przeglądanie dotykowe i pisanie wymagają ekranu dotykowego. Opcje ekranu
zależą od obsługi kurtyny i programowej blokady na danym urządzeniu.
Dotychczasowe podmenu zachowują własne opcje. Zobacz poradniki
[dotyku](ACCESSIBILITY-TOUCH-PL.md), [ekranu](ACCESSIBILITY-SCREEN-PL.md),
[kurtyny](ACCESSIBILITY-CURTAIN-PL.md) i [pisania](ACCESSIBILITY-TYPING-PL.md).

**Skrót dostępności** pozostaje bezpośrednio w **Dostępności**, ponieważ
steruje wyborem niezależnych usług. Ustawienia nagranych plików głosowych
interfejsu, nazw katalogów/plików i głośności plików głosowych także pozostają
na tym poziomie. Są niezależne od syntezy Talkbox i głośności jego silnika.
Zobacz [sterowanie usługami](ACCESSIBILITY-SHORTCUT-PL.md).

Przyciski fizyczne, ogólne ustawienia ekranu dotykowego i dźwięki interfejsu
pozostają w **Ustawienia ogólne → System**. Jasność i czasy podświetlenia
pozostają w **Ekran**; menu łączności zachowują dotychczasowe położenie.
Zmiana układu zachowuje klucze i wartości zapisanej konfiguracji, prywatne
profile wejścia i układ ustawień wtyczek. Etykiety menu mają wersję wyświetlaną
i mówioną po polsku i angielsku. Mowa, PCM i rzeczywista nawigacja klawiaturą
nadal wymagają walidacji nowo zbudowanego programu.

## Polecenia czytnika tekstu

Wspólny czytnik udostępnia **Znajdź**, **Znajdź następne**,
**Znajdź poprzednie**, **Przejdź do linii**, **Przejdź do strony** i
**Przejdź do procentu** w swoim menu kontekstowym **Opcje tekstu**.
Zakres nawigacji i Wiersze na stronie pozostają w Ustawieniach czytania tekstu.

Dwie osobne opcje w Opcjach tekstu są zapisywane między uruchomieniami:
**Wielkość liter przy wyszukiwaniu** oferuje domyślne **Ignoruj wielkość liter**
oraz **Uwzględniaj wielkość liter**; **Wyszukiwanie na granicy tekstu** oferuje
domyślne **Zatrzymaj i ogłoś**, **Pytaj o zawinięcie** oraz
**Zawijaj automatycznie**. Wyszukiwanie uwzględnia polskie pary małych i wielkich
liter; znaki diakrytyczne pozostają rozróżniane. Ostatnie skuteczne zapytanie
jest pamiętane tylko podczas bieżącego otwarcia czytnika. Skuteczne wyszukanie
i przejście do wpisanej pozycji pozostawiają pauzę; czytanie można potem wznowić.

[Opis czytania i zakładek](ESPEAK-BOOKMARKS-PL.md) podaje limity wpisywania,
numerację logicznych linii i stron, procenty liczone w bajtach oraz zachowanie
po anulowaniu. Dostępność zależy od paczki; datowane opisy wydań zachowują
pierwotny zakres.
