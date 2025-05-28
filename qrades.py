from flask import Flask, render_template, Response, request, redirect, url_for, make_response, send_file, flash
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId
from dotenv import load_dotenv
from io import BytesIO
import os
import qrcode
from openpyxl import Workbook
import datetime # Do ustawienia daty ważności cookie

base_url = "https://qrades.com/"

load_dotenv()
CONNECTION_STRING = os.environ.get('CONNECTION_STRING')
NAZWA_BAZY_DANYCH = "qrades"
NAZWA_KOLEKCJI = "ascends"

app = Flask(__name__) # Inicjalizacja aplikacji Flask

# Ustawianie SECRET_KEY jest potrzebne do działania flash messages
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'fallback_secret_key') # Fallback na wypadek braku w .env

# --- Pełna skala trudności wspinaczkowej (globalna stała) ---
CLIMBING_GRADES = ['4a', '4b', '4c', '5a', '5b', '5c', '6a', '6b', '6c', '7a', '7b', '7c']

def grades_by_route(dynamic_route_id_obj):
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

def avg_review_by_route(dynamic_route_id_obj):
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


def all_ascends_by_user_for_scatter(user_id):
    pipeline = [
        {
            '$match': {
                'user': user_id
            }
        },
        {
            '$lookup': {
                'from': 'routes',
                'localField': 'route_id',
                'foreignField': '_id',
                'as': 'route_info'
            }
        },
        {
            '$unwind': {
                'path': '$route_info',
                'preserveNullAndEmptyArrays': True # Zachowaj przejścia nawet bez pasującej trasy
            }
        },
        {
            '$project': {
                '_id': 1, # Ukryj domyślne _id przejścia
                'grade': 1, # Stopień trudności przejścia
                'review': 1, # Recenzja przejścia
                'created_at': 1, # Data utworzenia przejścia
                'route_id': '$route_id', # ObjectId trasy
                'user': 1, # Nazwa użytkownika
                'route_name': { '$ifNull': ['$route_info.name', 'Nieznana Trasa'] }, # Nazwa trasy z routes
            }
        },
        {
            '$sort': {
                'created_at': 1 # Sortuj chronologicznie dla wykresu
            }
        }
    ]

    return pobierz_dane_z_mongo(pipeline, "ascends")

def all_ascends_by_user(user_id):
    pipeline = [
        {
            '$match': {
                'user': user_id
            }
        },
        {
            '$lookup': {
                'from': 'routes',
                'localField': 'route_id',
                'foreignField': '_id',
                'as': 'route_info'
            }
        },
        {
            '$unwind': {
                'path': '$route_info',
            }
        },
        {
            '$project': {

                '_id': '$route_id',
                'id': { '$concat': [{'$substrCP': [{'$toString': '$route_id'}, 0, 7]}, '...'] },
                'Name': { '$concat': [{'$substrCP': [{'$toString': '$route_info.name'}, 0, 7]}, '...'] },  # Nazwa trasy
                'Grade': '$grade',  # Najczęściej występująca ocena z wpisów
                'Review': {'$round': ['$review', 1]},  # Średnia recenzja, zaokrąglona do 1 miejsca po przecinku
                'Date': {
                    '$dateToString': {
                        'format': "%Y-%m-%d %H:%M",  # Format daty, godziny i minuty
                        'date': "$created_at"  # Najnowsza data wpisu (z kolekcji ascends)
                    }
                }
            }
        },
        {
            '$sort': {
                'created_at': 1 # Sortuj chronologicznie dla wykresu
            }
        }
    ]

    return pobierz_dane_z_mongo(pipeline, "ascends")

