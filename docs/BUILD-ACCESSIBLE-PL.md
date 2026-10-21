# Kompilowanie Rockbox Accessible

Szczegółowa [angielska instrukcja natywnego HiBy R1](BUILD-ACCESSIBLE-NATIVE.md)
opisuje SDK, przygotowanie hosta, kompilację aplikacji i kontrole wyniku.
Rozróżnia to od pełnego pakowania wydania: publiczny generator wymaganych
informacji o pochodzeniu i licencjach, `tools/prepare_hiby_notices.py`, działa
offline na przypiętych wejściach SDK. Nie buduje samego SDK ani nie dowodzi jego
pochodzenia od źródeł. Polecenie pakowania nie oznacza potwierdzonej odtwarzalności
wydania od zera lub bajt w bajt. Instrukcja dla współtwórców jest
[po angielsku](CONTRIBUTING-ACCESSIBLE.md).

[English](BUILD-ACCESSIBLE.md)

Znane ograniczenie etykiet roboczych: część skryptów Sansy nadal nadaje historyczną
nazwę r29, choć wspólne źródła korzystają z r34. Sprawdzaj rewizję silnika
w manifeście, nie tę nazwę. Nie oznacza to aktualizacji ani ponownej weryfikacji
zachowanych wydań Sansy. HiBy R1 ma odrębną, aktualną ścieżkę wersjonowania.

