# 1. Zaimportuj potrzebną klasę
from flask import Flask, render_template, Response # Importuj Flask i funkcję do renderowania szablonów
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure # Do obsługi błędów połączenia
from bson.objectid import ObjectId
from bson.errors import InvalidId # Importujemy do obsługi błędów konwersji ObjectId
from dotenv import load_dotenv
from io import BytesIO
import os
import qrcode

# 1. Zdefiniuj bazowy URL (stała część linku)
base_url = "http://127.0.0.1:5000/" # Zmień na swój link

# --- Konfiguracja ---
# Zmień te wartości, aby pasowały do Twojej konfiguracji
load_dotenv()
CONNECTION_STRING = os.getenv("CONNECTION_STRING1")
NAZWA_BAZY_DANYCH = "qrades"          # Zastąp nazwą swojej bazy danych
NAZWA_KOLEKCJI = "ascends"       # Zastąp nazwą swojej kolekcji
# --------------------

# Inicjalizacja aplikacji Flask
app = Flask(__name__)

def statystyka_trudnosci_drogi(dynamic_route_id_obj):
    # Definicja potoku agregacji
    pipeline = [
        {
            # Etap $match do filtrowania według dynamicznego route_id
            '$match': {
                'route_id': dynamic_route_id_obj  # Używamy skonwertowanego ObjectId
            }
        },
        {
            '$lookup': {
                'from': 'routes',  # Kolekcja do połączenia
                'localField': 'route_id',  # Pole z kolekcji 'ascends'
                'foreignField': '_id',  # Pole z kolekcji 'routes'
                'as': 'route_info'  # Nazwa nowego pola zawierającego dopasowane dokumenty
            }
        },
        {
            '$unwind': '$route_info'  # Dekonstrukcja tablicy (zakładamy 1:1 match)
        },
        {
            # NOWY ETAP: $group - Grupowanie według wartości pola 'grade'
            '$group': {
                '_id': '$grade',  # Grupowanie po wartości pola 'grade' z dokumentów wchodzących do tego etapu
                # $grade odnosi się do pola 'grade' z oryginalnego dokumentu ascends
                'count': {'$sum': 1}  # Zliczenie liczby dokumentów w każdej grupie (dla każdej unikalnej oceny)
            }
            # Wyjście z tego etapu będzie wyglądać np. [{'_id': 5, 'count': 10}, {'_id': 4, 'count': 7}, ...]
            # Gdzie _id to wartość oceny, a count to jej liczność
        },
        {
            '$project': {
            '_id': 0,  # Wykluczamy domyślne pole _id z etapu $group
            'grade': '$_id', # Tworzymy nowe pole 'grade' z wartości pola '_id' z poprzedniego etapu
            'count': 1 # Zachowujemy pole 'count'
        }
        }
    ]
    return pobierz_dane_z_mongo(pipeline)

def statystyka_oceny_drogi(dynamic_route_id_obj):
    # Definicja potoku agregacji
    pipeline = [
        {
            # Etap $match do filtrowania według dynamicznego route_id
            '$match': {
                'route_id': dynamic_route_id_obj  # Używamy skonwertowanego ObjectId
            }
        },
        {
            '$lookup': {
                'from': 'routes',  # Kolekcja do połączenia
                'localField': 'route_id',  # Pole z kolekcji 'ascends'
                'foreignField': '_id',  # Pole z kolekcji 'routes'
                'as': 'route_info'  # Nazwa nowego pola zawierającego dopasowane dokumenty
            }
        },
        {
            '$unwind': '$route_info'  # Dekonstrukcja tablicy (zakładamy 1:1 match)
        },
        {
            # NOWY ETAP: $group - Grupowanie wszystkich pasujących dokumentów w jedną grupę
            '$group': {
                '_id': 0,  # Grupowanie po null umieszcza wszystkie dokumenty w tym etapie w jednej grupie
                'average_review': {'$avg': '$review'}  # Użycie akumulatora $avg do obliczenia średniej z pola 'review'
                # '$review' odnosi się do pola 'review' z dokumentów wchodzących do tego etapu
            }
            # Wyjście z tego etapu będzie jednym dokumentem np.:
            # [{'_id': null, 'average_review': 4.5}]
        },
        {
            # Opcjonalny etap: $project - Zmiana kształtu wyjścia dla lepszej czytelności
            # Usuwa pole '_id': null i pozostawia tylko pole 'average_review'
            '$project': {
                '_id': 0,  # Wykluczamy domyślne pole _id z etapu $group
                'average_review': 1  # Zachowujemy pole 'average_review'
            }
            # Wyjście będzie teraz jednym dokumentem np.:
            # [{'average_review': 4.5}]
        }
    ]

    return pobierz_dane_z_mongo(pipeline)