def grades_by_user(user_id):
    pipeline = [
        {
            '$match': {
                'user': user_id  # Używamy skonwertowanego ObjectId
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

def get_all_data():
    pipeline = [
        # Etap 1: Grupuj wpisy z 'ascends' po 'route_id'
        # Oblicz średnią recenzję, zbierz wszystkie oceny dla późniejszego wyznaczenia najczęściej występującej
        # ORAZ znajdź najnowszą datę utworzenia wpisu z kolekcji 'ascends'
        {
            '$group': {
                '_id': '$route_id',
                'average_review': { '$avg': '$review' },
                'grades_for_mode': { '$push': '$grade' },
                'latest_ascend_date': { '$max': '$created_at' } # DODANO: Najnowsza data z ascends
            }
        },
        # Etap 2: Dołącz informacje o trasie z kolekcji 'routes'
        {
            '$lookup': {
                'from': 'routes',
                'localField': '_id',
                'foreignField': '_id',
                'as': 'route_info'
            }
        },
        # Etap 3: Rozwiń tablicę 'route_info' (zakładamy, że każdy route_id pasuje do jednej trasy)
        {
            '$unwind': '$route_info'
        },
        # Etap 4: Oblicz najczęściej występującą ocenę
        # Tworzy mapę częstotliwości ocen dla każdej trasy
        {
            '$addFields': {
                'grade_frequency_map': {
                    '$reduce': {
                        'input': '$grades_for_mode',
                        'initialValue': {},
                        'in': {
                            '$mergeObjects': [
                                '$$value',
                                { '$arrayToObject': [[{
                                    'k': '$$this',
                                    'v': { '$add': [{ '$ifNull': [{ '$getField': '$$this' }, 0] }, 1] }
                                }]] }
                            ]
                        }
                    }
                }
            }
        },

        {
            '$addFields': {
                'most_frequent_grade': {
                    '$let': {
                        'vars': { 'gradesArray': { '$objectToArray': '$grade_frequency_map' } },
                        'in': {
                            '$arrayElemAt': [
                                { '$map': {
                                    'input': '$$gradesArray',
                                    'as': 'item',
                                    'in': '$$item.k'
                                }},
                                { '$indexOfArray': [
                                    { '$map': {
                                        'input': '$$gradesArray',
                                        'as': 'item',
                                        'in': '$$item.v'
                                    }},
                                    { '$max': '$$gradesArray.v' }
                                ]}
                            ]
                        }
                    }
                }
            }
        },

        {
            '$project': {
                'id': { '$concat': [{'$substrCP': [{'$toString': '$route_info._id'}, 0, 7]}, '...'] },
                'Created': {
                    '$dateToString': {
                        'format': "%Y-%m-%d %H:%M",  # Format daty, godziny i minuty
                        'date': "$route_info.created_at"  # Data utworzenia trasy (z kolekcji routes)
                    }
                },
                'Name': { '$concat': [{'$substrCP': [{'$toString': '$route_info.name'}, 0, 7]}, '...'] },  # Nazwa trasy
                'Grade': '$most_frequent_grade',  # Najczęściej występująca ocena z wpisów
                'Review': {'$round': ['$average_review', 1]},  # Średnia recenzja, zaokrąglona do 1 miejsca po przecinku
                'Last ascend': {
                    '$dateToString': {
                        'format': "%Y-%m-%d %H:%M",  # Format daty, godziny i minuty
                        'date': "$latest_ascend_date"  # Najnowsza data wpisu (z kolekcji ascends)
                    }
                }
            }
        }
    ]

    return pobierz_dane_z_mongo(pipeline, "ascends")

def top_10_routes_by_rating():
    pipeline = [
        {
            # Zgrupuj przejścia po route_id i oblicz średnią ocenę (review)
            '$group': {
                '_id': '$route_id',
                'average_review': { '$avg': '$review' }
            }
        },
        {
            # Dołącz informacje o trasie z kolekcji 'routes'
            '$lookup': {
                'from': 'routes',
                'localField': '_id',
                'foreignField': '_id',
                'as': 'route_info'
            }
        },
        {
            # Rozwiń tablicę route_info, jeśli istnieje (dołącz tylko matching routes)
            '$unwind': '$route_info'
        },
        {
            # Posortuj po średniej ocenie malejąco, aby najlepsze były na górze
            '$sort': {
                'average_review': -1
            }
        },
        {
            # Ogranicz wyniki do 10 najlepszych
            '$limit': 10
        },
        {
            # Projektuj pola, które chcemy zwrócić
            '$project': {
                '_id': 0, # Wyklucz domyślne _id grupy
                'route_id': '$_id',
                'route_name': '$route_info.name',
                'average_review': { '$round': ['$average_review', 2] } # Zaokrąglij do 2 miejsc po przecinku
            }
        }
    ]
    # Użyj istniejącej funkcji do pobierania danych
    return pobierz_dane_z_mongo(pipeline, NAZWA_KOLEKCJI)

def top_10_routes_by_ascends():
    pipeline = [
        {
            # Zgrupuj przejścia po route_id i oblicz średnią ocenę (review)
            '$group': {
                '_id': '$route_id',
                'count': { '$sum': 1 }
            }
        },
        {
            # Dołącz informacje o trasie z kolekcji 'routes'
            '$lookup': {
                'from': 'routes',
                'localField': '_id',
                'foreignField': '_id',
                'as': 'route_info'
            }
        },
        {
            # Rozwiń tablicę route_info, jeśli istnieje (dołącz tylko matching routes)
            '$unwind': '$route_info'
        },
        {
            # Posortuj po średniej ocenie malejąco, aby najlepsze były na górze
            '$sort': {
                'count': -1
            }
        },
        {
            # Ogranicz wyniki do 10 najlepszych
            '$limit': 10
        },
        {
            # Projektuj pola, które chcemy zwrócić
            '$project': {
                '_id': 0, # Wyklucz domyślne _id grupy
                'route_id': '$_id',
                'route_name': '$route_info.name',
                'count': 1
            }
        }
    ]
    # Użyj istniejącej funkcji do pobierania danych
    return pobierz_dane_z_mongo(pipeline, NAZWA_KOLEKCJI)

def top_10_users_by_ascents():
    pipeline = [
        {
            # Zgrupuj przejścia po user i zlicz liczbę przejść
            '$group': {
                '_id': '$user',
                'ascent_count': { '$sum': 1 }
            }
        },
        {
            # Posortuj po liczbie przejść malejąco
            '$sort': {
                'ascent_count': -1
            }
        },
        {
            # Ogranicz wyniki do 10 najlepszych użytkowników
            '$limit': 10
        },
        {
            # Projektuj pola, które chcemy zwrócić
            '$project': {
                '_id': 0, # Wyklucz domyślne _id grupy
                'user': '$_id',
                'ascent_count': 1
            }
        }
    ]
    return pobierz_dane_z_mongo(pipeline, NAZWA_KOLEKCJI)

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

def add_multiple_routes():

    new_route_document = {
        #"name": f"Route from {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",  # Dodaj unikalną nazwę
        "created_at": datetime.datetime.now()  # Dodaj aktualną datę i czas
    }

    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)  # Timeout po 5s
    # Sprawdzenie połączenia
    client.admin.command('ismaster')
    db = client[NAZWA_BAZY_DANYCH]
    collection = db["routes"]

    result = collection.insert_one(new_route_document)

    client.close()

    return result.inserted_id

@app.route('/generate_xlsx')
def generate_xlsx():

    data_for_xlsx = ["qrades"]

    # Generuj 20 nowych identyfikatorów tras i dodaj je do listy
    for _ in range(20): # Pętla wykonująca się 20 razy
        data_for_xlsx.append(f"{base_url}route/{add_multiple_routes()}")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "QR Codes"
    sheet['A1'] = "QR Code Link"

    for index, item in enumerate(data_for_xlsx, start=2):
        sheet[f'A{index}'] = item

    excel_buffer = BytesIO()
    workbook.save(excel_buffer)
    excel_buffer.seek(0) # Przewiń bufor na początek

    return send_file(excel_buffer, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name='qr_codes.xlsx')

@app.route('/qr/<route_id_str>')
def get_qr_by_route(route_id_str):
    """
    Generuje i serwuje obrazek QR kodu dla danej trasy.
    Obrazek jest zwracany jako odpowiedź HTTP typu image/png.
    """
    try:
        # base_url_for_qr to pełny URL bazowy Twojej aplikacji (np. http://127.0.0.1:5000/)
        base_url_for_qr = request.url_root

        # Pełny URL, który zostanie zakodowany w QR kodzie
        # Zakładamy, że masz trasę '/route/<id>' w Twojej aplikacji
        pelny_url_dla_qr = f"{base_url_for_qr}route/{route_id_str}"

        # Inicjalizacja generatora QR kodu
        qr = qrcode.QRCode(
            version=None,  # Automatyczny dobór wersji
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # Niski poziom korekcji błędów
            box_size=10,  # Rozmiar pojedynczego "kwadracika" QR
            border=4,  # Grubość ramki wokół kodu QR
        )

        # Dodaj dane (URL) do QR kodu
        qr.add_data(pelny_url_dla_qr)
        qr.make(fit=True)  # Dopasuj rozmiar kodu

        # Utwórz obrazek QR kodu
        img = qr.make_image(fill_color="black", back_color="white")

        # Zapisz obrazek do bufora w pamięci (zamiast na dysk)
        # To kluczowy krok, aby wysłać obrazek bezpośrednio do przeglądarki
        buffer = BytesIO()
        img.save(buffer, format='PNG')  # Zapisz obraz do bufora jako PNG
        buffer.seek(0)  # Przewiń bufor na początek, aby dane mogły być odczytane

        # Zwróć odpowiedź HTTP zawierającą obrazek PNG
        # 'mimetype='image/png'' informuje przeglądarkę, że to plik PNG
        return Response(buffer.getvalue(), mimetype='image/png')

    except Exception as e:
        # Obsługa błędów, jeśli coś pójdzie nie tak podczas generowania
        print(f"Wystąpił błąd podczas generowania QR kodu dla {route_id_str}: {e}")
        return Response("Wystąpił błąd serwera podczas generowania QR kodu.", status=500)

@app.route('/')  # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def index():

    return render_template('index.html')

@app.route('/all_data') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def all_data():

    dane_z_bazy, blad = get_all_data()

    top_routes_data, error = top_10_routes_by_rating()

    labels = [route.get('route_name', 'Brak nazwy') for route in top_routes_data]
    data_values = [route.get('average_review', 0) for route in top_routes_data]

    top_routes_data2, error = top_10_routes_by_ascends()

    labels2 = [route.get('route_name', 'Brak nazwy') for route in top_routes_data2]
    data_values2 = [route.get('count', 0) for route in top_routes_data2]

    top_routes_data3, error = top_10_users_by_ascents()

    labels3 = [route.get('user', 'Brak nazwy') for route in top_routes_data3]
    data_values3 = [route.get('ascent_count', 0) for route in top_routes_data3]

    return render_template('all_data.html', dane=dane_z_bazy,
                           chart_labels=labels, chart_data=data_values,
                           chart_labels2=labels2, chart_data2=data_values2,
                           chart_labels3=labels3, chart_data3=data_values3,
                           error=blad)

@app.route('/user')
@app.route('/user/<user_id>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def ascends_by_user(user_id = None):

    if not user_id: user_id = request.cookies.get('user_name')
    dane_z_bazy, blad = all_ascends_by_user(user_id)

    trudnosci_drog, blad = grades_by_user(user_id)

    etykiety = [item['grade'] for item in trudnosci_drog]
    wartosci = [item['count'] for item in trudnosci_drog]

    scatter_data_raw, scatter_error = all_ascends_by_user_for_scatter(user_id)

    # Definicja skali trudności (musi być zgodna z JS)
    # climbing_grades = ['5a', '5b', '5c', '6a', '6b', '6c', '7a', '7b', '7c']

    scatter_chart_data = []
    if not scatter_error and scatter_data_raw:
        for ascend in scatter_data_raw:
            grade_str = ascend.get('grade') # Grade z kolekcji ascends
            created_at_dt = ascend.get('created_at') # Datetime object from MongoDB

            if grade_str and created_at_dt:
                # Znajdź indeks stopnia w skali, dodaj 1, aby uzyskać wartość liczbową dla osi Y
                numerical_y = CLIMBING_GRADES.index(grade_str) + 1 if grade_str in CLIMBING_GRADES else None

                if numerical_y is not None:
                    scatter_chart_data.append({
                        'x': created_at_dt.strftime('%Y-%m-%d'), # Format daty dla JS
                        'y': numerical_y
                    })
    # --- Koniec przetwarzania danych dla wykresu ---

    return render_template('user.html', dane=dane_z_bazy, etykiety=etykiety, wartosci=wartosci,
                           scatter_chart_data=scatter_chart_data, # Przekaż przetworzone dane dla wykresu
                           climbing_grades=CLIMBING_GRADES, user_name=user_id) # Przekaż skalę trudności do JS)

@app.route('/route/<route_id_str>')
def ascends_by_route(route_id_str):

    user_from_cookie = request.cookies.get('user_name')

    dynamic_route_id_obj = ObjectId(route_id_str)
    trudnosci_drog, blad = grades_by_route(dynamic_route_id_obj)

    etykiety = [item['grade'] for item in trudnosci_drog]
    wartosci = [item['count'] for item in trudnosci_drog]

    ocena_drogi, blad = avg_review_by_route(dynamic_route_id_obj)

    average_review = ocena_drogi[0].get('average_review') if ocena_drogi and ocena_drogi[0].get(
        'average_review') is not None else 3

    available_grades_for_template = CLIMBING_GRADES  # Domyślnie pełna skala

    # ### ZMIANA: Logika sugestii stopni oparta na najstarszym przejściu DANEJ TRASY ###

    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    db = client[NAZWA_BAZY_DANYCH]
    ascends_collection = db['ascends']  # 'ascends' collection

    # Znajdź najstarsze przejście dla TEJ TRASY, niezależnie od użytkownika
    first_ascend_cursor = ascends_collection.find(
        {"route_id": dynamic_route_id_obj}
    ).sort("created_at", 1).limit(1)

    first_ascend_doc = None
    for doc in first_ascend_cursor:
        first_ascend_doc = doc
        break  # Pobierz pierwszy i zakończ

    if first_ascend_doc:
        first_grade = first_ascend_doc.get('grade')
        if first_grade and first_grade in CLIMBING_GRADES:
            first_grade_index = CLIMBING_GRADES.index(first_grade)

            # Oblicz granice dla +/- 2 stopni
            min_index = max(0, first_grade_index - 2)
            max_index = min(len(CLIMBING_GRADES) - 1, first_grade_index + 2)

            available_grades_for_template = CLIMBING_GRADES[min_index: max_index + 1]

    query = {
        "user": user_from_cookie,
        "route_id": ObjectId(route_id_str)
    }
    collection = db["ascends"]
    existing_document = collection.find_one(query)

    routes_collection = db["routes"]  # Dostęp do kolekcji routes
    route_info_doc = routes_collection.find_one({"_id": dynamic_route_id_obj})
    route_name = route_info_doc.get('name', '') if route_info_doc else ''
    route_tag = route_info_doc.get('tag', '') if route_info_doc else ''  # Pobierz tag, domyślnie pusty string

    # Sprawdź, czy to jest pierwszy wpis dla tej trasy
    existing_ascends_count = ascends_collection.count_documents({"route_id": dynamic_route_id_obj})
    is_first_ascent_flag = (existing_ascends_count == 0)

    initial_data_for_form = {
        'route_id': route_id_str,
        'user': user_from_cookie if user_from_cookie else '',  # Pre-fill user if cookie exists
        'is_first_ascent': is_first_ascent_flag,
        'route_name': route_name,  # Przekaż nazwę trasy do formularza
        'route_tag': route_tag  # Przekaż tag trasy do formularza
    }

    initial_data_for_form['user'] = user_from_cookie
    if existing_document:
        initial_data_for_form['grade'] = existing_document.get('grade')
        initial_data_for_form['review'] = existing_document.get('review')
       # initial_data_for_form['user'] = existing_document.get('user')  # Ensure user is also passed

    if client:
        client.close()

    return render_template('route.html', etykiety=etykiety, wartosci=wartosci,
                           average_review=average_review,
                           initial_data=initial_data_for_form,
                           available_grades=available_grades_for_template, error=blad)

@app.route('/add_ascend', methods=['POST'])
def add_ascend():
    # --- 1. Pobierz dane z formularza ---
    route_id_str = request.form.get('route_id')
    grade = request.form.get('grade')
    review_str = request.form.get('review')
    user = request.form.get('user')
    name = request.form.get('route_name')  # Nowe pole z formularza
    tag = request.form.get('route_tag')  # Nowe pole z formularza

    grade = grade.strip() # Usuń białe znaki z początku/końca
    review_int = int(review_str) # Konwersja stringa na liczbę całkowitą
    user = user.strip() # Usuń białe znaki z początku/końca

    # --- Zapytanie do znalezienia istniejącego wpisu ---
    query = {
        "user": user,
        "route_id": ObjectId(route_id_str)
    }

    new_ascend_document = {
        "route_id": ObjectId(route_id_str),
        "grade": grade,
        "review": review_int,     # Użyj skonwertowanej liczby całkowitej
        "user": user,
        "created_at": datetime.datetime.now()  # Dodaj aktualną datę i czas
        # _id zostanie automatycznie dodane przez MongoDB
    }

    # Wstaw dokument do kolekcji
    client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)  # Timeout po 5s
    # Sprawdzenie połączenia
    client.admin.command('ismaster')
    db = client[NAZWA_BAZY_DANYCH]
    collection = db["ascends"]

    existing_document = collection.find_one(query)
    # Dane do zaktualizowania/wstawienia
    update_data = {
        "grade": grade,
        "review": review_int,
        "created_at": datetime.datetime.now()
    }

    if existing_document:
        collection.update_one(query, {'$set': update_data})
    else:
        collection.insert_one(new_ascend_document)

    routes_collection = db["routes"]  # Dostęp do kolekcji routes

    # Jeśli to pierwszy wpis dla tej trasy (na podstawie flagi z formularza)
    route_update_data = {}
    if name:
        route_update_data['name'] = name
    if tag:  # Tag może być pusty, ale nadal chcemy go zapisać
        route_update_data['tag'] = tag

    if route_update_data:
        routes_collection.update_one({"_id": ObjectId(route_id_str)}, {"$set": route_update_data}, upsert=False)

    client.close()

    response = make_response(redirect(url_for('ascends_by_route', route_id_str=route_id_str)))  # Przekieruj np. na stronę główną po sukcesie
    response.set_cookie('user_name', user, max_age=30 * 24 * 60 * 60, httponly=True, secure=True)  # secure=True w produkcji

    return response

def clean_unlinked_routes():
    client = None
    try:
        client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        db = client[NAZWA_BAZY_DANYCH]
        routes_collection = db["routes"]
        ascends_collection = db["ascends"]

        # Krok 1: Znajdź wszystkie ID tras, które MAJĄ przejścia
        # Zbieramy unikalne route_id z kolekcji ascends
        linked_route_ids = ascends_collection.distinct("route_id")

        # Krok 2: Znajdź wszystkie trasy, których _id NIE MA w liście linked_route_ids
        # Tworzymy zapytanie, które znajdzie trasy, które nie są powiązane
        query_for_unlinked = {
            "_id": {"$nin": linked_route_ids}
        }

        # Opcjonalnie: możesz wyświetlić trasy do usunięcia przed faktycznym usunięciem
        print("\nTrasy do usunięcia (nie posiadające przejść):")
        for doc in routes_collection.find(query_for_unlinked):
            print(f"- ID: {doc.get('_id')}, Nazwa: {doc.get('name', 'Brak nazwy')}")
        print("---")

        # Krok 3: Usuń znalezione trasy
        result = routes_collection.delete_many(query_for_unlinked)
        deleted_count = result.deleted_count
        print(f"Pomyślnie usunięto {deleted_count} tras bez powiązanych przejść.")

    except ConnectionFailure as e:
        print(f"Błąd połączenia z bazą danych podczas czyszczenia tras: {e}")
        deleted_count = -1 # Oznacza błąd
    except Exception as e:
        print(f"Wystąpił błąd podczas czyszczenia tras: {e}")
        deleted_count = -1 # Oznacza błąd
    finally:
        if client:
            client.close()
    return deleted_count

@app.route('/clean_routes')
def clean_routes_endpoint():
    deleted = clean_unlinked_routes()
    if deleted > -1:
        flash(f"Usunięto {deleted} tras bez powiązanych przejść.", 'success')
    else:
        flash("Wystąpił błąd podczas czyszczenia tras.", 'error')
    return redirect(url_for('index'))

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)