from flask import Flask, render_template, Response, request, redirect, url_for, make_response, send_file, flash
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from io import BytesIO
import os
import qrcode
from openpyxl import Workbook
import datetime # Do ustawienia daty ważności cookie

base_url = "https://qrades.com/"

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

def pobierz_all_data():
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
                '_id': '$route_info._id', # ID trasy
                'name': '$route_info.name', # Nazwa trasy
                'route_created_at': '$route_info.created_at', # Data utworzenia trasy (z kolekcji routes)
                'most_frequent_grade': '$most_frequent_grade', # Najczęściej występująca ocena z wpisów
                'average_review': { '$round': ['$average_review', 1] }, # Średnia recenzja, zaokrąglona do 1 miejsca po przecinku
                'latest_ascend_date': '$latest_ascend_date' # DODANO: Najnowsza data wpisu (z kolekcji ascends)
            }
        }
    ]

    return pobierz_dane_z_mongo(pipeline, "ascends")

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
        "name": f"Route from {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",  # Dodaj unikalną nazwę
        "created_at": datetime.datetime.now()  # Dodaj aktualną datę i czas
    }

    # Wstaw dokument do kolekcji
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
    # Dane, które mają znaleźć się w pliku XLSX
    # Możesz to dynamicznie pobierać z bazy danych, np. wszystkie ID tras
    # Na potrzeby przykładu użyjemy podanych przez Ciebie wartości
    data_for_xlsx = [
        "qrades"
    ]

    # Generuj 20 nowych identyfikatorów tras i dodaj je do listy
    for _ in range(20): # Pętla wykonująca się 20 razy
        data_for_xlsx.append(f"{base_url}route/{add_multiple_routes()}")

    # Utwórz nowy skoroszyt (workbook) Excela
    workbook = Workbook()
    # Wybierz aktywny arkusz (domyślnie "Sheet")
    sheet = workbook.active
    # Zmień nazwę arkusza, jeśli chcesz
    sheet.title = "QR Codes"

    # Dodaj nagłówek kolumny
    sheet['A1'] = "QR Code Link"

    # Wypełnij kolumnę 'A' danymi
    # Zaczynamy od wiersza 2, ponieważ wiersz 1 to nagłówek
    for index, item in enumerate(data_for_xlsx, start=2):
        sheet[f'A{index}'] = item

    # Dostosuj szerokość kolumny do zawartości (opcjonalne, ale zalecane)
    sheet.column_dimensions['A'].width = 50 # Ustaw stałą szerokość lub oblicz dynamicznie

    # Zapisz skoroszyt do bufora w pamięci
    # Jest to kluczowe, aby nie zapisywać pliku na dysku serwera, a od razu go wysłać
    excel_buffer = BytesIO()
    workbook.save(excel_buffer)
    excel_buffer.seek(0) # Przewiń bufor na początek

    # Zwróć plik jako odpowiedź do pobrania
    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='qr_codes.xlsx' # Nazwa pliku, który zostanie pobrany
    )

def generate_qr_code(dynamic_route_id_obj = None):
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
    dane_z_bazy, blad = pobierz_all_data()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('index.html', dane=dane_z_bazy, error=blad)

@app.route('/all_data') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def all_data():
    # Pobierz dane przy każdym żądaniu strony
    dane_z_bazy, blad = pobierz_all_data()

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    return render_template('all_data.html', dane=dane_z_bazy, error=blad)

@app.route('/user')
@app.route('/user/<user_id>') # Dekorator definiuje, że ta funkcja obsłuży żądania do głównego adresu ('/')
def ascends_by_user(user_id = None):
    # --- Konwersja stringa route_id na ObjectId ---

    if not user_id: user_id = request.cookies.get('user_name')
    dane_z_bazy, blad = all_ascends_by_user(user_id)

    # --- Pobierz i przetwórz dane dla wykresu rozrzutu ---
    scatter_data_raw, scatter_error = all_ascends_by_user(user_id)

    # Definicja skali trudności (musi być zgodna z JS)
    climbing_grades = [
        '5a', '5b', '5c', '6a', '6b', '6c', '7a', '7b', '7c', '8a', '8b', '8c', '9a', '9b', '9c'
    ]

    scatter_chart_data = []
    if not scatter_error and scatter_data_raw:
        for ascend in scatter_data_raw:
            grade_str = ascend.get('grade') # Grade z kolekcji ascends
            created_at_dt = ascend.get('created_at') # Datetime object from MongoDB

            if grade_str and created_at_dt:
                # Znajdź indeks stopnia w skali, dodaj 1, aby uzyskać wartość liczbową dla osi Y
                numerical_y = climbing_grades.index(grade_str) + 1 if grade_str in climbing_grades else None

                if numerical_y is not None:
                    scatter_chart_data.append({
                        'x': created_at_dt.strftime('%Y-%m-%d'), # Format daty dla JS
                        'y': numerical_y
                    })
    # --- Koniec przetwarzania danych dla wykresu ---

    return render_template('user.html',
                           dane=dane_z_bazy,
                           scatter_chart_data=scatter_chart_data, # Przekaż przetworzone dane dla wykresu
                           climbing_grades=climbing_grades) # Przekaż skalę trudności do JS)

    # Renderuj szablon HTML, przekazując mu pobrane dane i ewentualny błąd
    # Flask automatycznie szuka szablonów w folderze 'templates'
    #return render_template('user.html', dane=dane_z_bazy, error=blad)

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

    client.close()

    response = make_response(redirect(url_for('ascends_by_route', route_id_str=route_id_str)))  # Przekieruj np. na stronę główną po sukcesie
    response.set_cookie('user_name', user, max_age=30 * 24 * 60 * 60, httponly=True, secure=True)  # secure=True w produkcji

    return response