def wszystkie_dane_z_bazy(dynamic_route_id_obj = None):
    # Definicja potoku agregacji
    pipeline = [
        {
            '$lookup': {
                'from': 'routes',  # Kolekcja do połączenia
                'localField': 'route_id',  # Pole z kolekcji 'ascends'
                'foreignField': '_id',  # Pole z kolekcji 'routes'
                'as': 'route_info'  # Nazwa nowego pola zawierającego dopasowane dokumenty
            }
        },
        {
            '$unwind': '$route_info'  # Dekonstrukcja tablicy (zakładamy 1:1 match)
        },
        {
            '$lookup': {
                'from': 'users',  # Kolekcja do połączenia
                'localField': 'user_id',  # Pole z kolekcji 'ascends'
                'foreignField': '_id',  # Pole z kolekcji 'users'
                'as': 'user_info'  # Nazwa nowego pola zawierającego dopasowane dokumenty
            }
        },
        {
            '$unwind': '$user_info'  # Dekonstrukcja tablicy (zakładamy 1:1 match)
        },
        {
            '$project': {  # Etap do kształtowania wyjścia
                '_id': 1,  # Zachowaj oryginalne _id z ascends
                'grade': 1,  # Zachowaj pole grade z ascends
                'review': 1,  # Zachowaj pole review z ascends
                'route_id': 1,  # Zachowaj route_id z ascends
                'user_id': 1,  # Zachowaj user_id z ascends
                'route_name': '$route_info.name',  # Pobierz name z połączonego dokumentu route
                'route_grade': '$route_info.grade',  # Pobierz grade z połączonego dokumentu route
                'user_name': '$user_info.name'  # Pobierz name z połączonego dokumentu user
            }
        }
    ]

    if (dynamic_route_id_obj):
        pipeline.append({
            # Etap $match do filtrowania według dynamicznego route_id
            '$match': {
                'route_id': dynamic_route_id_obj  # Używamy skonwertowanego ObjectId
            }
        })
    return pobierz_dane_z_mongo(pipeline)


# Funkcja do pobierania danych z MongoDB
def pobierz_dane_z_mongo(pipeline):
    """Łączy się z MongoDB, pobiera wszystkie dokumenty z kolekcji i je zwraca."""
    client = None
    dokumenty = []
    error_message = None
    try:
        client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000) # Timeout po 5s
        # Sprawdzenie połączenia
        client.admin.command('ismaster')
        db = client[NAZWA_BAZY_DANYCH]
        collection = db[NAZWA_KOLEKCJI]


        # Wykonanie agregacji
        dokumenty = list(collection.aggregate(pipeline))

#        print("Wyniki agregacji:")
#        for doc in dokumenty:
#            print(doc)

    except ConnectionFailure:
        error_message = "Błąd: Nie można połączyć się z serwerem MongoDB. Sprawdź, czy jest uruchomiony."
        print(error_message) # Logowanie błędu w konsoli serwera
    except Exception as e:
        error_message = f"Wystąpił nieoczekiwany błąd podczas pobierania danych: {e}"
        print(error_message) # Logowanie błędu
    finally:
        if client:
            client.close()
    return dokumenty, error_message

