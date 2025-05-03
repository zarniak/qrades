# 1. Zaimportuj potrzebną klasę
from flask import Flask, render_template # Importuj Flask i funkcję do renderowania szablonów
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure # Do obsługi błędów połączenia
from dotenv import load_dotenv
import os

# --- Konfiguracja ---
# Zmień te wartości, aby pasowały do Twojej konfiguracji
load_dotenv()
CONNECTION_STRING = os.getenv("CONNECTION_STRING1")
NAZWA_BAZY_DANYCH = "qrades"          # Zastąp nazwą swojej bazy danych
NAZWA_KOLEKCJI = "routes"       # Zastąp nazwą swojej kolekcji
# --------------------

# Inicjalizacja aplikacji Flask
app = Flask(__name__)

# Funkcja do pobierania danych z MongoDB
def pobierz_dane_z_mongo():
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
        # Pobierz wszystkie dokumenty i skonwertuj kursor na listę
        dokumenty = list(collection.find())

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

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)
