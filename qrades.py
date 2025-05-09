from flask import Flask, render_template, Response, request, redirect, url_for, flash, make_response
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from io import BytesIO
import os
import qrcode
import datetime # Do ustawienia daty ważności cookie

base_url = "https://qrades.onrender.com/"

load_dotenv()
#CONNECTION_STRING = os.getenv("CONNECTION_STRING")
CONNECTION_STRING = os.environ.get('CONNECTION_STRING')
NAZWA_BAZY_DANYCH = "qrades"
NAZWA_KOLEKCJI = "ascends"

# Inicjalizacja aplikacji Flask
app = Flask(__name__)

# Ustawianie SECRET_KEY jest potrzebne do działania flash messages
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'fallback_secret_key') # Fallback na wypadek braku w .env

def statystyka_trudnosci_drogi(dynamic_route_id_obj):
    # Definicja potoku agregacji
    pipeline = [
        {
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
                'count': {'$sum': 1}  # Zliczenie liczby dokumentów w każdej grupie (dla każdej unikalnej oceny)
            }
        },
        {
            '$project': {
            '_id': 0,  # Wykluczamy domyślne pole _id z etapu $group
            'grade': '$_id', # Tworzymy nowe pole 'grade' z wartości pola '_id' z poprzedniego etapu
            'count': 1 # Zachowujemy pole 'count'
        }
        },
        {
            # ### NOWY ETAP: $sort - Sortowanie wyników ###
            '$sort': {
                'grade': 1  # Sortujemy po polu 'grade' utworzonym w poprzednim etapie
                # 1 oznacza sortowanie rosnące (np. "4a", "5a", "6a", "6b", ...)
                # -1 oznacza sortowanie malejące
            }
        }
    ]
    return pobierz_dane_z_mongo(pipeline, "ascends")

def statystyka_oceny_drogi(dynamic_route_id_obj):
    pipeline = [
        {
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
            '$group': {
                '_id': 0,  # Grupowanie po null umieszcza wszystkie dokumenty w tym etapie w jednej grupie
                'average_review': {'$avg': '$review'}  # Użycie akumulatora $avg do obliczenia średniej z pola 'review'
                # '$review' odnosi się do pola 'review' z dokumentów wchodzących do tego etapu
            }
        },
        {
            '$project': {
                '_id': 0,  # Wykluczamy domyślne pole _id z etapu $group
                'average_review': 1  # Zachowujemy pole 'average_review'
            }
        }
    ]
    return pobierz_dane_z_mongo(pipeline ,"ascends")

def wszystkie_dane_z_bazy(dynamic_route_id_obj = None):
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
            '$project': {  # Etap do kształtowania wyjścia
                '_id': 1,  # Zachowaj oryginalne _id z ascends
                'grade': 1,  # Zachowaj pole grade z ascends
                'review': 1,  # Zachowaj pole review z ascends
                'route_id': 1,  # Zachowaj route_id z ascends
                'user_id': 1,  # Zachowaj user_id z ascends
                'route_name': '$route_info.name',  # Pobierz name z połączonego dokumentu route
                'route_grade': '$route_info.grade',  # Pobierz grade z połączonego dokumentu route
            }
        }
    ]
    if dynamic_route_id_obj:
        pipeline.append({
            # Etap $match do filtrowania według dynamicznego route_id
            '$match': {
                'route_id': dynamic_route_id_obj  # Używamy skonwertowanego ObjectId
            }
        })
    return pobierz_dane_z_mongo(pipeline, "ascends")

def wszystkie_drogi():
    pipeline = [
        {
            '$project': {
                'route_id': 1,  # Włącz pole _id
                'name': 1,  # Włącz pole name
            }
        }
    ]
    return pobierz_dane_z_mongo(pipeline, "routes")

def pobierz_dane_z_mongo(pipeline, kolekcja):
    client = None
    dokumenty = []
    error_message = None
    try:
        client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000) # Timeout po 5s
        # Sprawdzenie połączenia
        client.admin.command('ismaster')
        db = client[NAZWA_BAZY_DANYCH]
        collection = db[kolekcja]

        # Wykonanie agregacji
        dokumenty = list(collection.aggregate(pipeline))

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

def generuj_qr_code(dynamic_route_id_obj = None):
    pelny_url = f"{base_url}route/{dynamic_route_id_obj}"

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

    #- Zapisz obraz do bufora w pamięci ---
    buffer = BytesIO()
    img.save(buffer, format='PNG') # Zapisz obraz do bufora jako PNG
    buffer.seek(0) # Przewiń bufor na początek

    # --- Zwróć dane obrazu jako odpowiedź HTTP ---
    return Response(buffer.getvalue(), mimetype='image/png')

# Definicja głównej trasy (route) dla strony
@app.route('/')  # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def index():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = wszystkie_drogi()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('index.html', dane=dane_z_bazy, error=blad)