def clean_unlinked_routes():
    client = None
    deleted_count = 0
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

# Przykład użycia (możesz dodać nową trasę w Flasku, np. do panelu administracyjnego)
@app.route('/clean_routes')
def clean_routes_endpoint():
    deleted = clean_unlinked_routes()
    if deleted > -1:
        flash(f"Usunięto {deleted} tras bez powiązanych przejść.", 'success')
    else:
        flash("Wystąpił błąd podczas czyszczenia tras.", 'error')
    return redirect(url_for('index'))

def clean_duplicate_ascends():
    client = None
    deleted_count = 0
    duplicate_ascend_ids_to_delete = []

    try:
        client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        db = client[NAZWA_BAZY_DANYCH]
        ascends_collection = db["ascends"]

        # Agregacja do znalezienia duplikatów i identyfikacji tych do usunięcia
        # Chcemy znaleźć wszystkie dokumenty, które mają tę samą parę route_id i user,
        # ale NIE są pierwszym dokumentem napotkanym dla tej pary (posortowanym po dacie utworzenia).
        pipeline = [
            {
                '$sort': {
                    'created_at': 1, # Sortujemy po dacie, aby łatwo wybrać najstarszy (lub najnowszy)
                    '_id': 1 # Dodatkowo po _id dla determinizmu w przypadku tej samej daty
                }
            },
            {
                '$group': {
                    '_id': {
                        'route_id': '$route_id',
                        'user': '$user'
                    },
                    'count': { '$sum': 1 },
                    'first_id': { '$first': '$_id' }, # ID pierwszego napotkanego dokumentu
                    'all_ids': { '$push': '$_id' } # Zbierz wszystkie ID w grupie
                }
            },
            {
                '$match': {
                    'count': { '$gt': 1 } # Interesują nas tylko grupy z więcej niż jednym dokumentem
                }
            },
            {
                '$project': {
                    '_id': 0, # Nie potrzebujemy _id z grupy
                    'duplicate_ids': {
                        '$filter': {
                            'input': '$all_ids',
                            'as': 'id',
                            'cond': { '$ne': ['$$id', '$first_id'] } # Zostaw tylko ID, które nie są 'first_id'
                        }
                    }
                }
            }
        ]

        # Wykonaj agregację
        duplicates_info = list(ascends_collection.aggregate(pipeline))

        # Zbieranie ID duplikatów do usunięcia
        for doc in duplicates_info:
            duplicate_ascend_ids_to_delete.extend(doc['duplicate_ids'])

        if duplicate_ascend_ids_to_delete:
            print(f"\nZnaleziono {len(duplicate_ascend_ids_to_delete)} zduplikowanych wpisów do usunięcia:")
            for dup_id in duplicate_ascend_ids_to_delete:
                print(f"- Duplikat ID: {dup_id}")
            print("---")

            # Krok 3: Usuń znalezione duplikaty
            # Usuwamy wszystkie znalezione duplikaty, czyli te, które NIE są 'first_id'
            result = ascends_collection.delete_many({
                "_id": {"$in": duplicate_ascend_ids_to_delete}
            })
            deleted_count = result.deleted_count
            print(f"Pomyślnie usunięto {deleted_count} zduplikowanych wpisów w kolekcji ascends.")
        else:
            print("\nNie znaleziono zduplikowanych wpisów w kolekcji ascends.")

    except ConnectionFailure as e:
        print(f"Błąd połączenia z bazą danych podczas czyszczenia duplikatów: {e}")
        deleted_count = -1 # Oznacza błąd
    except Exception as e:
        print(f"Wystąpił błąd podczas czyszczenia duplikatów: {e}")
        deleted_count = -1 # Oznacza błąd
    finally:
        if client:
            client.close()
    return deleted_count

# Przykład użycia (możesz dodać nową trasę w Flasku, np. do panelu administracyjnego)
@app.route('/clean_duplicate_ascends')
def clean_duplicate_ascends_endpoint():
    deleted = clean_duplicate_ascends()
    if deleted > -1:
        flash(f"Usunięto {deleted} zduplikowanych przejść.", 'success')
    else:
        flash("Wystąpił błąd podczas czyszczenia duplikatów przejść.", 'error')
    return redirect(url_for('index'))

# Uruchomienie aplikacji Flask w trybie deweloperskim
if __name__ == '__main__':
    # debug=True automatycznie przeładowuje serwer przy zmianach w kodzie
    # i pokazuje szczegółowe błędy w przeglądarce (NIE UŻYWAJ W PRODUKCJI!)
    app.run(debug=True)