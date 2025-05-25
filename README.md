# QRades - Climbing Route Management with QR Codes

## Project Description

QRades is a Flask-based web application that allows for the management of climbing routes, logging of ascents, and generation of QR codes for each route. The QR codes can then be used to quickly access route details and add new ascents directly from the climbing site. The application also offers basic statistics on route difficulty and reviews, as well as the ability to export data to an XLSX file.

## Features
* **Route Management:** Add and view climbing routes (name, grade, creation date).
* **Ascent Logging:** Users can add entries about their ascents, rating the route (1-5) and providing a grade (e.g., 6a, 7b).
* **QR Code Generation:** Automatic generation of unique QR codes for each route, leading directly to the route details page.
* **Route Statistics:** Display of difficulty grade distribution for a given route and average review rating.
* **User Memory:** The application remembers the user's name in cookies, facilitating quick addition of subsequent ascents.
* **Data Export:** Ability to generate an XLSX file with a list of QR code URLs for all routes.
* **Responsive Interface:** Thanks to MDBootstrap, the interface is adapted to various screen sizes.

## Technologies Used
### Backend:
* **Flask:** Python web microframework.
* **PyMongo:** Python driver for MongoDB.
* **python-dotenv:** For managing environment variables.
* **gunicorn:** WSGI HTTP Server (for production deployment).
* **qrcode:** Library for generating QR codes.
* **Pillow:** Image processing library (required by qrcode).
* **openpyxl:** Library for reading/writing XLSX files.

### Database:
* MongoDB: NoSQL, document-oriented database.

### Frontend:
* **HTML5**
* **CSS3**
* **JavaScript**
* **MDBootstrap:** UI framework based on Bootstrap and Material Design.
* **Chart.js:** Charting library.

## Usage
* Homepage (/): Displays a list of climbing routes.
* Route Details (/route/<route_id> or /details/<route_id>): Clicking on a route ID will show detailed statistics (difficulty distribution, average review) and options to add a new ascent.
* Add Ascent (/add_ascend): Form for logging ascents.
* Generate QR (/qr/<route_id>): Displays the QR code image for a given route.
* Download XLSX (/generate_xlsx): Generates and downloads an Excel file with a list of QR code URLs.

## Future Improvements (Ideas)
* User authentication and authorization.
* Ability to edit and delete routes/ascents.
* More advanced statistics and visualizations.
* Integration with climbing APIs (e.g., OpenBeta).
* Ability to add photos to ascents.
