# 1. Zaimportuj potrzebną klasę
from flask import Flask, render_template # Importuj Flask i funkcję do renderowania szablonów
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure # Do obsługi błędów połączenia
from bson.objectid import ObjectId
from bson.errors import InvalidId # Importujemy do obsługi błędów konwersji ObjectId
from dotenv import load_dotenv
import os

# --- Konfiguracja ---
# Zmień te wartości, aby pasowały do Twojej konfiguracji
load_dotenv()
CONNECTION_STRING = os.getenv("CONNECTION_STRING1")
NAZWA_BAZY_DANYCH = "qrades"          # Zastąp nazwą swojej bazy danych
NAZWA_KOLEKCJI = "ascends"       # Zastąp nazwą swojej kolekcji
# --------------------

# Inicjalizacja aplikacji Flask
app = Flask(__name__)

# Funkcja do pobierania danych z MongoDB
def pobierz_dane_z_mongo(dynamic_route_id_obj = None):
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
            pipeline.append( {
               # Etap $match do filtrowania według dynamicznego route_id
               '$match': {
                   'route_id': dynamic_route_id_obj  # Używamy skonwertowanego ObjectId
               }
           })

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

# Definicja głównej trasy (route) dla strony
@app.route('/') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def index():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = pobierz_dane_z_mongo()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('index.html', dane=dane_z_bazy, error=blad)

@app.route('/<route_id_str>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def get_ascends_by_route(route_id_str):
    # --- Konwersja stringa route_id na ObjectId ---
     try:
        dynamic_route_id_obj = ObjectId(route_id_str)
        # Pobierz dane przy każdym żądaniu strony
        dane_z_bazy, blad = pobierz_dane_z_mongo(dynamic_route_id_obj)

        # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
        # Flask automatycznie szuka szablonów w folderze 'templates'
        return render_template('index.html', dane=dane_z_bazy, error=blad)
     except InvalidId:
        print(f"Błąd: '{route_id_str}' nie jest prawidłowym ObjectId.")
        # Tutaj obsłuż błąd - np. zwróć błąd 400 w aplikacji webowej
        exit() # Na potrzeby przykładu zakończ działanie skryptu

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)
