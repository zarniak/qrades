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
            # Etap 2: $project - Określ, które pola mają być zwrócone i w jakiej formie
            # '{поле: 1}' oznacza, że pole ma być włączone do wyniku (1 to true)
            # Pola wymienione w przykładzie struktury to _id, name, grade
            '$project': {
                '_id': 1,  # Włącz pole _id
                'name': 1,  # Włącz pole name
                'grade': 1  # Włącz pole grade
                # Jeśli chcesz wyświetlić *wszystkie* pola, a nie tylko te z przykładu,
                # i nie wiesz z góry wszystkich nazw, możesz użyć:
                # '$project': { $mergeObjects: '$$ROOT' } # Kopiuje cały dokument wejściowy do nowego pola, a potem...
                # Ale do prostego wyświetlenia tych trzech pól, lepiej jawnie je wymienić.
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
    pelny_url = f"{base_url}{dynamic_route_id_obj}"

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
@app.route('/') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def index():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = wszystkie_drogi()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('index.html', dane=dane_z_bazy, error=blad)

@app.route('/<route_id_str>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
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

        return render_template('route.html', etykiety=etykiety, wartosci=wartosci,
                               average_review=ocena_drogi[0].get('average_review'),
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

    # --- 2. Walidacja i konwersja danych ---
    errors = []
    review_int = None

    # Walidacja grade
    if not grade or not grade.strip():
         errors.append("Pole 'Ocena' jest wymagane.")
    else:
         grade = grade.strip() # Usuń białe znaki z początku/końca

    # Walidacja review (zakładamy liczbę całkowitą, np. 1-5)
    if not review_str:
         errors.append("Pole 'Recenzja' jest wymagane.")
    else:
        try:
            review_int = int(review_str) # Konwersja stringa na liczbę całkowitą
            # Opcjonalna walidacja zakresu, np. 1-5
            if not (1 <= review_int <= 5):
                errors.append("Pole 'Recenzja' musi być liczbą od 1 do 5.")
                review_int = None
        except ValueError:
            errors.append("Pole 'Recenzja' musi być liczbą całkowitą.")
            review_int = None

    # Walidacja user
    if not user or not user.strip():
        errors.append("Pole 'Użytkownik' jest wymagane.")
    else:
        user = user.strip() # Usuń białe znaki z początku/końca
    # --- 3. Jeśli są błędy, wyświetl je ponownie w formularzu ---
    if errors:
        for error in errors:
            flash(error, 'error') # Użyj flash messages do przekazania błędów
        # Przekaż wprowadzone dane z powrotem do szablonu, żeby użytkownik nie musiał wpisywać od nowa
        return render_template('add_ascend.html',
                               initial_data={'route_id': ObjectId(route_id_str),
                                             'grade': grade,
                                             'review': review_str,
                                             'user': user})

    # --- 4. Jeśli brak błędów, przygotuj dokument i zapisz w bazie ---
    try:
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

        response = make_response(redirect(url_for('index')))  # Przekieruj np. na stronę główną po sukcesie
        response.set_cookie('user_name', user, max_age=30 * 24 * 60 * 60, httponly=True,
                            secure=True)  # secure=True w produkcji

        # Sprawdź, czy wstawienie się powiodło
        if result.inserted_id:
            flash(f"Wpis został pomyślnie dodany! ID: {result.inserted_id}", 'success')
        else:
             # To raczej nie powinno się zdarzyć przy insert_one, ale na wszelki wypadek
             flash("Wystąpił błąd podczas zapisywania wpisu w bazie.", 'error')

    except Exception as e:
        flash(f"Wystąpił błąd bazy danych: {e}", 'error')
        # Przekaż wprowadzone dane z powrotem, żeby użytkownik mógł poprawić
        return render_template('add_ascend.html',
                               initial_data={'route_id': ObjectId(route_id_str),
                                             'grade': grade,
                                             'review': review_str,
                                             'user': user})

        # --- 5. Przekieruj po pomyślnym dodaniu ---
        # Przekierowanie do tej samej trasy (metodą GET) zapobiega ponownemu wysłaniu formularza po odświeżeniu strony

    return response

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)