@app.route('/all_data') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def all_data():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = wszystkie_drogi()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('all_data.html', dane=dane_z_bazy, error=blad)

@app.route('/<route_id_str>')
@app.route('/route/<route_id_str>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def ascends_by_route(route_id_str):
    # --- Konwersja stringa route_id na ObjectId ---
     try:
        user_from_cookie = request.cookies.get('user_name')

        dynamic_route_id_obj = ObjectId(route_id_str)
        # Pobierz dane przy każdym żądaniu strony
        trudnosci_drog, blad = statystyka_trudnosci_drogi(dynamic_route_id_obj)

        etykiety = [item['grade'] for item in trudnosci_drog]  # Lista ocen
        wartosci = [item['count'] for item in trudnosci_drog]  # Lista liczności

        ocena_drogi, blad = statystyka_oceny_drogi(dynamic_route_id_obj)

        average_review = ocena_drogi[0].get('average_review') if ocena_drogi and ocena_drogi[0].get(
            'average_review') is not None else 3

        return render_template('route.html', etykiety=etykiety, wartosci=wartosci,
                               average_review=average_review,
                               initial_data={'route_id': ObjectId(route_id_str), 'user': user_from_cookie}, error=blad)
     except InvalidId:
        print(f"Błąd: '{route_id_str}' nie jest prawidłowym ObjectId.")
        # Tutaj obsłuż błąd - np. zwróć błąd 400 w aplikacji webowej
        exit() # Na potrzeby przykładu zakończ działanie skryptu

@app.route('/qr/<route_id_str>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def get_qr_by_route(route_id_str):
    # --- Konwersja stringa route_id na ObjectId ---
     try:
        dynamic_route_id_obj = ObjectId(route_id_str)
        return generuj_qr_code(dynamic_route_id_obj)
     except InvalidId:
        print(f"Błąd: '{route_id_str}' nie jest prawidłowym ObjectId.")
        # Tutaj obsłuż błąd - np. zwróć błąd 400 w aplikacji webowej
        exit() # Na potrzeby przykładu zakończ działanie skryptu

# Obsługuje GET (wyświetlenie formularza) i POST (przetwarzanie danych)
@app.route('/add_ascend', methods=['POST'])
def add_ascend():
    # --- 1. Pobierz dane z formularza ---
    route_id_str = request.form.get('route_id')
    grade = request.form.get('grade')
    review_str = request.form.get('review')
    user = request.form.get('user')

    grade = grade.strip() # Usuń białe znaki z początku/końca
    review_int = int(review_str) # Konwersja stringa na liczbę całkowitą
    user = user.strip() # Usuń białe znaki z początku/końca

    new_ascend_document = {
        "route_id": ObjectId(route_id_str),
        "grade": grade,
        "review": review_int,     # Użyj skonwertowanej liczby całkowitej
        "user": user
        # _id zostanie automatycznie dodane przez MongoDB
    }

    # Wstaw dokument do kolekcji
    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)  # Timeout po 5s
    # Sprawdzenie połączenia
    client.admin.command('ismaster')
    db = client[NAZWA_BAZY_DANYCH]
    collection = db["ascends"]

    result = collection.insert_one(new_ascend_document)

    client.close()

    response = make_response(redirect(url_for('ascends_by_route', route_id_str=route_id_str)))  # Przekieruj np. na stronę główną po sukcesie
    response.set_cookie('user_name', user, max_age=30 * 24 * 60 * 60, httponly=True,
                        secure=True)  # secure=True w produkcji

    return response

@app.route('/new_route') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def new_route():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = wszystkie_drogi()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('new_route.html', dane=dane_z_bazy, error=blad)


@app.route('/add_route', methods=['POST'])
def add_route():
    # --- 1. Pobierz dane z formularza ---
    grade = request.form.get('grade')
    name = request.form.get('name')
    user = request.form.get('user')

    grade = grade.strip() # Usuń białe znaki z początku/końca
    user = user.strip() # Usuń białe znaki z początku/końca
    name = name.strip()  # Usuń białe znaki z początku/końca

    new_route_document = {
        "name": name,
        # _id zostanie automatycznie dodane przez MongoDB
    }

    # Wstaw dokument do kolekcji
    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)  # Timeout po 5s
    # Sprawdzenie połączenia
    client.admin.command('ismaster')
    db = client[NAZWA_BAZY_DANYCH]
    collection = db["routes"]

    result = collection.insert_one(new_route_document)

    collection = db["ascends"]

    new_ascend_document = {
        "route_id": result.inserted_id,
        "grade": grade,
        "user": user
        # _id zostanie automatycznie dodane przez MongoDB
    }

    result = collection.insert_one(new_ascend_document)

    client.close()

    response = make_response(redirect(url_for('all_data')))  # Przekieruj np. na stronę główną po sukcesie
    return response

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)