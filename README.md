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
