# Współtworzenie AERO C14

Dziękujemy za zgłoszenia błędów, propozycje funkcji i poprawki. Przed rozpoczęciem większej zmiany opisz jej zakres w zgłoszeniu GitHub.

## Zgłoszenia błędów

Podaj wersję integracji i Home Assistant, model oraz firmware urządzenia, sposób połączenia i kroki odtworzenia problemu. Opisz oczekiwane zachowanie i rzeczywisty wynik.

Przed dołączeniem diagnostyki sprawdź jej zawartość. Nie publikuj haseł, tokenów, prywatnych adresów, konfiguracji instalacji ani zapisów transmisji magistrali.

## Proponowanie zmian

- Opisz problem i zakres poprawki.
- Zachowaj zgodność istniejących identyfikatorów urządzeń i encji.
- Nie usuwaj sprawdzania potwierdzeń, ograniczeń kolejki ani obsługi konfliktów magistrali.
- Podaj sposób i wynik weryfikacji zmienianej funkcji.
- Nie dołączaj testów opartych na przechwytach, logów transmisji ani materiałów badawczych.

Testy i dane wykorzystywane podczas rozwoju są utrzymywane poza publicznym repozytorium. Próby sprzętowe przeprowadzaj z możliwością przywrócenia nastaw. Nie ponawiaj zapisu, którego wyniku nie udało się potwierdzić.

## Struktura repozytorium

```text
custom_components/compit_aero4/
README.md
LICENSE
CONTRIBUTING.md
hacs.json
```

Nazwa katalogu i domena `compit_aero4` pozostają zachowane ze względu na zgodność konfiguracji Home Assistant. Nazwa wyświetlana projektu to **AERO C14 – Unofficial Home Assistant Integration**.

Przesyłając zmianę, zgadzasz się na jej udostępnienie na licencji MIT projektu. Nie dołączaj kodu, firmware ani dokumentacji osób trzecich bez odpowiednich uprawnień i spełnienia warunków ich licencji.