# Funkcja do pobierania danych z MongoDB
def generuj_qr_code(dynamic_route_id_obj = None):
    """Łączy się z MongoDB, pobiera wszystkie dokumenty z kolekcji i je zwraca."""

    pelny_url = f"{base_url}{dynamic_route_id_obj}"

    # 5. Wygeneruj kod QR
    # qrcode.QRCode() - Konfiguracja wyglądu/właściwości QR kodu
    # version: rozmiar kodu (None = automatyczny, 1 do 40)
    # error_correction: poziom korekcji błędów (L, M, Q, H)
    # box_size: rozmiar pojedynczego kwadratu w pikselach
    # border: grubość ramki wokół kodu
    qr = qrcode.QRCode(
        version=None,  # Automatyczny dobór wersji
        error_correction=qrcode.constants.ERROR_CORRECT_L,  # Niski poziom korekcji błędów
        box_size=10,
        border=4,
    )

    # Dodaj dane (URL) do kodu QR
    qr.add_data(pelny_url)
    # Dopasuj rozmiar kodu (wymagane po add_data() jeśli version=None)
    qr.make(fit=True)

    # Utwórz obraz kodu QR
    # fill_color i back_color definiują kolory kwadratów i tła
    img = qr.make_image(fill_color="black", back_color="white")


    # 6. Zapisz kod QR do pliku
    # Nazwa pliku będzie zawierać zmienny parametr, żeby łatwo je zidentyfikować
    nazwa_pliku = f"qr_codes/kod_qr_{dynamic_route_id_obj}.png"

    try:
        img.save(nazwa_pliku)
        print(f"Zapisano: {nazwa_pliku}")
    except Exception as e:
        print(f"Wystąpił błąd podczas zapisu pliku {nazwa_pliku}: {e}")

#    print("Wyniki agregacji:")
#    for doc in dokumenty:
#        print(doc)
    #- Zapisz obraz do bufora w pamięci ---
    buffer = BytesIO()
    img.save(buffer, format='PNG') # Zapisz obraz do bufora jako PNG
    buffer.seek(0) # Przewiń bufor na początek

    # --- Zwróć dane obrazu jako odpowiedź HTTP ---
    return Response(buffer.getvalue(), mimetype='image/png')

# Definicja głównej trasy (route) dla strony
@app.route('/') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def index():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = wszystkie_dane_z_bazy()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('index.html', dane=dane_z_bazy, error=blad)

@app.route('/<route_id_str>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def get_ascends_by_route(route_id_str):
    # --- Konwersja stringa route_id na ObjectId ---
     try:
        dynamic_route_id_obj = ObjectId(route_id_str)
        # Pobierz dane przy każdym żądaniu strony
        trudnosci_drog, blad = statystyka_trudnosci_drogi(dynamic_route_id_obj)

        # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
        # Flask automatycznie szuka szablonów w folderze 'templates'

        etykiety = [item['grade'] for item in trudnosci_drog]  # Lista ocen
        wartosci = [item['count'] for item in trudnosci_drog]  # Lista liczności

        ocena_drogi, blad = statystyka_oceny_drogi(dynamic_route_id_obj)

        ocena = ocena_drogi[0].get('average_review')

        return render_template('route_stat.html', etykiety=etykiety, wartosci=wartosci, average_review=ocena, error=blad)
     except InvalidId:
        print(f"Błąd: '{route_id_str}' nie jest prawidłowym ObjectId.")
        # Tutaj obsłuż błąd - np. zwróć błąd 400 w aplikacji webowej
        exit() # Na potrzeby przykładu zakończ działanie skryptu

@app.route('/qr/<route_id_str>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def get_qr_by_route(route_id_str):
    # --- Konwersja stringa route_id na ObjectId ---
     try:
        dynamic_route_id_obj = ObjectId(route_id_str)
        # Pobierz dane przy każdym żądaniu strony


        # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
        # Flask automatycznie szuka szablonów w folderze 'templates'
        return generuj_qr_code(dynamic_route_id_obj)
     except InvalidId:
        print(f"Błąd: '{route_id_str}' nie jest prawidłowym ObjectId.")
        # Tutaj obsłuż błąd - np. zwróć błąd 400 w aplikacji webowej
        exit() # Na potrzeby przykładu zakończ działanie skryptu

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)
