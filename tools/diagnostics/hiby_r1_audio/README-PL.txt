HiBy R1: diagnostyka ciszy bez czytania ekranu odtwarzacza

To NIE jest potwierdzona naprawa dźwięku. To osobny, odwracalny zestaw
diagnostyczny. Wersję aplikacji określa BUILD.json, a jej wymaganą sumę SHA256
plik manifest.json. Zestaw odrzuca inne wersje; nie wymuszaj instalacji.
Samo logowanie nie modyfikuje rdzenia, symulatora ani firmware producenta.
Nie kopiuj r1.upt i nie flashuj urządzenia ponownie.

Zestaw wymaga Windows PowerShell 5.1, dostępnego standardowo w Windows.
Sterowanie odbywa się na komputerze z klawiatury; nie trzeba odczytywać
ekranu R1. Nie obiecuje to testu z rzeczywistym NVDA ani testu na R1.

1. Wyłącz R1. Włóż kartę do czytnika komputera. Nie wyjmuj karty z działającego
   odtwarzacza. Poniżej E:\ to przykład; wpisz faktyczną literę karty.
2. W terminalu Windows uruchom z katalogu tego zestawu:
   .\Start.cmd -Mode Check -CardRoot E:\
   To tylko odczyt karty. Raport powstaje w podfolderze Reports tego zestawu.
   Zapisz go: może już pokazać inny build albo wyłączoną syntezę w konfiguracji.
3. Aby zbadać sam dźwięk, uruchom:
   .\Start.cmd -Mode Enable -CardRoot E:\
   Potwierdź TAK. Program sprawdza sumy aplikacji i ALSA. Inny lub niepełny
   build jest odrzucany bez podmiany programu. Nie wymuszaj instalacji.
4. Bezpiecznie wysuń kartę, włóż do wyłączonego R1, podłącz słuchawki kablem
   i uruchom odtwarzacz. Poczekaj około 15 sekund, spróbuj kilku krótkich
   naciśnięć. Głośność nie jest zwiększana ani wymuszana przez diagnostykę.
5. Wyłącz R1, przełóż kartę do czytnika i uruchom:
   .\Start.cmd -Mode Collect -CardRoot E:\
   Podeślij report.json oraz r1-audio-diagnostic.log i r1-audio-launcher.log
   z nowego podfolderu Reports. Nie trzeba odczytywać ani przepisywać paniki.
6. Aby przywrócić zwykły program, przy wyłączonym R1 i karcie w czytniku:
   .\Start.cmd -Mode Restore -CardRoot E:\
   Potwierdź TAK. Działa również wtedy, gdy start diagnostyczny się nie udał,
   o ile zapisane pliki są kompletne. Nie wymaga działającej mowy na playerze.

Co dokładnie zmienia Enable:
- PRZENOSI oryginalny rockbox.r1 do rockbox.r1.audio-original na tej samej
  karcie. To nadal ten sam plik programu, nie druga kopia wydania.
- Kopiuje małą bibliotekę r1-audio-trace.so i launcher do .rockbox.
- Launcher przy starcie kopiuje oryginalny program do RAM w /tmp i uruchamia
  go z dodatkowym logowaniem ALSA. Sam program Rockboxa pozostaje identyczny.
- Nie kasuje profilu, zakładek, eSpeak-data ani muzyki; nie zmienia głośności,
  miksera, tras audio, Bluetooth, Wi-Fi, partycji, bootloadera ani firmware.
- Tworzy na karcie dwa logi obok programu. Ślad biblioteki ma limit 64 KiB
  i loguje tylko pierwsze pakiety, nie całe nagranie ani treść syntezy.

Collect tworzy potrzebną kopię logów w Reports, zachowując je na karcie.
Restore przenosi launcher, bibliotekę i logi do Reports jako materiał do
diagnostyki/odzyskiwania oraz przywraca ten sam oryginalny rockbox.r1.
Te raporty i zachowane pliki pozostają po pracy; nic nie jest automatycznie
kasowane. Ustawienia są raportowane tylko z krótkiej listy dotyczącej mowy
i głośności; nie zbieramy pełnej konfiguracji ani haseł sieciowych.

Ograniczenia: kontrolowane testy MIPS/ALSA null nie potwierdzają DAC-a,
wykrywania słuchawek, zgodności każdego firmware ani rzeczywistego dźwięku.
Zestaw nie identyfikuje sam wszystkich przyczyn awarii TTS i nie jest wydaniem
do codziennego używania. Po zebraniu logów użyj Restore.