Starszy klon Windows może zachować CRLF w `lib/espeak/License.txt` mimo aktualizacji
reguł Git. Jeśli kontrola zgłosi niezgodną sumę tej licencji, nie wyłączaj jej.
[Instrukcja naprawy](BUILD-ACCESSIBLE.md#existing-windows-checkout-with-a-license-hash-mismatch)
zmienia wyłącznie końcówki linii zgodne z bieżącą wersją Git i odmawia nadpisania
innych lokalnych zmian. Uruchamia się ją z katalogu źródeł w powłoce Linux/WSL.
Nie resetuje repozytorium ani nie zmienia tekstu licencji, danych głosu i ustawień.

To źródła rozwojowe, nie uniwersalny firmware. Zacznij od symulatora SDL.
[Opis projektu](../README.md) rozróżnia wspólny rdzeń, obsługiwane cele i prace
niedokończone. Kod nie oznacza jeszcze zaakceptowanego nowego wydania na sprzęt.

## 1. Repozytorium i dokładne dane eSpeaka

Potrzebujesz Gita i Pythona co najmniej 3.12. W przykładach katalog źródeł nazywa
się `rockbox`; polecenia wykonuj z jego katalogu głównego.

```sh
git clone --config core.autocrlf=false --branch accessible https://github.com/Pates2004/rockbox-accessible.git rockbox
cd rockbox
python3 -B tools/prepare_espeak_source.py
```

Pomocnik pobiera publiczny commit eSpeaka
`a14831fd3af6b3df77ef23b854cd05ee05b12851`, nakłada dołączoną poprawkę danych
i sprawdza sumy źródeł silnika oraz wszystkich 283 plików danych i 88 źródeł
słowników. Odtwarza też dokładne zakończenia wierszy, w tym mieszane LF/CRLF
w polskich źródłach. Nie przebudowuje po cichu słownika i nie używa eSpeak NG.

Domyślnie powstaje **sąsiedni** katalog `espeak-1.44.05-source`. Istniejący katalog
nie zostanie nadpisany. Inne nowe miejsce wskaż przez `--destination /pełna/ścieżka`,
a następnie przekaż je builderowi przez `--espeak-source /pełna/ścieżka`.
Istniejące dane sprawdzisz przez `--check-only --destination /pełna/ścieżka`.
Nieudane pobranie pozostawia katalog do diagnozy; nie naprawia ani nie kasuje
Twoich źródeł. Internet jest potrzebny do pierwszego pobrania, nie do działania
syntezy. Zmodyfikowany silnik jest już w `lib/espeak/engine`; osobny katalog
dostarcza oryginalne źródła i zgodne dane potrzebne także przy dystrybucji.

## 2. Katalogi wynikowe

Bieżące paczki trafiają do `installfiles` w repozytorium. Materiały kompilacji
są poza nim. W Windows i WSL jest to `D:/work`, jeśli dysk D: istnieje, a tylko
w przeciwnym razie `C:/work`, z kategoriami `Workspace/<nazwa-katalogu-projektu>`,
`Snapshots/<nazwa-katalogu-projektu>` itd. W natywnym Linuksie ustaw pełną ścieżkę
zapisywalnego katalogu poza repozytorium:

```sh
export ROCKBOX_WORK_ROOT="$HOME/rockbox-work"
```

Buildery sprawdzają niebezpieczne dowiązania i nakładanie ścieżek. Nie zastępują
istniejącej instalacji symulatora: przenieś ją świadomie, zachowując potrzebne
ustawienia i zakładki. Nie nadpisuj działającego programu. Zwykłych archiwalnych
buildów nie trzeba przechowywać bez końca. Część odziedziczonych narzędzi hosta
powstaje jeszcze w `tools`; są to ignorowane wyniki kompilacji, nie nowe źródła.

## 3. Symulator linuksowy

Zainstaluj zwykłe zależności Rockboksa: kompilator C/C++, make, Perl, Python,
pkg-config, zip/unzip i nagłówki SDL2. Dla Debiana/Ubuntu pakiety to m.in.
`build-essential perl python3 git pkg-config zip unzip libsdl2-dev`.

```sh
python3 -B tools/build_espeak_simulator.py --platform linux --target hibyr1 --jobs 4
```

Cele: `hibyr1`, `sansaclipplus`, `sansaclipzip`. Program używa własnego sąsiedniego
`simdisk`. Nowa paczka ma czyste ustawienia testowe, a nie Twój poprzedni profil.
Opis sterowania jest w poradnikach poszczególnych urządzeń.

## 4. Natywny symulator Windows x64 kompilowany w Linuksie/WSL

Do zależności hosta dodaj MinGW-w64 z C/C++. Pobierz oficjalny MinGW development
SDK SDL2 [2.32.10](https://github.com/libsdl-org/SDL/releases/tag/release-2.32.10);
zachowaj `LICENSE.txt` obok katalogu `x86_64-w64-mingw32`.
Wskaż pełną ścieżkę SDK:

Archiwum: `SDL2-devel-2.32.10-mingw.tar.gz`, SHA-256
`83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2`
(suma oficjalnego pliku wydania, potwierdzona również na lokalnym archiwum SDK).
Sprawdź ją poleceniem `sha256sum`, a potem rozpakuj archiwum przez `tar -xzf`.

```sh
python3 -B tools/build_espeak_simulator.py --platform windows --target hibyr1 \
  --sdl-sdk /pełna/ścieżka/SDL2-2.32.10/x86_64-w64-mingw32 --jobs 4
```

Wynik: `installfiles/simwindows-hibyr1/rockboxui.exe` i cały sąsiedni runtime.
Na Windows nie trzeba już WSL, Pythona ani systemowego syntezatora. Nie przenoś
samego EXE i nie mieszaj modułów ze stockowego Rockboksa.
[Użytkowanie Windows](ESPEAK-WINDOWS.md).

Pełna ścieżka `espeak-data` musi mieścić się w odziedziczonym limicie 149 bajtów
UTF-8. Używaj rozsądnie krótkich ścieżek; polska litera może zajmować kilka
bajtów. Bluetooth symulatora nie steruje radiem komputera.

## 5. Fizyczne odtwarzacze

- Sansa: [Clip+](ESPEAK-CLIPPLUS-PL.md), [Clip Zip](ESPEAK-CLIPZIP-PL.md),
  `python3 -B tools/build_espeak_clipplus.py --help`.
- HiBy R1: [port](ESPEAK-HIBYR1-PL.md),
  `python3 -B tools/build_espeak_hiby.py --help`. Builder wymaga jawnie wskazanych
  zgodnych narzędzi MIPS, informacji licencyjnych runtime i źródeł ALSA.
  `--stage-hardware-test --source-frozen` przygotowuje kandydata do weryfikacji,
  nie potwierdza całego startu na urządzeniu.

Zwykły kompilator MIPS z dystrybucji nie gwarantuje zgodności z systemem HiBy.
Nie dodajemy tu obrazów firmware’u HiBy, jego bibliotek współdzielonych ani
binarnych toolchainów. Niezmienione źródła upstream zawierają natomiast binarne
firmware’y Marvell z zachowaną osobną licencją; nie są to instalatory HiBy.
Instalacja i odzyskiwanie to osobny temat:
[instrukcja R1](HIBY-R1-INSTALL-PL.md). Nie stosuj firmware’u innego modelu i nie
flashuj tylko po to, by wymienić `.rockbox` w działającej już instalacji.

Zmiana układu ustawień/wtyczek wymaga właściwego ABI i ponownej kompilacji
modułów. Nie wgrywaj starych ani stockowych wtyczek. Numery historycznych paczek
w poradnikach opisują tamte paczki, nie potwierdzają obecnego kodu rozwojowego.

## 6. Testy i zgłaszanie problemów

Małe testy przygotowania zależności i wspólnych list:

```sh
python3 -B -m unittest discover -s tools/tests -p test_prepare_espeak_source.py -v
python3 -B -m unittest discover -s tools/tests -p test_accessibility_lists.py -v
```

Pozostałe zestawy mają własne wymagania: część korzysta z ukończonych buildów
native/Windows, przypiętych danych diagnostycznych albo samego Windows.
Uruchomienie wszystkich testów GUI/sprzętowych naraz nie jest zwykłą kontrolą
kompilacji. Pominięty test platformowy ani mock usługi nie potwierdza sprzętu.
Zgłaszając problem podaj model, dokładny commit, komunikat i kroki odtworzenia.
Nie publikuj haseł ani prywatnych nagrań diagnostycznych.
