# Kurtyna ekranu

Otwórz **Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox → Ustawienia ekranu → Kurtyna ekranu**. Akcję
**Kurtyna ekranu** możesz też przypisać do gestu lub przycisku fizycznego.
Przełącza czarny ekran bez zatrzymywania mowy, muzyki i sterowania dotykiem.
Włączenie wymaga dostępnego silnika eSpeak w Talkbox. Wyłączenie Talkbox przywraca obraz przy
następnym pobraniu akcji rdzenia, aby nie pozostawić niemego, niewidocznego menu.

Kurtyna nie nadpisuje jasności, czasu podświetlenia, przypisań gestów ani blokady
ekranu. Zwykłe przyciski i zmiany ładowania nie powinny odsłaniać interfejsu
rdzenia. Blokada jest oddzielna: zwykły gest czytnika nie odblokowuje ekranu.
Opcjonalne przypisania wybudzania w Systemie są odrębnym, świadomie włączanym
wyjątkiem i nie wyłączają kurtyny. Zobacz [zasady ekranu](ACCESSIBILITY-SCREEN-PL.md).

Na R1 przy aktywnej kurtynie **Power + Next** przywraca obraz przed obsługą
własnych przypisań i blokady. Przed dalszym sterowaniem zwolnij oba przyciski;
ich zwolnienie nie powinno przypadkowo otwierać pozycji. Gdy kurtyna jest
wyłączona, ta kombinacja zachowuje zwykłą funkcję danego ekranu. Skrót działa
przez wspólne API akcji oraz standardowe wywołania wtyczek `button_get` i
`button_get_w_tmo`. Wtyczka sprawdzająca jedynie stan przycisków lub omijająca
te interfejsy nadal może omijać skrót odzyskiwania.
Dotychczasowe awaryjne wyłączenie przez długie Power nadal działa. Po ponownym
uruchomieniu Rockboxa kurtyna jest zawsze wyłączona — celowo nie zapisujemy
czarnego stanu na kolejny start. To także droga wyjścia z wtyczki surowego wejścia.

Nie jest to ochrona prywatności całego urządzenia. Selektor startowy, system
fabryczny, kernel, ekrany paniki/odzyskiwania i zewnętrzne programy nie podlegają
kurtynie. Ścieżki obrazu fizycznego R1 i Windows wymagają odrębnych sprawdzeń;
zastępcze testy hosta nie mierzą jasności sprzętu ani oszczędności baterii.
Inne backendy wyświetlacza wymagają własnej integracji i weryfikacji.
