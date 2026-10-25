# Profile wydań

[English](RELEASE-PROFILES.md)

Nowe buildy z wbudowaną syntezą startują po angielsku, z wyłączonym Talkbox
i przeglądaniem dotykowym. Skrót dostępności pozostaje włączony i obejmuje
Talkbox oraz dostępne przeglądanie dotykowe. Na czystym HiBy R1 w interfejsie
i odtwarzaniu uruchamiają go **trzy szybkie naciśnięcia Power**. Wyłączenie
przeglądania dotykowego nie wyłącza tego fizycznego skrótu. Zapisane wcześniej
ustawienia i własne przypisania przycisków pozostają zachowane. Inne porty
zachowują ograniczenia swoich możliwości; test R1 nie potwierdza działania
Power ani ekranu dotykowego innego odtwarzacza.

`Accessible-Polish.cfg` jest opcjonalnym profilem, nie ładuje się automatycznie.
Wybiera polski, włącza Talkbox i dostępne przeglądanie dotykowe, zachowując
wybór usług skrótu. Nie resetuje własnych przypisań przycisków. eSpeak podąża
za językiem interfejsu.

W symulatorze Windows skopiuj dostarczony CFG do `simdisk`, obok `.rockbox`,
a następnie otwórz przez **Files / Pliki**. Na natywnej karcie opcjonalny CFG
znajduje się w `.rockbox`; użyj przeglądarki plików konfiguracyjnych albo
skopiuj go do głównego katalogu karty i otwórz w Plikach. Nie kopiuj EXE
Windows na kartę. W źródłach profil jest w `docs/profiles/Accessible-Polish.cfg`.

Ustawienie importu `accessibility touch enabled: on` zapisuje istniejącą prywatną
preferencję dostępności. Nie trafia do głównego zapisywanego `config.cfg`,
więc późniejsze zmiany z menu nie są nadpisywane przy każdym restarcie.
Błędne wartości on/off i nieudany zapis prywatnej preferencji powodują błąd
importu. Podobnie jak dotychczasowy loader CFG, nie jest to transakcja wszystkich
ustawień pliku. Porty bez danej możliwości ignorują jej ustawienia.

Starsze paczki zachowują poprzednie ustawienia. Ich manifesty nie mają pola
`default_profile`. Nowe deklarują `standard-en`; walidatory rozróżniają te
profile i nie traktują starszych polskich paczek jako zmienionych.
