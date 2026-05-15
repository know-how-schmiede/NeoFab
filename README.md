![NeoFab Logo](images/Logo_NeoFab.png)


# NeoFab – Multilingual 3D Print Order Management System

NeoFab is a modern, multilingual web application designed for managing 3D printing orders in academic, maker, and research environments.  
The system provides a streamlined workflow for submitting, reviewing, tracking, and communicating about 3D printing projects – fully integrated with file uploads, messaging, and administrative tools.

NeoFab is developed bilingual from the start, with **English (default)** and **German** support.  
All UI elements, status texts, and system emails are fully internationalized.

---

## 🚀 Features

- **Multilingual UI (EN/DE)**  
  Fully internationalized via gettext/Babel.

- **User Accounts & Authentication**  
  Registration, login, password reset, user roles.

- **3D Print Order Management**  
  Project metadata, 3D model uploads (STL/STEP), G-Code, priorities & deadlines.

- **Integrated Messaging System**  
  Built-in communication between submitter and admin/operator.  
  Email notifications only as short hints — full content stored in NeoFab.

- **Admin Dashboard**  
  Manage materials, colors, printers, printer profiles, departments, status values, and user accounts.

- **File Management**  
  Project-based storage for models, G-Code, and additional attachments.

- **Status Tracking & History**  
  Complete audit trail for project and print job state changes.

- **Bootstrap-based Responsive UI**  
  Clean, modern interface using Bootstrap 5 and Jinja templates.

---

## 🛠️ Tech Stack

- **Python 3 + Flask**
- **SQLAlchemy** (database ORM)
- **Flask-Login + Werkzeug Security**
- **Flask-Babel** for i18n
- **Bootstrap 5** (UI)
- **SQLite / MariaDB / PostgreSQL**
- **Nginx / Gunicorn (optional for production)**

---

## 📦 Project Structure (planned)

neofab/<br>
├─ app/<br>
│ ├─ models/<br>
│ ├─ routes/<br>
│ ├─ templates/<br>
│ ├─ static/<br>
│ ├─ i18n/ # language files (en, de)<br>
│ └─ utils/<br>
├─ migrations/<br>
├─ tests/<br>
├─ README.md<br>
└─ run.py<br>

## Setup

Installations-Scripte unter /script
Zuerst /script/README.md lesen !!!

## Screenshots V0.8.6

![Home NeoFab](images/NeoFab_V0-8-6_-00.jpg)
![STL/3MF-Viewer](images/NeoFab_V0-8-6_-01.jpg)
![Systemeinstellungen](images/NeoFab_V0-8-6_-02.jpg)
![Admin Panel](images/NeoFab_V0-8-6_-03.jpg)
![User-Profil](images/NeoFab_V0-8-6_-04.jpg)
![Komunikation - Chatfunktion](images/NeoFab_V0-8-6_-05.jpg)
![Auftrag - Druckaufträge](images/NeoFab_V0-8-6_-06.jpg)
![Auftrag - 3D-Modelle](images/NeoFab_V0-8-6_-07.jpg)
![Auftrag - Dokumentation](images/NeoFab_V0-8-6_-08.jpg)
![Auftrag - Allgemein](images/NeoFab_V0-8-6_-09.jpg)
![Auftragsliste](images/NeoFab_V0-8-6_-10.jpg)
![LogIn](images/NeoFab_V0-8-6_-11.jpg)
