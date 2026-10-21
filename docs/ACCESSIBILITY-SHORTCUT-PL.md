# Przełączanie usług dostępności

Czytnik nazywa się Talkbox; silnikiem pozostaje dostarczony fork eSpeaka.
Te funkcje pochodzą z generacji ABI `0xe004` i nie występują w starszych paczkach alpha10/Windows13.
Obecne ustawienia rozwojowe wymagają zgodnych modułów ABI `0xe006`.
Czyste wydanie prywatne zachowuje polski interfejs i włączoną mowę. Angielski
interfejs i początkowo wyłączona mowa pozostają na przyszłe wydanie publiczne.
Nowe profile R1 przypisują trzykrotny Power do grupowego skrótu w interfejsie
i na ekranie odtwarzania. Zapisane wcześniej przypisania są zachowywane.
Sterownik klawiatury ADC R1 nie pozwala polegać na jednoczesnym przytrzymaniu
obu przycisków głośności.

W Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia Talkbox znajdują się
Ustawienia eSpeak, zawierające wyłącznie parametry silnika syntezy. Czytnik tekstu
i pozostałe funkcje Talkboxa są obok Ustawień eSpeak, w Ustawieniach Talkbox.
Skrót dostępności zawiera przełącznik jego używania oraz Wybierz usługi
dostępności. Domyślnie skrót jest włączony i obejmuje Talkbox oraz przeglądanie
dotykowe. Możesz dołączyć pliki głosowe interfejsu i, gdzie jest obsługiwana,
kurtynę ekranu. Osobne przełączniki wybierają usługi dla skrótu; samo zaznaczenie
usługi nie zmienia jeszcze jej bieżącego stanu.

Jeśli choć jedna wybrana usługa jest wyłączona, skrót włącza wszystkie wybrane.
Gdy wszystkie są włączone, skrót wyłącza je wszystkie. Wyłączenie Talkboxa wyłącza
też aktywną kurtynę ekranu przed wyłączeniem mowy, nawet gdy kurtyna nie była
wybrana. Włączenie Talkboxa może ponownie włączyć kurtynę tylko wtedy, gdy jest
wybrana i mowa jest dostępna. Inne niewybrane usługi zachowują swój stan.
Jeden wspólny komunikat podaje faktyczny stan każdej wybranej usługi i zależną
zmianę kurtyny, również po wyłączeniu mowy. Częściowe niepowodzenie jest zgłaszane;
udanych zmian nie cofamy po cichu. Wyłączony skrót albo pusta lista wybranych usług niczego
nie przełącza. Nie ma sztucznego limitu dwóch usług.

Niezależnie przypisuj akcje Przełącz usługi skrótu dostępności, Włącz lub wyłącz
Talkbox, Włącz lub wyłącz pliki głosowe interfejsu albo przełączanie przeglądania
dotykowego:

- Przyciski: Ustawienia → Ustawienia ogólne → System → Ustawienia przycisków fizycznych.
- Gesty: Ustawienia → Ustawienia ogólne → Dostępność → Ustawienia przeglądania dotykowego → Przypisania gestów.

W Systemie są ustawienia ekranu dotykowego i przycisków fizycznych.
W wersji z dotykiem i eSpeakiem ustawienia ekranu
dotykowego przeniesiono z Wyświetlacza do Systemu. Wersja dotykowa bez eSpeaka
zachowuje pozycję w Wyświetlaczu. Przeglądanie dotykowe i przypisania gestów
pozostają w Dostępności.

Stary `/.rockbox/accessibility-shortcut.cfg` jest ignorowany i pozostaje bez
zmian. Jego dawne wartości enabled/service nie sterują żadną z tych akcji.
Przypisania nadal należą do `/.rockbox/accessibility.cfg`, a zwykłe ustawienia
eSpeaka i plików głosowych pozostają niezależne.

W przypisaniach przycisków i gestów pozostają pojedyncze usługi obok akcji grupy.
Dotychczasowe mapowania pojedynczego, podwójnego, potrójnego naciśnięcia oraz
przytrzymania są zachowane. Potrójny Power jest ustawieniem fabrycznym, a nie
nadpisaniem zapisanej akcji Domyślna lub Nieprzypisany. Rozpoznawanie potrójnego
naciśnięcia opóźnia pojedyncze i podwójne użycie Power do końca okna kolejnych
naciśnięć; przytrzymanie Power i kombinacje ratunkowe pozostają oddzielne.
Przełączanie
wykonuje się raz, a nie wielokrotnie przy trzymaniu przycisku. Wyłączone
przeglądanie dotykowe nie rozpoznaje gestów; zachowaj przypisanie fizyczne, jeżeli
poza dotykiem nie masz innego sposobu nawigacji.

Przełączenie plików głosowych nie wyłącza Talkboxa ani syntezy nazw katalogów
i plików. Przełączenie Talkboxa nie zmienia preferencji plików głosowych.
Włączenie plików przy wyłączonym Talkboxie wymaga poprawnego pliku głosowego
zgodnego z językiem i wydaniem Rockboxa. Paczka testowa nie udaje, że go zawiera.
Brak pliku powoduje błąd i przywrócenie poprzedniej preferencji. Przy włączonym
Talkboxie używanie plików jest nieaktywną preferencją, którą można zmienić osobno.

Zmiana usługi zleca syntetyczny komunikat o włączeniu lub wyłączeniu, nawet gdy
zwykły Talkbox jest wyłączony albo głośność plików głosowych wynosi zero.
Nadal obowiązuje głośność Talkboxa i główna głośność odtwarzacza: niczego nie
podgłaśniamy. Uszkodzone lub brakujące dane silnika, niedostępne wyjście,
zerowa głośność albo awaria sprzętu mogą uniemożliwić usłyszenie komunikatu.
Natychmiastowe niepowodzenie dodania komunikatu do kolejki ma wizualny komunikat
zastępczy. Późniejszy błąd syntezy lub wyjścia albo zerowa głośność nie gwarantują
wizualnego komunikatu zastępczego ani słyszalnego potwierdzenia. Przyjęcie tekstu
do kolejki nie dowodzi, że dźwięk faktycznie zabrzmiał. Dalsza nawigacja może
przerwać ten komunikat tak samo jak inną mowę interfejsu.

Edytor gestów zawiera także potrójne stuknięcie, dwukrotne z przytrzymaniem,
opcjonalne powtarzanie przesunięcia, datę, podsumowanie i cele uruchamiania.
Obecność tych opcji nie oznacza akceptacji fizycznego dotyku. Testy klawiatury/PCM
Windows nie potwierdzają działania rzeczywistego R1, NVDA, fizycznego dźwięku,
radia ani wydajności baterii.

Zobacz [przyciski](ACCESSIBILITY-BUTTONS-PL.md),
[dotyk](ACCESSIBILITY-TOUCH-PL.md) i
[łączność R1](HIBY-R1-CONNECTIVITY-PL.md).
