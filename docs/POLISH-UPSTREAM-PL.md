# Polska łata tłumaczenia: zgłoszenie do Rockbox Gerrit

[English version](POLISH-UPSTREAM.md)

Aktualizacja 2026-10-21: sprawdzona łata samego tłumaczenia jest opublikowana
jako commit `dcb4b6d60db9ae5052ba79cc8b80939539301d07` na oddzielnej
[gałęzi `polish-translation-fixes`](https://github.com/Pates2004/rockbox-accessible/tree/polish-translation-fixes).
Zmienia tylko istniejące polskie tłumaczenia, bez kodu TTS. GitHub potwierdza
Pates2004 jako autora i committera. Nie ma zgłoszenia do Gerrita ani akceptacji
oficjalnego Rockboksa. Ścieżki i stan przygotowania poniżej opisują pierwotną
migawkę z 2026-10-10; nie powtarzaj w ciemno poleceń commita/push ani nie nadpisuj
opublikowanej gałęzi. Lokalny checkout referencyjny pozostaje oddzielny.

Stan na 2026-10-10: łata jest przygotowana lokalnie, ale nie ma jeszcze commita
ani zgłoszenia. Nie masz konta Rockbox Gerrit. Teraz priorytetem jest HiBy;
ten poradnik możesz zachować na później. Żaden opisany krok publikacji nie
został wykonany podczas przygotowywania dokumentacji.

## 1. Co jest już przygotowane

- Łata: `D:/Rockbox/rockbox/installfiles/polish-upstream/rockbox-polish-fixes-20261010.patch`.
- SHA256: `a5ba9d510ea56529eb17504cceb00191371a157d70fd227450437de2cbf7951c`.
- Oddzielny checkout: `D:/work/Workspace/rockbox/polish-upstream-20261010/checkout`.
- Bieżąca gałąź: `polish-translation-fixes-20261010`.
- Baza: `7d090f24b990ef54e3f9dc7eb2edba4865605471`.
- Jedyny zmieniony plik: `apps/lang/polski.lang`; łata jest już zastosowana,
  zmiany nie są dodane do indeksu i nie są zatwierdzone.

Łata dotyczy 47 istniejących identyfikatorów i 77 pól tłumaczenia tekstu lub
mowy. Wynikowy `git diff --numstat` w checkoucie podaje 77 dodane i 77 usunięte
wiersze; surowy plik łaty ma statystyki 77/77. To różne reprezentacje tej
samej zmiany, nie dodatkowe zmienione pola. Łata nie zawiera 101 nowych identyfikatorów
integracji TTS/wtyczek, kodu eSpeak, HiBy ani tych poradników. Zachowaj ten
zakres. Główny katalog `D:/Rockbox/rockbox` zawiera inne niezakończone prace;
przyszłe zgłoszenie przygotowuj w oddzielnym checkoucie wskazanym powyżej.
Nie stosuj łaty drugi raz i nie twórz kolejnego checkoutu bez potrzeby.

Kontrola tylko do odczytu w PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:/Rockbox/rockbox/installfiles/polish-upstream/rockbox-polish-fixes-20261010.patch'
Set-Location 'D:/work/Workspace/rockbox/polish-upstream-20261010/checkout'
git branch --show-current
git status --short
git diff --cached --name-only
git diff --numstat
git diff --check
git apply --reverse --check 'D:/Rockbox/rockbox/installfiles/polish-upstream/rockbox-polish-fixes-20261010.patch'
```

Oczekiwane wyniki: powyższa gałąź, tylko ` M apps/lang/polski.lang`, pusty
indeks i `77 77 apps/lang/polski.lang`. Ostatnie dwa polecenia powinny zakończyć
się powodzeniem bez komunikatu. `--reverse --check` niczego nie cofa, tylko
sprawdza już zastosowaną łatę. Przy innym wyniku zatrzymaj przygotowanie i
wyjaśnij różnicę; nie resetuj ani nie chowaj istniejących zmian.

## 2. Oficjalna droga i granice weryfikacji

[Rockbox CONTRIBUTING](https://raw.githubusercontent.com/Rockbox/rockbox/master/docs/CONTRIBUTING)
kieruje kontrybutorów do przeglądu zmian w Gerricie. Oficjalne repozytorium
GitHub ma obecnie `has_pull_requests=false`, co sprawdzono w
[API GitHub](https://api.github.com/repos/Rockbox/rockbox). Fork ani upstreamowy
pull request nie są potrzebne do opisanej drogi Gerrit.

Oficjalny plik
[.gitreview](https://raw.githubusercontent.com/Rockbox/rockbox/master/.gitreview)
potwierdza host `gerrit.rockbox.org`, port SSH `29418`, projekt `rockbox.git`
i gałąź docelową `master`. To konfiguracja projektu, nie dowód, że logowanie
SSH działa dla Twojego konta.

Podczas sprawdzania [Gerrita Rockboksa](https://gerrit.rockbox.org/) oraz wiki
[UsingGit](https://www.rockbox.org/wiki/UsingGit) i
[WhyRealNames](https://www.rockbox.org/wiki/WhyRealNames) przeglądarka narzędzia
zwracała błędy, w tym 429, a bezpośredni HTTP zwracał stronę ochrony Anubis.
Ochrona zastąpiła też odpowiedzi `config/server/info`, `ssh_info`, dokumentację
instancji i plik hooka. HTTP 200 nie oznaczał otrzymania właściwej treści.
Nie potwierdzono rejestracji, dostawcy logowania, uprawnień, konfiguracji
uwierzytelniania ani adresu zapisu Git przez HTTPS na tej instancji.

Ogólne mechanizmy poniżej sprawdzono w oficjalnej dokumentacji Gerrita:
[wysyłanie zmian](https://gerrit-review.googlesource.com/Documentation/user-upload.html),
[Change-Id](https://gerrit-review.googlesource.com/Documentation/user-changeid.html)
i [hook commit-msg](https://gerrit-review.googlesource.com/Documentation/cmd-hook-commit-msg.html).
Obsługiwane opcje konkretnego serwera trzeba potwierdzić w jego interfejsie.

## 3. Konto i tożsamość: do ustalenia przed commitem

Gdy zechcesz wrócić do zgłoszenia, otwórz Gerrit Rockboksa w zwykłej
przeglądarce. Sprawdź, jakie oficjalne logowanie lub utworzenie konta faktycznie
oferuje. Nie zakładaj, że istnieje formularz „Register”, logowanie GitHub ani
automatyczne połączenie kont. Jeżeli właściwa strona lub sposób uzyskania konta
jest niedostępny, poproś opiekunów Rockboksa o aktualną instrukcję, korzystając
z kontaktu wskazanego w oficjalnej witrynie. Dalsze kroki wymagają działającego
konta i uprawnień do przesyłania zmian.

Są dwie odrębne informacje o autorze:

| Zastosowanie | Wymagana wartość |
| --- | --- |
| Pełne prawdziwe imię i nazwisko kontrybutora Rockboksa | Patryk Chojnacki |
| Git: autor i committer | `Patryk (Pates2004)` |
| Git: e-mail autora i committera | `255875083+Pates2004@users.noreply.github.com` |

Rockbox wymaga pełnego prawdziwego imienia i nazwiska także dla zmian
przekazywanych do Git. Ustawienie nazwiska w profilu lub treści commita nie
jest potwierdzonym rozwiązaniem różnicy względem wymaganego `user.name`.
Przed utworzeniem commita wyjaśnij z opiekunami, czy akceptują tę kombinację
z jawnym wskazaniem Patryka Chojnackiego. Jeśli wymagają zmiany tożsamości Git,
potrzebna jest Twoja wyraźna decyzja; nie zmieniaj jej automatycznie.

Adres GitHub `noreply` nie jest skrzynką do odbioru linku weryfikacyjnego.
Nie potwierdzono, czy Gerrit umożliwi jego przypisanie lub dopuści commit
z takim adresem. Nie zastępuj go innym adresem bez swojej wyraźnej decyzji.
Nazwa użytkownika Gerrita również nie musi być taka sama jak `Pates2004`.

Po rozstrzygnięciu tych kwestii poniższe polecenia w **Git Bash** ustawiają
tożsamość tylko dla oddzielnego checkoutu. Kolejne bloki Bash wykonuj w tej
samej sesji i po sprawdzeniu wyniku każdego kroku:

```bash
cd /d/work/Workspace/rockbox/polish-upstream-20261010/checkout
git config --local user.name "Patryk (Pates2004)"
git config --local user.email "255875083+Pates2004@users.noreply.github.com"
git config --show-origin --get user.name
git config --show-origin --get user.email
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Sprawdź autora i committera osobno: zmienne środowiskowe mogą nadpisać
konfigurację Git. Przy innej nazwie lub adresie zatrzymaj się przed commitem.
Powiązanie tożsamości z GitHubem nie zapewnia uprawnień w Gerricie. Jeśli
kiedyś opublikujesz commit także na GitHubie, sprawdź tam osobno powiązanie
autora i committera z `Pates2004`.

## 4. Wybierz faktycznie dostępny sposób połączenia

SSH i HTTP/HTTPS to możliwości Gerrita; nie każdy serwer udostępnia obie.
Wybierz jedną drogę wskazaną przez Rockbox dla Twojego konta.

### SSH, jeśli jest dostępne

Potwierdź nazwę użytkownika, host i port w interfejsie Gerrita. Jeżeli konto
oferuje klucze SSH, przypisz do niego wyłącznie **klucz publiczny** zgodnie
z aktualną instrukcją. Nie nadpisuj istniejącego klucza. Nie wysyłaj klucza
prywatnego ani hasła do niego.

Po takiej konfiguracji poniższy przykład sprawdza połączenie. Zastąp
`YOUR_GERRIT_USERNAME` własną potwierdzoną nazwą; nie wpisuj hasła w polecenie.
Przy pierwszym połączeniu zweryfikuj odcisk klucza hosta z zaufanym źródłem
Rockboksa przed jego zaakceptowaniem.

```bash
GERRIT_USER='YOUR_GERRIT_USERNAME'
ssh -p 29418 "${GERRIT_USER}@gerrit.rockbox.org"
```

Gerrit może potwierdzić uwierzytelnienie, a następnie zamknąć połączenie,
ponieważ nie oferuje interaktywnej powłoki. Błąd logowania lub odmowa dostępu
nie potwierdzają poprawnego przygotowania do wysyłki.

### HTTP/HTTPS, jeśli jest dostępne

Skopiuj **uwierzytelniony adres Git do wysyłania zmian** z interfejsu projektu
Rockbox. Nie zgaduj ścieżki na podstawie adresu strony, klonowania anonimowego
ani przykładu z innego serwera. Używaj HTTPS do przesyłania poświadczeń.

W zależności od konfiguracji serwer może używać osobnego hasła lub tokenu HTTP
albo innej wskazanej metody. Korzystaj tylko z opcji faktycznie dostępnej na
Twoim koncie. Nie zakładaj istnienia „Generate Password” ani zgodności hasła
webowego z Git. Podawaj sekret w zaufanym monicie uwierzytelniania, nigdy w URL,
historii poleceń, opisie zmiany, logach lub wiadomości do asystenta.

## 5. Oficjalny hook generujący Change-Id

Przed pierwszym commitem zainstaluj oficjalny hook `commit-msg` z serwera
Rockboksa. `Change-Id` identyfikuje przegląd Gerrita; nie jest SHA commita.
Poniższe przykłady dotyczą istniejącego oddzielnego checkoutu ze zwykłym `.git`.
Najpierw sprawdź konfigurację:

```bash
git config --show-origin --get core.hooksPath
git config --show-origin --get gerrit.createChangeId
git config --show-origin --get gerrit.reviewUrl
test ! -e .git/hooks/commit-msg
```

Brak ustawienia `--get` daje pusty wynik i kod 1; sam w sobie nie jest błędem.
Jeżeli `core.hooksPath` jest ustawione lub hook już istnieje, ustal właściwe
miejsce i zachowaj jego funkcję przed instalacją; nie nadpisuj go w ciemno.
`gerrit.createChangeId=false` wyłącza generowanie. W nowszych hookach
`gerrit.reviewUrl` może zastąpić linię `Change-Id` linią `Link`; nie zakładaj
obsługi tego wariantu przez Rockbox. Wyjaśnij te ustawienia przed kontynuacją.

Wybierz **jedną** metodę pobrania, dopiero gdy odpowiednia usługa działa.
Przykład SCP po potwierdzeniu uwierzytelniania SSH:

```bash
scp -p -P 29418 "${GERRIT_USER}@gerrit.rockbox.org:hooks/commit-msg" .git/hooks/commit-msg
```

Alternatywa HTTPS z oficjalnego endpointu, gdy zwraca właściwy skrypt:

```bash
curl --fail --location --proto '=https' --proto-redir '=https' --output .git/hooks/commit-msg https://gerrit.rockbox.org/tools/hooks/commit-msg
```

Podczas przygotowania poradnika endpoint HTTPS zwracał **HTML ochrony
antybotowej**. Nie pobieraj go teraz jako działającego hooka. Po przyszłym
pobraniu przeczytaj plik, potwierdź, że jest oficjalnym skryptem powłoki
`commit-msg`, a nie HTML ani komunikatem błędu. Dopiero wtedy:

```bash
chmod u+x .git/hooks/commit-msg
```

Nie uruchamiaj przypadkowego skryptu, nie wymyślaj ręcznie identyfikatora
i nie kopiuj Change-Id z cudzego commita. Gdy plik jest niewłaściwy, przerwij
przed commitem i uzyskaj prawidłowy hook oficjalną drogą.

## 6. Przegląd człowieka, pochodzenie i pierwszy commit

Sam wynik testów nie zastępuje przeglądu tłumaczenia. Przeczytaj całą łatę
i uzasadnij każde brzmienie. Zgodnie z `docs/CONTRIBUTING` ujawnij udział AI,
użyte narzędzia i potwierdzone modele, a także przygotuj się do wyjaśnienia
zmian. Rockbox uprzedza o małej szansie przyjęcia kodu wygenerowanego przez AI;
ujawnienie pochodzenia nie gwarantuje przeglądu ani akceptacji tłumaczenia.

Nie wszystkie modele użyte w historycznych zmianach zostały potwierdzone.
Podaj tę lukę uczciwie, zamiast przypisywać całej łacie model bieżącej sesji
dokumentacyjnej. Nie deklaruj przeglądu człowieka, odsłuchu, testu urządzenia
ani NVDA, dopóki rzeczywiście ich nie wykonasz. Rozróżnij wcześniejsze wyniki
kontroli katalogu od testów powtórzonych przed zgłoszeniem. Jeśli wymagane
pochodzenie pozostaje niewyjaśnione, ustal to przed publikacją z opiekunami.

Po zakończeniu powyższych ustaleń i przeglądu przygotuj tylko plik językowy:

```bash
git diff -- apps/lang/polski.lang
git diff --check
git add -- apps/lang/polski.lang
git diff --cached --name-only
git diff --cached --check
git diff --cached -- apps/lang/polski.lang
```

Indeks ma zawierać wyłącznie `apps/lang/polski.lang`. Gdy baza upstream zmieniła
się od podanej wersji, najpierw sprawdź zgodność łaty z aktualnym `master`,
rozwiąż ewentualne konflikty w oddzielnym checkoucie i powtórz odpowiednie
kontrole katalogu. Nie publikuj obcych commitów ani rozszerzonej integracji.

Utwórz jeden commit przez `git commit`, wpisując angielski opis w edytorze.
Poniższy tekst jest **szablonem do uzupełnienia**, a nie gotową deklaracją
przeglądu lub testów:

```text
lang: fix Polish translations

Correct existing Polish display and voice translations in polski.lang.

Contributor real name: Patryk Chojnacki
AI provenance: [verified tools/models for this patch and any unknown history]
Human review: [strings and meanings actually checked by a person]
Validation: [actual commands, results and remaining limitations]
```

Nie dopisuj fikcyjnego `Co-authored-by` ani oświadczenia `Signed-off-by`,
którego znaczenia nie potwierdzono. Hook ma dopisać linię
`Change-Id: I...` w stopce. Po commicie sprawdź:

```bash
git log -1 --format=fuller
git show --format=fuller --stat HEAD
git show --format= --name-only HEAD
git log -1 --format=%B
git status --short
```

Autor i committer muszą mieć wymaganą nazwę i e-mail; diff ma dotyczyć tylko
pliku językowego, opis ma zawierać uzupełnione pochodzenie i dokładnie jeden
właściwy Change-Id. Jeśli hook nie zadziałał, napraw jego instalację i użyj
`git commit --amend` przed wysłaniem; sprawdź ponownie całą wiadomość.

## 7. Wysłanie do przeglądu, kiedy zdecydujesz się wrócić

To etap publiczny. Przed nim ponownie sprawdź tożsamość, uprawnienia,
pochodzenie i zakres. Wysyłka do `refs/for/master` tworzy przegląd zmian;
nie oznacza włączenia łaty do Rockboksa. Nie wysyłaj bezpośrednio do `master`.

Dla potwierdzonej drogi SSH:

```bash
git push "ssh://${GERRIT_USER}@gerrit.rockbox.org:29418/rockbox.git" HEAD:refs/for/master
```

Albo dla potwierdzonej drogi HTTPS, po zastąpieniu całego przykładowego adresu
adresem Git z interfejsu Rockboksa, bez hasła lub tokenu:

```bash
GERRIT_PUSH_URL='PASTE_VERIFIED_HTTPS_GIT_URL'
git push "$GERRIT_PUSH_URL" HEAD:refs/for/master
```

Otwórz adres zmiany zwrócony przez serwer. Sprawdź projekt, `master`, pliki,
autora, committera i opis. Zapisz adres oraz numer przeglądu, aby móc do niego
wrócić. Błąd uwierzytelniania lub weryfikacji e-maila wymaga wyjaśnienia,
a nie zmiany adresu autora na przypadkowy ani udostępnienia sekretów.

## 8. Odpowiedzi na uwagi i kolejne wersje

Odpowiadaj w istniejącym przeglądzie. Dla poprawek tej samej zmiany edytuj plik
w tym samym checkoucie, powtórz właściwe kontrole, sprawdź tożsamość i wykonaj:

```bash
git add -- apps/lang/polski.lang
git diff --cached --check
git diff --cached --name-only
git commit --amend
git log -1 --format=fuller
git log -1 --format=%B
```

Zachowaj **ten sam Change-Id**, projekt `rockbox.git` i gałąź `master`, po czym
powtórz wybrane polecenie `git push ... HEAD:refs/for/master`. Gerrit powinien
dodać nowy patch set do istniejącego przeglądu; sprawdź to w interfejsie.
SHA commita może się zmienić po amend lub rebase. Nie twórz nowego commita
z nowym Change-Id ani nowego zgłoszenia dla każdej uwagi. Po ewentualnym
rebase również zachowaj ID. Włączenie zmiany zależy od przeglądu i uprawnień
opiekunów, a nie od samego udanego push.

## Co pozostaje niezweryfikowane

Instrukcja nie jest testem logowania, rejestracji, przypisania e-maila,
pobrania działającego hooka ani wysłania zmiany. Te etapy pozostają na później,
podobnie jak uzgodnienie pełnego nazwiska z wymaganą tożsamością Git i końcowy
przegląd człowieka. Nie przeprowadzono nowych buildów, odsłuchu, testów sprzętu
ani NVDA. Istniejąca łata i oddzielny checkout pozostają gotowe do dalszej pracy,
bez zobowiązania do zgłaszania ich teraz.
